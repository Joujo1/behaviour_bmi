# TCP Commands

The PC maintains one persistent TCP connection per cage Pi. All messages are newline-terminated UTF-8 strings. The Pi responds to every command with either `ACK:message\n` or `ERROR:reason\n`.

Source: [RPi_main/tcp_command_receiver.py](../../RPi_main/tcp_command_receiver.py) (Pi server), [RPi_main/main.py](../../RPi_main/main.py) (`handle_command`), [command/tcp_command_sender.py](../../command/tcp_command_sender.py) (PC client).

---

## PC → Pi commands

| Command | Response | What happens |
|---|---|---|
| `START_STREAMING` | `ACK:ok` | Pi starts the camera and begins sending UDP frames to the PC. Fails with `ERROR` if already streaming or if the PC IP is not yet known. |
| `STOP_STREAMING` | `ACK:ok` | Pi stops the camera and UDP sender. |
| `STOP_TRIAL` | `ACK:trial stopped` | Pi aborts the running trial immediately. Fails with `ERROR` if no trial is running. |
| `FAN_ON` | `ACK:fan on` | Fan GPIO driven fully on. |
| `FAN_OFF` | `ACK:fan off` | Fan GPIO driven off. |
| `FAN_PWM:<duty>` | `ACK:fan pwm N%` | Fan software PWM set to `duty` percent (0–100 float). |
| `STRIP_ON` | `ACK:strip on` | Strip light GPIO driven on. |
| `STRIP_OFF` | `ACK:strip off` | Strip light GPIO driven off. |
| `{trial JSON}` | `ACK:ok` | Any JSON string starts a new trial. If a trial is already running it is stopped first. Returns `ERROR` on JSON parse failure or invalid trial definition. |

---

## Pi → PC events (unsolicited)

The Pi pushes one-way event messages to the PC without a prior command. These arrive on the same TCP connection as ACK/ERROR responses. The PC reader thread classifies lines: anything that does not start with `ACK:` or `ERROR:` is dispatched to the `on_event` callback as a parsed JSON dict.

| Event JSON | When sent |
|---|---|
| `{"event": "trial_complete", "trial_id": "...", "outcome": "correct"\|"wrong", "events": [...], "trial_start_us": N, "trial_start_real": F}` | After a trial ends with a non-aborted outcome. |
| `{"event": "trial_aborted",  "trial_id": "...", "outcome": "aborted",         "events": [...], "trial_start_us": N, "trial_start_real": F}` | After a trial is aborted (e.g. via `STOP_TRIAL`). |

`events` is the full list of FSM events collected during the trial. `trial_start_us` is the Pi's `CLOCK_MONOTONIC` timestamp in microseconds at trial start; `trial_start_real` is the corresponding wall-clock time as a float. Both fields are always present.

---

## Protocol details

- The TCP port is `TCP_COMMAND_PORT = 6000` (defined in [bmi_closed_loop/config.py](../../config.py)).
- The Pi accepts exactly one connection at a time. If the PC reconnects, the previous connection is closed.
- `TCPCommandSender.send()` on the PC blocks for up to 5 seconds waiting for `ACK`/`ERROR`. It returns `(True, message)` or `(False, reason)`.
- The connection is lazily established on the first `send()` call and automatically reconnected if the socket is lost.
- The Pi's reader thread runs at `SCHED_OTHER` priority — TCP handling does not contend with the real-time FSM or GPIO threads.

---

## UDP stream port

The UDP stream is separate from TCP. Each cage's UDP port is `UDP_BASE_PORT + cage_id` (default: cage 1 → port 5001, cage 12 → port 5012). The Pi learns the PC's IP address from the first TCP connection and sends UDP frames to that IP.
