# Valkey Architecture

Valkey is used as a RAM-speed shared state bus between the UI process and the Acquisition process, and as the pub/sub backbone for the live H.264 video stream. There is no direct IPC between the two processes — all cross-process communication goes through Valkey.

---

## Key inventory

### Per-cage flags (set by UI, read by Acquisition)

| Key | Type | Values | Set by | Read by |
|---|---|---|---|---|
| `cage:{id}:streaming` | string | `"0"` / `"1"` | `stream.py` endpoints | `frame_writer.py` (PUBLISH vs SET path) |
| `cage:{id}:recording` | string | `"0"` / `"1"` | `stream.py` endpoints | `frame_writer.py` (NAS + Postgres write gate) |
| `cage:{id}:fan` | string | `"0"` / `"1"` | `control.py` | `cameras/peripherals` endpoint |
| `cage:{id}:strip` | string | `"0"` / `"1"` | `control.py` | `cameras/peripherals` endpoint |
| `cage:{id}:active_session` | string (JSON) | session object or absent | `session.py` on open/close | dashboard, session endpoints |

All five are cleared to `"0"` (or deleted) by `ui_main.py` at startup to discard stale state from a previous server run.

### Per-cage live data (set by Acquisition or event_handler, read by UI)

| Key | Type | TTL | Written by | Read by |
|---|---|---|---|---|
| `cage:{id}:latest_frame` | bytes (JPEG) | 5 s | `frame_writer._write_valkey` | `GET /cage/{id}/frame` |
| `cage:{id}:sync_status` | string (JSON) | 15 s | `event_handler` | `GET /cage/{id}/sync` |
| `cage:{id}:advancement` | string (JSON) | 20 s | `event_handler` | `GET /cage/{id}/advancement` |

`latest_frame` is only written when the frame is MJPEG (magic bytes `0xFF 0xD8`). When streaming is active and frames are H.264, `latest_frame` is not updated — the live path uses the pub/sub channel instead.

`sync_status` carries the NTP offset reported by chrony on the Pi every 5 s. The 15-second TTL means the key expires if the Pi stops reporting (e.g. disconnected), so the UI can distinguish "in sync" from "no data".

`advancement` carries the most recent automatic curriculum change: `{decision, new_id, new_label, ts}`. The 20-second TTL is long enough for the browser to pick it up on the next poll cycle.

### Camera status (set by Acquisition Watchdog, read by UI)

| Key | Type | Written by | Read by |
|---|---|---|---|
| `camera_status` | hash | `watchdog.py` every 1 s | `GET /cameras/status` |

Each field in the hash is `cage_{id}` → `"alive|fps=N|drops=N|net_drops=N|streaming=N|recording=N"`. A cage is considered dead if its `last_seen` timestamp in the Watchdog's internal stats is older than `WATCHDOG_DEAD_THRESHOLD_SECONDS = 10`.

---

## Pub/sub channel

| Channel | Published by | Subscribed by |
|---|---|---|
| `cage:{id}:h264_stream` | `frame_writer._write_valkey` | WebSocket handler (`stream.py`) |

This is the real-time cross-process data path. The Acquisition process publishes one message per H.264 frame; the UI process's WebSocket handler subscribes and forwards each message to the browser.

Message format: `[1 byte keyframe flag][8 bytes LE timestamp µs][H.264 Annex-B NAL bytes]`. The 9-byte prefix is stripped by the WebSocket handler before sending to the browser.

The channel is only active when `cage:{id}:streaming == "1"`. When streaming is off, `frame_writer` writes to `latest_frame` instead.

---

## Lifetime and startup behaviour

On `ui_main.py` startup, the following keys are reset for every cage:

```python
valkey.set(f"cage:{cage_id}:streaming", "0")
valkey.set(f"cage:{cage_id}:recording", "0")
valkey.set(f"cage:{cage_id}:fan",       "0")
valkey.set(f"cage:{cage_id}:strip",     "0")
valkey.delete(f"cage:{cage_id}:active_session")
```

This prevents stale flags from a crashed or stopped UI process from leaving Acquisition in a recording state indefinitely.

TTL-bearing keys (`latest_frame`, `sync_status`, `advancement`) self-expire without any explicit cleanup.
