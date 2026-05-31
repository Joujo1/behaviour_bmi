# System Overview

<!-- TODO: add full cross-layer diagram once both layer diagrams are finalised -->

## Raspberry Pi Layer

Every cage runs one Python process (`main.py`). The diagram below shows all source files in `RPi_main/`, their roles, and how data flows between them. Excludes `debug/` and `audio.py` (offline waveform builder, not used at runtime).

Yellow boxes are Python modules. The pink box (`cage_controller.service`) is the systemd unit that starts `main.py` at boot. Solid arrows show runtime data flow; dotted arrows show config imports from `config.py`; the dashed arrow from the service to `main.py` indicates systemd process execution.

![Pi-side architecture](img/Doc%20-%20pi_architecture_doc.svg)

### Thread priorities

Four timing-critical threads run on isolated core 3 under `SCHED_FIFO`, with priorities encoding their latency budget. All remaining threads run on cores 0–2 at default priority.

| Thread | Priority | File | Role |
|---|---|---|---|
| Click trigger | SCHED_FIFO 85 | `actions.py` | Busy-wait click TTL timing — highest priority because click timestamps are the experimentally meaningful variable |
| GPIO monitor | SCHED_FIFO 75 | `gpio_handler.py` | Drains kernel beam-break events from gpiod; kernel timestamps the interrupt before this thread runs |
| Hold timers | SCHED_FIFO 72 | `engine.py` | One per beam, busy-wait for the required hold duration; must preempt the FSM but yield to the GPIO monitor |
| FSM | SCHED_FIFO 70 | `engine.py` | Single consumer of the event queue; drives all state transitions, action dispatch, and trial-outcome decisions |
| TCP command receiver | default | `tcp_command_receiver.py` | Reads trial JSON and control commands from the PC; pushes trial-complete / trial-aborted events back |
| UDP frame sender | default | `udp_sender_pi.py` | Dequeues assembled per-frame bundles and emits them as UDP packets to the PC |
| Camera / picamera2 | default | `streamer.py` | H.264 capture and encoding via picamera2; assembles per-frame bundles (GPIO snapshot + FSM events) |
| NTP reporter | default | `main.py` | Queries chrony every 5 s and pushes a `sync_status` event to the PC over TCP |

---

## Linux PC Layer

The PC runs two Python processes launched by `main.py`. The UI process serves the web interface and drives all trial logic; the Acquisition process receives and stores the camera stream. They share state only through Valkey and Postgres — no direct IPC.

![Linux-layer architecture](img/Doc%20-%20Linux%20Layer.svg)

### Top level

**`main.py`**
Top-level entry point. Spawns two subprocesses: the UI process (`ui.ui_main`) and the Acquisition process (`acquisition.acquisition_main`). Accepts a session name and optional duration as arguments.

**`config.py`**
Single source of truth for all PC-side constants: `N_CAGES = 12`, `UDP_BASE_PORT`, `TCP_COMMAND_PORT = 6000`, `FLASK_PORT = 5000`, `POSTGRES_DSN`, `VALKEY_HOST/PORT`, `NAS_BASE_PATH`, `DB_CHUNK_SIZE = 1000`, `WATCHDOG_DEAD_THRESHOLD_SECONDS = 10`, `CLICK_WIDTH_S`.

**`bin_viewer.py`**
Standalone offline analysis tool, not used at runtime. Launches its own Flask app on port 7000. Reads `.bin` recording files from the NAS, parses the binary packet format (same header as `packet_parser.py`), and serves a browser UI with a Plotly GPIO waveform viewer, trial timeline, frame-by-frame JPEG/H.264 preview (via WebCodecs), and trial outcome stats. Run with `python bin_viewer.py`.

### `shared/`

**`shared/logger.py`**
Utility function `get_logger(name, log_dir, level)`. Returns a configured `logging.Logger` that writes to stdout and optionally to a log file.

### `command/`

