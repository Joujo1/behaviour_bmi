# Valkey Architecture

Valkey is a Redis-compatible in-memory store. Think of it as a shared whiteboard that both processes on the PC — the UI process and the Acquisition process — can read and write.

The two processes can't share Python variables directly because they're separate OS processes. Valkey is how they talk to each other without direct IPC.

The config for Valkey is in `bmi_closed_loop/config.py` (`VALKEY_HOST`, `VALKEY_PORT`).

---

## Flags set by the UI, read by Acquisition

These keys control what the Acquisition process does with incoming frames.

| Key | Values | Set by | Read by |
|---|---|---|---|
| `cage:{id}:streaming` | `"0"` / `"1"` | `ui/endpoints/stream.py` | `acquisition/frame_writer.py` |
| `cage:{id}:recording` | `"0"` / `"1"` | `ui/endpoints/stream.py` | `acquisition/frame_writer.py` |
| `cage:{id}:fan` | `"0"` / `"1"` | `ui/endpoints/control.py` | `ui/endpoints/stream.py` (peripherals endpoint) |
| `cage:{id}:strip` | `"0"` / `"1"` | `ui/endpoints/control.py` | `ui/endpoints/stream.py` (peripherals endpoint) |
| `cage:{id}:active_session` | JSON string or absent | `ui/endpoints/session.py` | Dashboard, session endpoints |

When `streaming = "1"`, `frame_writer.py` publishes each H.264 frame to the live stream channel instead of writing it to the snapshot key. When `recording = "1"`, it also writes to the NAS and database.

All five keys are reset to `"0"` (or deleted) every time `ui_main.py` starts up. This clears any stale state left over from a crash or previous run.

---

## Live data written by Acquisition or the event handler, read by the UI

These keys carry real-time information flowing from the Acquisition side back to the UI.

| Key | TTL | Written by | Read by | What it contains |
|---|---|---|---|---|
| `cage:{id}:latest_frame` | 5 s | `acquisition/frame_writer.py` | `GET /cage/{id}/frame` | The most recent JPEG frame — used for dashboard snapshots when not streaming live |
| `cage:{id}:sync_status` | 15 s | `ui/event_handler.py` | `GET /cage/{id}/sync` | NTP sync quality reported by the Pi — offset and RMS offset in ms |
| `cage:{id}:advancement` | 20 s | `ui/event_handler.py` | `GET /cage/{id}/advancement` | Most recent curriculum advancement — decision, new substage ID and label |

The TTL (time-to-live) on these keys means they automatically disappear if nobody writes them for a while. For example, if the Pi disconnects, `sync_status` will expire after 15 seconds and the UI will show "no sync data" instead of showing stale information.

`latest_frame` is only written when the frame is MJPEG. When H.264 streaming is active, frames go through the pub/sub channel below instead.

---

## Camera status — written by the Watchdog

| Key | Written by | Read by |
|---|---|---|
| `camera_status` | `acquisition/watchdog.py` every 1 second | `GET /cameras/status` |

This is a Valkey hash. Each field is `cage_{id}` and the value is a status string like `"alive|fps=60|drops=0|net_drops=0|streaming=1|recording=0"`.

The watchdog marks a cage as dead if it hasn't received a frame in 10 seconds (`WATCHDOG_DEAD_THRESHOLD_SECONDS` in `config.py`). The UI reads this to show the coloured status dots on the dashboard.

---

## The live video pub/sub channel

| Channel | Published by | Subscribed by |
|---|---|---|
| `cage:{id}:h264_stream` | `acquisition/frame_writer.py` | `ui/endpoints/stream.py` WebSocket handler |

This is how live video gets from the Acquisition process to the browser. The Acquisition process publishes one message per H.264 frame. The UI process's WebSocket handler is subscribed and forwards each message to the browser immediately.

Each message is: `[1 byte keyframe flag][8 bytes timestamp in µs][H.264 frame bytes]`. The WebSocket handler strips the 9-byte prefix before sending to the browser. The keyframe flag tells the browser's decoder when a new video segment starts.

This channel is only active when `cage:{id}:streaming == "1"`. When streaming is off, frames go to `latest_frame` instead.

---

## Startup cleanup

When `ui_main.py` starts, it runs this for every cage:

```python
valkey.set(f"cage:{cage_id}:streaming", "0")
valkey.set(f"cage:{cage_id}:recording", "0")
valkey.set(f"cage:{cage_id}:fan",       "0")
valkey.set(f"cage:{cage_id}:strip",     "0")
valkey.delete(f"cage:{cage_id}:active_session")
```

Without this, if the UI process crashed while recording was on, the Acquisition process would keep writing to the NAS forever after restart because it still sees `recording = "1"`.
