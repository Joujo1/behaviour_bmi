# System Overview

The system has two physical parts: the **Raspberry Pis** (one per cage) and the **Linux PC** (one for everything else). This page explains what runs where and what each file does.

---

## The Raspberry Pi side

Each cage has its own Pi. The Pi runs a single Python program: `RPi_main/main.py`.

That one program starts several threads that all run at the same time:

| Thread | File | What it does |
|---|---|---|
| FSM | `engine.py` | Runs the trial state machine — the brain of the trial. Reads events from a queue and decides what happens next. |
| GPIO monitor | `gpio_handler.py` | Watches for beam breaks. When a beam is broken, it puts an event into the FSM's queue. Also drives other peripherals such as LEDs.|
| Hold timers | `engine.py` | When a beam-break transition requires the beam to stay broken for X ms, these timers enforce that wait. |
| Click trigger | `actions.py` | Fires click sounds at precise times. Has the highest priority. |
| Camera | `streamer.py` | Captures H.264 video via picamera2. Once per frame, it also grabs the current GPIO state and any FSM events, and bundles everything together. |
| UDP sender | `udp_sender_pi.py` | Takes the bundles from the camera thread and sends them to the PC as UDP packets. |
| TCP receiver | `tcp_command_receiver.py` | Listens for commands from the PC (e.g. "run this trial"). Sends back trial results when a trial finishes. |
| NTP reporter | `main.py` | Every 5 seconds, asks the Pi's clock daemon how well-synced the clock is, and reports that to the PC over TCP. |

The four timing-critical threads (FSM, GPIO, hold timers, click trigger) all run on a dedicated CPU core (core 3) with real-time scheduling (`SCHED_FIFO`). The priority numbers decide who can interrupt whom:

| Thread | Priority | Why this priority |
|---|---|---|
| Click trigger | 85 | Highest — click timing is the key experimental variable |
| GPIO monitor | 75 | Needs to react to beam breaks fast |
| Hold timers | 72 | Must be able to interrupt the FSM when a hold expires |
| FSM | 70 | Lowest of the RT group — processes events, but others can preempt it |

The Pi architecture diagram is here:

![Pi-side architecture](img/Doc%20-%20pi_architecture_doc.svg)

---

## The Linux PC side

The PC runs **two separate Python processes**, both started by `main.py` at the project root.

- **UI process** (`ui/ui_main.py`) — serves the web interface, drives the trial loop, writes to the database.
- **Acquisition process** (`acquisition/acquisition_main.py`) — receives video from all Pis over UDP, saves it to the NAS, indexes it in the database.

These two processes don't talk directly to each other. They share state through **Valkey** (for live flags and video streaming) and **PostgreSQL** (for permanent storage).

The PC architecture diagram is here:

![Linux-layer architecture](img/Doc%20-%20Linux%20Layer.svg)

---

## Key files on the PC

### Root level

**`main.py`** — the entry point. Starts the UI process and the Acquisition process as subprocesses.

**`config.py`** — all PC-side settings in one place: number of cages, ports, database connection string, NAS path, Valkey address, and timing constants. If you need to change a setting, this is almost always where to look.

---

### `acquisition/` — the video pipeline

**`acquisition_main.py`** — entry point for the Acquisition process. Creates one UDP listener and one frame writer per cage, and starts the watchdog.

**`udp_receiver.py`** — listens on a UDP port for incoming frames from a Pi. Uses two threads: one to receive packets as fast as possible, one to process them. This way a slow frame doesn't block incoming packets.

**`packet_parser.py`** — takes the raw bytes from a UDP packet and turns them into a usable Python object (`ParsedFrame`). Reads the 29-byte header, decodes the JSON events, and hands everything off.

**`frame_writer.py`** — decides what to do with each received frame. Always sends it to Valkey (for live streaming or snapshot). When recording is on, also writes it to a `.bin` file on the NAS and updates the chunk index in the database every 1000 frames.

**`watchdog.py`** — runs once per second, checks whether each cage is still sending frames. Writes a status string to Valkey for the UI to read. If a cage hasn't sent a frame in 10 seconds, it marks it as dead.

---

### `command/`

**`tcp_command_sender.py`** — manages the TCP connection to one Pi. `send()` sends a command and waits for an ACK. A background thread reads anything the Pi sends back and routes it: ACKs go to unblock `send()`, trial results and sync events go to `event_handler`.

---

### `shared/`

**`shared/logger.py`** — a helper to set up a logger that writes to stdout and optionally a log file. Used by all modules.

---

### `ui/` — the trial logic and web interface

**`ui_main.py`** — the Flask app. Registers all API endpoints, creates one `TCPCommandSender` and one `CageRunner` per cage at startup, and clears any leftover Valkey flags from a previous run.

**`cage_runner.py`** — the trial loop for one cage. During the gap between trials (ITI), it pre-computes the next trial (bias correction, side assignment, click generation). Then it sends the trial to the Pi and waits for the result. One instance per cage, runs permanently; the worker thread starts and stops per session. See [Cage Runner Flowchart](06_cage_runner_flowchart.md) for the full loop.

**`event_handler.py`** — called by the TCP reader thread when a trial result arrives from the Pi. Saves the result to the database, checks whether the animal should advance or fall back in the curriculum, and notifies the runner.

**`advancement.py`** — looks at recent trial results and decides whether the animal should advance to the next substage, fall back, or stay. `evaluate()` returns the decision; `apply()` writes it to the database.

**`bias_algorithms.py`** — three side-bias correction algorithms (`brody`, `ibl`, `rebalance`) plus a `none` option. Each takes recent trial history and returns a probability for the left side. See [Bias Algorithms](../reference/04_bias_algorithms.md).

**`click_generator.py`** — generates left and right click trains as lists of timestamps using a Poisson process. Uses a fixed random seed so any trial can be regenerated identically later.

---

### `ui/endpoints/` — all REST API routes

| File | What it handles |
|---|---|
| `session.py` | Opening and closing sessions, listing active sessions |
| `trial.py` | Starting/stopping the trial runner, reading advancement status |
| `stream.py` | Streaming on/off, recording on/off, live video WebSocket, camera status |
| `control.py` | Fan, LED strip, trial graph preview, NTP sync status |
| `curriculum.py` | Creating and editing training stages and substages |
| `subjects.py` | Creating and editing animal records |
| `metrics.py` | Performance charts on the dashboard |
| `export.py` | CSV download of trial data |
| `scoresheet.py` | Daily welfare scoresheet |
| `builder.py` | Trial JSON validator and preview |
| `dev.py` | Debug endpoints, not used in normal sessions |