**`command/tcp_command_sender.py`**
`TCPCommandSender` — one instance per cage, created at UI startup. Manages the persistent TCP connection to the Pi. Lazy-connects on the first `send()` call. `send()` writes a JSON command and blocks waiting for an ACK. A background `_read_loop` thread continuously reads incoming messages: ACK/ERROR responses go to an internal `_response_queue` to unblock `send()`, and everything else (trial events, sync status) is passed to the `on_event` callback, which is wired to `event_handler.handle_trial_event`.

### `acquisition/`

**`acquisition/acquisition_main.py`**
Acquisition process entry point. Creates one `UDPreceiver` and one `FrameWriter` per cage, starts the `Watchdog`, and starts a stats logger thread that appends per-cage FPS and drop counts to `frame_stats.csv` on the NAS every 5 seconds.

**`acquisition/udp_receiver.py`**
`UDPreceiver` — dual-threaded. A listener thread calls `recvfrom` in a tight loop and pushes raw datagrams into a `queue.Queue(maxsize=60)` with an 8 MB kernel socket buffer. A worker thread drains the queue and calls `packet_parser.parse_packet()`, then forwards the result to the frame callback. The split prevents slow callback processing from dropping kernel-buffered packets.

**`acquisition/packet_parser.py`**
Stateless parser for the binary UDP wire format. `parse_packet()` unpacks the fixed-size header (format `<IQIIBBBBBBBBB`), decodes the JSON events blob, and returns a `ParsedFrame` dataclass containing all GPIO signal states, the Pi sequence number, a microsecond timestamp (`CLOCK_MONOTONIC` from the Pi), the raw packet bytes, and network arrival time. Returns `None` on malformed input.

**`acquisition/frame_writer.py`**
`FrameWriter` — one per cage. `write_frame()` always publishes to Valkey: either `PUBLISH cage:{id}:h264_stream` (if streaming is on) or `SET cage:{id}:latest_frame`. When `cage:{id}:recording == "1"`, it additionally appends the raw packet to a `.bin` file on the NAS and writes a chunk index entry to Postgres. Postgres writes are batched in memory and flushed every `DB_CHUNK_SIZE = 1000` frames to avoid per-frame round-trips.

**`acquisition/watchdog.py`**
`Watchdog` — single thread, monitors all cages. Every second, reads per-cage stats (fps, drop counts, streaming/recording flags) and writes them to the Valkey hash key `camera_status` via `HSET cage_{id} "alive|fps=N|drops=N|..."`. If a cage has not received a frame within `WATCHDOG_DEAD_THRESHOLD_SECONDS = 10`, it marks that cage as dead. This key is polled by the `/cameras/status` REST endpoint.

### `ui/`

**`ui/ui_main.py`**
Flask application factory and startup code. Registers all 11 blueprints. Creates one `TCPCommandSender` and one `CageRunner` per cage. On startup, clears stale Valkey keys from any previous run (`streaming`, `recording`, `fan`, `strip`, `active_session`). Exposes the WebSocket route `/cage/<id>/ws/video` and the root dashboard route `/`.

**`ui/cage_runner.py`**
`CageRunner` — one per cage, permanent object. The trial loop runs inside a thread that starts and stops per session. Each iteration: during the ITI, pre-computes the next trial by calling `_apply_bias()` → `_resolve_sides()` → `_expand_clicks()` → `_resolve_aliases()`, then sends the trial JSON to the Pi via `TCPCommandSender.send()`, then blocks on `threading.Event.wait()` until `on_trial_complete()` is called from the event handler thread. Supports `switch_substage()` for mid-session curriculum advancement without stopping the runner. Also holds the current `context` dict (`session_id`, `substage_id`, `correct_side`, `click_seed`) which `event_handler` reads before signalling completion.

