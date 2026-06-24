# Adding Events to UDP Sender

Each UDP packet sent from the Pi carries a JSON array of events that happened during that camera frame. The array is embedded between the binary header and the H264 frame bytes. This document explains what events exist and how to add new ones.

For the full packet wire format, see [reference/02_udp_packet_format.md](../reference/02_udp_packet_format.md).

---

## The three existing event shapes

All events share a `"t"` key: elapsed seconds since `trial_start`, measured by `CLOCK_MONOTONIC` on the Pi.

### Beam event

Emitted every time a beam-break sensor changes state.

```json
{"t": 1.234, "sensor": "center", "active": true}
```

| Key | Type | Values |
|---|---|---|
| `t` | float | seconds since trial start |
| `sensor` | string | `"left"`, `"right"`, `"center"` |
| `active` | bool | `true` = beam broken, `false` = beam cleared |

### State transition event

Emitted when the FSM moves from one state to another.

```json
{"t": 1.450, "from": "stimulus", "to": "choice"}
```

| Key | Type | Values |
|---|---|---|
| `t` | float | seconds since trial start |
| `from` | string | the state that was just left |
| `to` | string | the state being entered |

### Output event

Emitted when a hardware output (LED, valve) turns on or off.

```json
{"t": 0.012, "output": "led_left", "active": true}
```

| Key | Type | Values |
|---|---|---|
| `t` | float | seconds since trial start |
| `output` | string | name of the output (e.g. `"led_left"`, `"valve_right"`) |
| `active` | bool | `true` = turned on, `false` = turned off |

---

## Where events are created

All three event types are appended to `self._event_buffer` inside the trial engine on the Pi: [RPi_main/engine.py](../../RPi_main/engine.py).

| Event type | Location in engine.py |
|---|---|
| Beam | `_on_beam_event()` — around line 283 |
| Transition | `_transition_to()` — around line 404 |
| Output | `_log_output_event()` — around line 431 |

The buffer is drained each frame by `pop_frame_events()` and handed to the UDP sender, which serialises the list to JSON and packs it into the packet.

---

## How to add a new event type

### Step 1 — Append to `_event_buffer` in engine.py

Find the place in [RPi_main/engine.py](../../RPi_main/engine.py) where the event naturally occurs and append a dict:

```python
entry = {"t": time.monotonic() - self._trial_start, "my_event": "some_value"}
self._event_buffer.append(entry)
```

The dict can have any keys you need beyond `"t"`. There is no schema to register — the JSON array accepts arbitrary dicts.

### Step 2 — Handle the event on the PC side

The PC receives and parses events in [acquisition/packet_parser.py](../../acquisition/packet_parser.py). The `ParsedFrame.events` field is a plain Python list of dicts — your new event dict will appear there automatically once step 1 is done. No parser change is needed.

If you want to store the new event in the database, update the event writer in [acquisition/frame_writer.py](../../acquisition/frame_writer.py) to recognise your new `"my_event"` key and insert the appropriate row. See [architecture/03_trial_events_database_flow.md](../architecture/03_trial_events_database_flow.md) for how events flow from packets to the database.

### Step 3 — Add to the UDP header (only if you need per-frame state, not event-based)

If you need to stream a GPIO pin state on every frame rather than as a discrete event, you must modify the binary header itself. This requires changes in three places:

1. `_pack_and_send()` in [RPi_main/udp_sender_pi.py](../../RPi_main/udp_sender_pi.py) — add the field to the `struct.pack` call and update `HEADER_FORMAT`.
2. `HEADER_FORMAT` and `ParsedFrame` in [acquisition/packet_parser.py](../../acquisition/packet_parser.py) — mirror the change.
3. Any downstream code that reads the header fields.

This is a breaking wire-format change — both the Pi and the PC must be updated together.
