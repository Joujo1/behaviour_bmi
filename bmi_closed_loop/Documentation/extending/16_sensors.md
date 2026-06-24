# Adding Sensors

Beam-break sensors are the only input sensors in the current system. All beam sensor configuration lives in [RPi_main/config.py](../../RPi_main/config.py), and all GPIO monitoring is handled by [RPi_main/gpio_handler.py](../../RPi_main/gpio_handler.py).

---

## How beam sensors work

### Hardware

Each beam-break sensor has an IR emitter and a detector. When the beam is broken (rat's paw passes through), the GPIO input pin changes state. The sensors are wired as active-low (the pin is pulled up and falls on break) or active-high depending on the sensor module used — this is captured in `BEAM_ACTIVE_LOW`.

### Software

`gpio_handler.start_monitoring()` opens all pins in `BEAM_PINS` with gpiod v2 edge detection (`BOTH` edges) and starts a persistent monitor thread. That thread blocks on `select()` and wakes up immediately on a kernel GPIO interrupt. For each edge event:

1. It maps the raw BCM pin number to a sensor name using `_pin_to_target`.
2. It converts `RISING_EDGE`/`FALLING_EDGE` to `is_active: bool` using `BEAM_ACTIVE_LOW`.
3. It calls `_on_event_fn(target, is_active, t_mono)`, where `t_mono` is the kernel interrupt timestamp in `CLOCK_MONOTONIC` seconds.

The per-trial callback is swapped via `update_callbacks()` at the start of each trial and set to `None` between trials (events are silently dropped during ITI).

### Current beam sensor config

```python
BEAM_PINS = {
    "left":   2,
    "center": 3,
    "right":  4,
}
BEAM_ACTIVE_LOW = {
    "left":   True,
    "center": True,
    "right":  True,
}
```

---

## How to add a new sensor

### Step 1 — Wire the hardware

Connect the sensor's output to an unused BCM GPIO input pin on the Pi 40-pin header. Note the BCM pin number. Connect power (3.3 V or 5 V depending on the sensor module) and ground from the header.

### Step 2 — Add the pin to `config.py`

Open [RPi_main/config.py](../../RPi_main/config.py) and add your sensor to `BEAM_PINS` and `BEAM_ACTIVE_LOW`:

```python
BEAM_PINS = {
    "left":   2,
    "center": 3,
    "right":  4,
    "nose":   17,   # new sensor
}
BEAM_ACTIVE_LOW = {
    "left":   True,
    "center": True,
    "right":  True,
    "nose":   True,   # True = pulled high, breaks to low
}
```

### Step 3 — Restart the Pi service

`gpio_handler.start_monitoring()` is called once at startup with all pins from `BEAM_PINS`. Restart the service to pick up the new pin:

```bash
sudo systemctl restart pi_bmi_rig
```

### Step 4 — Use the sensor in trial definitions

Once the sensor is registered, events for `"nose"` will flow through the engine the same way as `"left"`, `"right"`, and `"center"`. Use the sensor name in trial definition transitions:

```json
{ "trigger": "beam_break", "target": "nose", "next_state": "reward" }
```

The sensor name in `target` must exactly match the key in `BEAM_PINS`.

### Step 5 — Add to the UDP header snapshot (optional)

The current UDP packet header includes the state of `beam_left`, `beam_right`, and `beam_center` as per-frame snapshots. If you want your new sensor's state in every frame header, add it to the `gpio` dict passed to `UDPSender._pack_and_send()` in [RPi_main/streamer.py](../../RPi_main/streamer.py), update `HEADER_FORMAT` in [RPi_main/udp_sender_pi.py](../../RPi_main/udp_sender_pi.py), and mirror the change in [acquisition/packet_parser.py](../../acquisition/packet_parser.py). This is a breaking wire-format change — see [06_udp_events.md](06_udp_events.md).

---

## Real-time scheduling note

The GPIO monitor thread runs at `SCHED_FIFO` priority 75 and is pinned to CPU core 3. It preempts the FSM (priority 70) and the click trigger thread (priority 85 preempts it during click playback). No changes to scheduling are needed when adding a sensor.