**`ui/event_handler.py`**
`handle_trial_event()` — the `on_event` callback wired into every `TCPCommandSender`, called on the TCP reader thread. Routes `sync_status` events to a Valkey key with a 15-second TTL. For `trial_complete` and `trial_aborted`: reads the runner context, calls `runner.on_trial_complete()` to unblock the trial loop, inserts the result into `trial_results` in Postgres, then calls `advancement.evaluate()`. If the advancement decision is not "stay", calls `advancement.apply()`, swaps the runner's substage via `runner.switch_substage()`, and writes an `advancement` notification to Valkey with a 20-second TTL.

**`ui/advancement.py`**
`evaluate(subject_id, substage_id, conn)` — queries `trial_results` filtered by `substage_entered_at`, computes `pct_correct` over a rolling window, and returns `"advance"`, `"fall_back"`, or `"stay"`. `apply(subject_id, substage_id, decision, conn)` — updates the subject's current substage in Postgres and returns the new substage ID. Criterion handlers: `pct_correct`, `min_trials`.

**`ui/bias_algorithms.py`**
Registry of side-bias correction algorithms. Each algorithm is a function that takes recent trial history and returns a `left_probability` in [0, 1], or `None` to leave the trial unchanged. Three algorithms registered: `brody` (performance equalisation — push trials to the harder side, window 20), `ibl` (layup after wrong trial — push to preferred side, window 10), `rebalance` (presentation rebalance — push toward under-presented side, window 20). The `REGISTRY` dict maps algorithm name to an `AlgorithmSpec` dataclass containing the function and window size.

**`ui/click_generator.py`**
`generate_clicks(left_rate, right_rate, duration, seed, min_ici)` — generates independent left and right Poisson click trains. Inter-click intervals are exponentially distributed. A minimum ICI of `2 × CLICK_WIDTH_S = 6 ms` (start-to-start) prevents waveform addition artifacts in the audio buffer on the Pi; clicks drawn too close are shifted forward rather than dropped. Returns a dict with `left_clicks` and `right_clicks` as sorted lists of timestamps in seconds.

### `ui/endpoints/`

**`session.py`** — `POST /session/open` creates a new session row in Postgres and auto-starts streaming, recording, and the CageRunner. `POST /session/{id}/close` stops the runner and recording. `GET /sessions/active`, `GET /sessions`.

**`trial.py`** — `POST /cage/{id}/trial/run` starts the CageRunner manually. `POST /cage/{id}/trial/run/stop` stops it. `GET /cage/{id}/run/status`. `GET /cage/{id}/advancement` reads the current advancement notification from Valkey.

**`stream.py`** — `POST /cage/{id}/stream/start|stop` and `POST /cage/{id}/recording` set Valkey flags. `GET /cage/{id}/frame` returns the latest JPEG snapshot. `WS /cage/{id}/ws/video` subscribes to the `cage:{id}:h264_stream` Valkey pub/sub channel and forwards H.264 NAL units to the browser in real time. `GET /cameras/status` reads the Watchdog's `camera_status` hash. `GET /cameras/peripherals` returns fan/strip state.

**`control.py`** — `POST /cage/{id}/fan`, `POST /cage/{id}/strip` send peripheral commands to the Pi. `POST /trial/graph` renders a trial FSM as a Graphviz SVG. `GET /cage/{id}/sync` returns the latest NTP sync status from Valkey.

**`curriculum.py`** — CRUD endpoints for the training curriculum: stages, substages, and criteria. All backed by Postgres.

**`subjects.py`** — Subject create, list, and update endpoints.

**`metrics.py`** — Aggregate performance metric queries against `trial_results`. Used by the dashboard charts.

**`export.py`** — Queries `trial_results` and related tables and returns CSV or JSON for download.

**`scoresheet.py`** — Per-session trial outcome scoresheet view.

**`builder.py`** — Trial definition builder: validates and previews trial JSON structures before saving to a substage.

**`dev.py`** — Development and debug endpoints, not used in production sessions.

