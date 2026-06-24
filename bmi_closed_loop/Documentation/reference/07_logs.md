# Logs

There are two logging systems: **Pi-side** logs go to the systemd journal, and **PC-side** logs go to rotating log files on the PC.

---

## Pi-side logs (systemd journal)

All output from `cage_controller.service` (stdout and stderr) is captured by systemd and readable via `journalctl`.

```bash
# Stream live logs for one cage
journalctl -u cage_controller.service -f

# Show the last 200 lines
journalctl -u cage_controller.service -n 200

# Show logs since a specific time
journalctl -u cage_controller.service --since "2026-06-15 09:00"
```

The Pi logs use the format:
```
YYYY-MM-DD HH:MM:SS [module.name] LEVEL: message
```

---

## PC-side logs (files)

PC-side loggers are created by `get_logger(name, log_dir, level)` in [shared/logger.py](../../shared/logger.py). Each logger writes to:

```
<LOGGING_DIR>/<name>.log
```

`LOGGING_DIR` defaults to `/home/sentinel/Desktop/bmi/behaviour_bmi/bmi_closed_loop/logs` and can be overridden with the `BMI_LOG_DIR` environment variable (set in `bmi_closed_loop/config.py`).

`LOGGING_LEVEL` is `"INFO"` by default, also in `config.py`.

### Log files created at runtime

| File | Written by | Contents |
|---|---|---|
| `writer.cage1.log` … `writer.cage12.log` | `FrameWriter` (per cage) | Frame write statistics, chunk flushes, Postgres errors |
| `acquisition.log` | UDP receiver | Frame drop counts, packet parse errors |
| `ui.log` | Flask app | HTTP request errors, session open/close lifecycle |
| `cage_runner.log` | `CageRunner` | Trial dispatch, bias algorithm calls, advancement decisions |

Log file names come from the `name` argument passed to `get_logger()`. Each module uses `logging.getLogger(__name__)` for standard Python logging and `get_logger(...)` for file-backed loggers where file output is needed.

---

## Log format

Both Pi and PC logs use the same format:

```
2026-06-15 09:32:14 [acquisition.cage1] INFO: Frame drop detected: seq gap 3 (expected 1042, got 1045)
2026-06-15 09:32:14 [writer.cage1] WARNING: Postgres flush failed: connection timed out
```

---

## Log levels

| Level | When used |
|---|---|
| `DEBUG` | Per-event detail (individual frames, GPIO edges). Not logged at default `INFO` level. |
| `INFO` | Lifecycle events: service start/stop, session open/close, trial start/end, stream start/stop. |
| `WARNING` | Unexpected but recoverable: frame drops, hold timer cancelled, GPIO mismatch. |
| `ERROR` | Needs operator attention: Postgres write failure, UDP send error, camera lost. |

To enable `DEBUG` logging temporarily, change `LOGGING_LEVEL = "DEBUG"` in `bmi_closed_loop/config.py` and restart the PC process. On the Pi, `DEBUG` output goes to the journal — it can produce high volume at 60 fps.
