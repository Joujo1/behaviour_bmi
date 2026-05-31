# Clocks & Timestamping

The Pi and the PC are separate machines with separate clocks. This page explains which clock each timestamp comes from, why it matters, and how to convert between them.

---

## The two clocks on the Pi

The Pi uses two different clocks for different purposes:

**`CLOCK_MONOTONIC`** — counts time since boot, in microseconds. It never jumps backwards and is not affected by NTP corrections. This is the right clock for measuring durations and timing events within a trial. All FSM events, beam breaks, hardware outputs, and frame timestamps use this clock.

**`CLOCK_REALTIME`** — the wall clock. This is set by NTP and can jump if the clock gets corrected. Not good for measuring durations, but useful for anchoring data to a real-world time.

---

## What each timestamp is and where it's stored

| Timestamp | Clock | Where stored | What it's for |
|---|---|---|---|
| `t` in FSM events | `CLOCK_MONOTONIC`, trial-relative seconds | `trial_results.events` (JSONB) | Reaction times, event ordering within a trial |
| `trial_start_us` | `CLOCK_MONOTONIC` in µs, at FSM thread start | `trial_results.trial_start_us` | Anchor to convert `t` to absolute monotonic time |
| `trial_start_real` | `CLOCK_REALTIME` in seconds, at same instant as `trial_start_us` | `trial_results.trial_start_real` | Anchor to convert `t` to wall-clock time |
| `completed_at` | `NOW()` on the PC | `trial_results.completed_at` | Rough wall time of when the PC received the result — not a precision timestamp |
| Frame timestamp | `CLOCK_MONOTONIC` in µs | UDP packet header, `recordings` chunk index | Seeking into `.bin` video files by time |

---

## How to convert timestamps

**Event time → absolute monotonic time on the Pi:**
```
absolute_us = trial_start_us + t * 1_000_000
```

**Event time → wall-clock time:**
```
wall_time = trial_start_real + t
```

For example, if a beam break happened at `t = 0.841` seconds, and `trial_start_real = 1717000000.0`, then the beam break happened at wall time `1717000000.841`.

**Seeking into a `.bin` video file by event time:**

1. Calculate `absolute_us = trial_start_us + t * 1_000_000`.
2. Find the `recordings` row where `chunk_start_ts <= absolute_us <= chunk_end_ts`.
3. Seek to `chunk_byte_offset` in the file and scan forward frame by frame.

`bin_viewer.py` in `bmi_closed_loop/docs/` has tooling that does this.

---

## How well does timing work?

| Event type | Precision | Why |
|---|---|---|
| Beam break | < 1 µs | The Linux kernel timestamps the GPIO interrupt before Python even runs |
| Hardware output (LED, valve) | ~10–100 µs | Stamped just after the GPIO pin changes |
| State transition | ~10–100 µs | Stamped in the FSM thread at decision time |
| Frame timestamp | ~1 frame (16.7 ms at 60 fps) | Converted from camera sensor PTS |
| `trial_start_us` | < 1 µs | Captured after the thread has reached RT priority |
| `trial_start_real` | ~1 ms | Limited by NTP accuracy |
| `completed_at` | 10–100 ms | Includes network latency and PC processing time |

---

## NTP clock sync between Pi and PC

The Pi runs `chrony` to keep its `CLOCK_REALTIME` close to the PC's clock. Every 5 seconds, the Pi's NTP reporter thread checks the sync status and sends it to the PC over TCP:

```json
{ "event": "sync_status", "offset_ms": 0.3, "rms_offset_ms": 0.1, "received_at": 1717000000.5 }
```

`event_handler.py` saves this to Valkey key `cage:{id}:sync_status` with a 15-second TTL. The dashboard reads it via `GET /cage/{id}/sync` and shows a sync quality indicator.

If the key expires (no data for 15 seconds), the Pi is probably disconnected or chrony has stopped. `CLOCK_MONOTONIC` itself is not affected by NTP and remains usable either way — it's only the wall-clock anchor (`trial_start_real`) that degrades if clocks drift apart.

---

## Which timestamp to use for what

| Task | Field to use |
|---|---|
| Measure reaction time (beam break after stimulus onset) | `events[].t` |
| Place a trial on a wall-clock timeline | `trial_start_real + events[].t` |
| Seek to a frame in the `.bin` video file | `trial_start_us + events[].t * 1e6` vs `chunk_start_ts` in `recordings` |
| Check clock sync quality | `cage:{id}:sync_status` in Valkey |
| Know roughly when the PC got a trial result | `trial_results.completed_at` |
