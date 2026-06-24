# Adding TCP Commands

The PC and each Pi maintain a persistent TCP connection. The PC sends newline-terminated command strings; the Pi responds with `ACK:message\n` or `ERROR:reason\n`. The Pi also sends unsolicited event lines (e.g. `trial_complete`) that the PC receives asynchronously.

The Pi-side handler is `handle_command()` in [RPi_main/main.py](../../RPi_main/main.py). The PC-side sender is `TCPCommandSender` in [command/tcp_command_sender.py](../../command/tcp_command_sender.py).

---

## Existing commands (PC → Pi)

| Command | What happens |
|---|---|
| `START_STREAMING` | Pi starts camera and begins sending UDP frames |
| `STOP_STREAMING` | Pi stops camera and UDP sender |
| `STOP_TRIAL` | Pi aborts the running trial |
| `FAN_ON` | Fan GPIO driven fully on |
| `FAN_OFF` | Fan GPIO driven off |
| `FAN_PWM:<duty>` | Fan software PWM set to `duty` percent (0–100) |
| `STRIP_ON` | Strip light GPIO driven on |
| `STRIP_OFF` | Strip light GPIO driven off |
| `{trial JSON}` | Any JSON string starts a new trial (fallthrough case) |

## Existing events (Pi → PC, unsolicited)

| Event | When sent |
|---|---|
| `{"event": "trial_complete", "outcome": "...", "trial_id": "...", "events": [...]}` | After every trial ends |

---

## How to add a new command

### Step 1 — Handle it in `handle_command()` on the Pi

Open [RPi_main/main.py](../../RPi_main/main.py) and add an `if` branch inside `handle_command()`. Add it before the `json.loads(command)` fallthrough line:

```python
if command == "MY_COMMAND":
    # do something with gpio_handler, current_engine, etc.
    gpio_handler.set_my_output(True)
    return True, "my command ok"

if command.startswith("MY_COMMAND:"):
    param = command.split(":", 1)[1]
    # ...
    return True, f"my command: {param}"
```

Return `(True, message)` for success, `(False, reason)` for failure. The receiver wraps these as `ACK:message\n` or `ERROR:reason\n`.

### Step 2 — Call it from the PC

Wherever you need to send the command from the PC (typically a Flask endpoint), get the `TCPCommandSender` for the relevant cage and call `send()`:

```python
sender = current_app.cage_runners[cage_id]._sender  # or however the sender is exposed
ok, msg = sender.send("MY_COMMAND")
if not ok:
    return jsonify({"ok": False, "msg": msg}), 500
return jsonify({"ok": True})
```

`send()` blocks until it receives `ACK` or `ERROR` (5-second timeout) and returns `(bool, str)`.

---

## How to add a new Pi → PC push event

To push an unsolicited event from the Pi to the PC, call `receiver.push()` inside `main.py`. `receiver` is the `TCPCommandReceiver` instance:

```python
import json
receiver.push(json.dumps({"event": "my_event", "value": 42}))
```

On the PC side, `TCPCommandSender._dispatch()` receives the line. If it does not start with `ACK:` or `ERROR:`, it calls the `on_event` callback registered at construction time. The callback receives `(cage_id, event_dict)`. Add handling for your new event key in that callback.
