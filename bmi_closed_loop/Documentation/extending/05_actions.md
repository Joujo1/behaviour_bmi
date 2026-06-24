# Adding Actions

Actions are the outputs the trial state machine can trigger — opening a valve, turning on an LED, firing a click sequence. All actions are registered in one dictionary in [bmi_closed_loop/RPi_main/actions.py](../../RPi_main/actions.py).

---

## The four existing actions

| Key | What it does |
|---|---|
| `led_on` | Drives a GPIO LED pin high. Accepts a `target` key (`"left"`, `"right"`, `"center"`, or symbolic sides). |
| `led_off` | Drives a GPIO LED pin low. Same `target` key as `led_on`. |
| `valve_open` | Opens a solenoid valve to deliver water reward. Accepts `target` (`"left"` or `"right"`). |
| `play_clicks` | Fires a series of 50 µs TTL pulses to the ItsyBitsy audio MCU. Accepts `left_clicks` and `right_clicks` (lists of absolute timestamps in seconds). |

---

## How dispatch works

`dispatch(action_dict, on_complete, log_cb, latency_cb)` in `actions.py`:

1. Pops the `"type"` key from `action_dict`.
2. Looks up the function in `ACTIONS`.
3. Calls the function with the remaining keys as keyword arguments.
4. Calls `on_complete()` when the action finishes (used by the engine to log the output event).

`safety_sweep()` (also in `actions.py`) drives all LEDs and valves to off and is called at the end of every trial to ensure hardware outputs are clean.

---

## How to add a new action — step by step

### Step 1 — Write the function and add it to `ACTIONS`

Add a private function in `actions.py` and register it:

```python
def _puff_air(target: str, duration_ms: float) -> None:
    """Fire the air puff solenoid for `duration_ms` milliseconds."""
    pin = AIR_PINS[target]
    # ... GPIO logic ...

ACTIONS: dict = {
    "led_on":      _led_on,
    "led_off":     _led_off,
    "valve_open":  _valve_open,
    "play_clicks": _fire_click_triggers,
    "puff_air":    _puff_air,        # new
}
```

Add any new pin constants to [RPi_main/config.py](../../RPi_main/config.py).

### Step 2 — Update `safety_sweep()`

If your new action controls a hardware output that needs to be driven low at the end of a trial, add it to `safety_sweep()`:

```python
def safety_sweep() -> None:
    """Drive all hardware outputs to their safe (off) state."""
    for pin in LED_PINS.values():
        gpiod_line_set_value(pin, 0)
    for pin in VALVE_PINS.values():
        gpiod_line_set_value(pin, 0)
    for pin in AIR_PINS.values():       # new
        gpiod_line_set_value(pin, 0)    # new
```

### Step 3 — Log the output event in `engine.py`

Open [RPi_main/engine.py](../../RPi_main/engine.py) and find `_dispatch_action()`. Add an `elif` branch so the engine records your action in the event stream:

```python
elif action_type == "puff_air":
    self._log_output("puff_air", True)
    dispatch(action_dict, on_complete=lambda: self._log_output("puff_air", False), ...)
```

Without this, the action still works but will not appear in the stored trial events.

### Step 4 — Add the type to the curriculum builder UI

Open [ui/templates/curriculum.html](../../ui/templates/curriculum.html) and find line 417:

```javascript
const ACTION_TYPES = ['led_on','led_off','valve_open','play_clicks'];
```

Add your new type:

```javascript
const ACTION_TYPES = ['led_on','led_off','valve_open','play_clicks','puff_air'];
```

This makes `"puff_air"` appear in the action type dropdown when building a trial definition. If your action takes parameters other than `target`, also update the `extraFields` block in `renderStateCard()` (around line 840) to render the correct input fields for those parameters.

---

## Where actions come from at runtime

The trial definition JSON lists actions under `entry_actions` and `exit_actions` for each state. The engine reads those lists and calls `dispatch()` for each one. The `"type"` key is how `dispatch()` looks up the function in `ACTIONS`.
