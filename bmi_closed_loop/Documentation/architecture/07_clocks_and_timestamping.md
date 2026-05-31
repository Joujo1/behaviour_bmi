# Clocks & Timestamping Policy

The system spans two physical machines (Pi and PC) with independent clocks. This document describes what clock each timestamp is derived from, how the clocks are kept in sync, and how to convert between timestamp domains.

---

## Clock sources

### Pi — `CLOCK_MONOTONIC`

All timing-critical timestamps on the Pi use `CLOCK_MONOTONIC`. This clock never jumps backwards and is not adjusted by NTP, making it safe for measuring durations. It is the basis for:

- Beam-break event timestamps (via `ev.timestamp_ns` from the gpiod kernel interrupt)
- Hardware output timestamps (read just after the GPIO pin changes)
- State transition timestamps (read in the FSM thread)
- `trial_start_us` — the FSM thread's `CLOCK_MONOTONIC` at the moment `_run()` starts, after reaching RT priority
- Frame timestamps in UDP packets

### Pi — `CLOCK_REALTIME`

Read once per trial alongside `trial_start_us`:

- `trial_start_real` — `CLOCK_REALTIME` seconds at the same instant as `trial_start_us`. Stored in `trial_results`. Provides a wall-clock anchor so CLOCK_MONOTONIC events can be mapped to absolute time in post-processing (`absolute_wall = trial_start_real + (event_t_mono_us - trial_start_us) / 1e6`).

### PC — wall clock (`NOW()`)

- `completed_at` in `trial_results` is `NOW()` on the PC — the approximate wall time the PC received the trial result over TCP. This is not a precision timestamp; network + processing latency mean it lags the true trial completion by tens of milliseconds.

---

## NTP synchronisation

The Pi runs `chrony` to synchronise its `CLOCK_REALTIME` to the PC (or an upstream NTP server). Every 5 seconds, the Pi's NTP reporter thread queries chrony and pushes a `sync_status` event over TCP:

```json
{ "event": "sync_status", "offset_ms": 0.3, "rms_offset_ms": 0.1, "received_at": 1717000000.5 }
```

`event_handler` writes this to Valkey key `cage:{id}:sync_status` with a 15-second TTL. The UI reads it via `GET /cage/{id}/sync` and displays a sync quality indicator. A missing key means the Pi has stopped reporting (disconnected or chrony failure).

NTP keeps `CLOCK_REALTIME` aligned across machines, but `CLOCK_MONOTONIC` is local and cannot be directly compared between Pi and PC. Cross-machine time alignment is done via `trial_start_real` (the shared wall-clock anchor).

---

## Event timestamp format

All FSM events stored in `trial_results.events` (JSONB) and in UDP packet event blobs use trial-relative time in seconds:

```
t = CLOCK_MONOTONIC_at_event - trial_start   (seconds, float)
```

`trial_start` is the `CLOCK_MONOTONIC` value captured at FSM thread startup. To convert back to absolute CLOCK_MONOTONIC:

```
absolute_us = trial_start_us + t * 1_000_000
```

To convert to wall time:

```
wall_time = trial_start_real + t
```

---

## Timestamp precision by event type

| Event type | Source | Precision | Notes |
|---|---|---|---|
| Beam break | Kernel GPIO interrupt (`ev.timestamp_ns`) | < 1 µs (hardware) | Kernel timestamps the IRQ before Python runs |
| Hardware output | FSM thread, after `actions.dispatch()` | ~10–100 µs | One Python call after pin change |
| State transition | FSM thread, at decision time | ~10–100 µs | Same thread as output, no extra delay |
| Frame timestamp | picamera2 PTS → CLOCK_MONOTONIC | ~1 frame period (16.7 ms at 60 fps) | Camera sensor clock, see note below |
| `trial_start_us` | FSM thread CLOCK_MONOTONIC at `_run()` entry | < 1 µs | After RT priority is set |
| `trial_start_real` | CLOCK_REALTIME at same instant | NTP accuracy (~1 ms typical) | Subject to NTP slew |
| `completed_at` | PC `NOW()` at TCP receipt | 10–100 ms | Network + processing latency |

**Frame timestamp note:** The picamera2 PTS represents the camera's capture time, converted to absolute CLOCK_MONOTONIC via an anchor computed on the first frame. Empirical verification is recommended by comparing the stored frame timestamp against the known CLOCK_MONOTONIC time of a GPIO event (e.g. an LED turn-on) that is visible in the frame image. See `bin_viewer.py` for tooling.

---

## Summary: which timestamp to use for what

| Use case | Field |
|---|---|
| Measure reaction time (beam break relative to stimulus) | `events[].t` |
| Align trials to wall clock | `trial_start_real + events[].t` |
| Seek into .bin video file by time | `trial_start_us + events[].t * 1e6` vs `chunk_start_ts` in `recordings` |
| Check clock sync quality | `cage:{id}:sync_status` in Valkey |
| Audit when the PC received a result | `trial_results.completed_at` |
