"""
GPIO hardware abstraction layer.

All pin numbers and all RPi.GPIO calls are confined to this module.
Engine and actions interact with hardware exclusively through the functions here.

All beam sensors are monitored continuously for the entire trial with both
entry and exit edges.

Audio is GPIO-based: a brief HIGH pulse on an AUDIO_PIN drives the PAM8302
amplifier input directly, producing an audible click.
"""

import logging
import threading

logger = logging.getLogger(__name__)

import RPi.GPIO as _GPIO



from config import (
    LED_PINS, VALVE_PINS, BEAM_PINS, AUDIO_PINS,
    BEAM_ACTIVE_LOW, BEAM_DEBOUNCE_MS,
    FAN_PIN, STRIP_PIN, FAN_PWM_FREQ,
)

# Internal output-state tracking
_output_state: dict[int, bool] = {}
_output_lock = threading.Lock()

# Fan PWM state (None when in simple on/off mode)
_fan_pwm: "object | None" = None   # _GPIO.PWM instance
_fan_pwm_lock = threading.Lock()
_fan_pwm_duty: float = 0.0         # last set duty cycle (0–100)


def _drive(pin: int, state: bool) -> None:
    """Write a digital value to an output pin and record the new state."""
    _GPIO.output(pin, _GPIO.HIGH if state else _GPIO.LOW)
    with _output_lock:
        _output_state[pin] = state


def setup() -> None:
    """Configure all GPIO pins; must be called once at process start."""
    _GPIO.setmode(_GPIO.BCM)
    _GPIO.setwarnings(False)

    for pin in LED_PINS.values():
        _GPIO.setup(pin, _GPIO.OUT, initial=_GPIO.LOW)
    for pin in VALVE_PINS.values():
        _GPIO.setup(pin, _GPIO.OUT, initial=_GPIO.LOW)
    for pin in AUDIO_PINS.values():
        _GPIO.setup(pin, _GPIO.OUT, initial=_GPIO.LOW)
    _GPIO.setup(FAN_PIN,   _GPIO.OUT, initial=_GPIO.LOW)
    _GPIO.setup(STRIP_PIN, _GPIO.OUT, initial=_GPIO.LOW)

    for target, pin in BEAM_PINS.items():
        pull = _GPIO.PUD_UP if BEAM_ACTIVE_LOW[target] else _GPIO.PUD_DOWN
        _GPIO.setup(pin, _GPIO.IN, pull_up_down=pull)

    all_output_pins = (list(LED_PINS.values()) + list(VALVE_PINS.values()) +
                       list(AUDIO_PINS.values()) + [FAN_PIN, STRIP_PIN])
    with _output_lock:
        for pin in all_output_pins:
            _output_state[pin] = False

    logger.info("GPIO setup complete")


def cleanup() -> None:
    """Run safety sweep and release all GPIO resources; call on shutdown."""
    safety_sweep()
    _GPIO.cleanup()
    logger.info("GPIO cleaned up")


def set_led(target: str, state: bool) -> None:
    """Drive an indicator LED on or off."""
    _drive(LED_PINS[target], state)


def set_valve(target: str, state: bool) -> None:
    """Open or close a reward delivery valve."""
    _drive(VALVE_PINS[target], state)


def set_audio(target: str, state: bool) -> None:
    """Drive an audio output pin high or low; a brief pulse produces a click."""
    _drive(AUDIO_PINS[target], state)


def _stop_fan_pwm() -> None:
    """Stop PWM on FAN_PIN if active. Must be called with _fan_pwm_lock held."""
    global _fan_pwm, _fan_pwm_duty
    if _fan_pwm is not None:
        _fan_pwm.stop()
        _fan_pwm      = None
        _fan_pwm_duty = 0.0


def set_fan(state: bool) -> None:
    """Drive fan fully on or off (binary). Stops any active PWM first."""
    global _fan_pwm
    with _fan_pwm_lock:
        _stop_fan_pwm()
    _drive(FAN_PIN, state)


def set_fan_pwm(duty: float, freq: float = FAN_PWM_FREQ) -> None:
    """
    Control fan speed via PWM on the SSR gate signal.

    duty : 0.0 – 100.0  (percent of full speed).
             0   → fan off (falls back to set_fan(False)).
             100 → fan fully on (falls back to set_fan(True)).
    freq : PWM frequency in Hz (default 25 Hz).
           Check your SSR datasheet — most DC SSRs handle up to a few kHz;
           AC zero-crossing SSRs are limited to ~100 Hz.

    If the relay turns out to be mechanical, call set_fan() instead and do
    not use this function — rapid switching will destroy the relay contacts.
    """
    global _fan_pwm, _fan_pwm_duty
    duty = max(0.0, min(100.0, float(duty)))

    if duty == 0.0:
        set_fan(False)
        return
    if duty >= 100.0:
        set_fan(True)
        return

    with _fan_pwm_lock:
        if _fan_pwm is None:
            _fan_pwm = _GPIO.PWM(FAN_PIN, freq)
            _fan_pwm.start(duty)
        else:
            _fan_pwm.ChangeFrequency(freq)
            _fan_pwm.ChangeDutyCycle(duty)
        _fan_pwm_duty = duty

    # Mark pin as active in the output tracker
    with _output_lock:
        _output_state[FAN_PIN] = True

    logger.debug("Fan PWM: duty=%.1f%% freq=%.1fHz", duty, freq)


def get_fan_pwm_duty() -> float:
    """Return the current PWM duty cycle (0 if off or in binary mode)."""
    with _fan_pwm_lock:
        return _fan_pwm_duty


def set_strip(state: bool) -> None:
    _drive(STRIP_PIN, state)


def safety_sweep() -> None:
    """Force all outputs off; called on trial abort, watchdog, or shutdown."""
    for target in LED_PINS:
        set_led(target, False)
    for target in VALVE_PINS:
        set_valve(target, False)
    for target in AUDIO_PINS:
        set_audio(target, False)
    set_fan(False)   # set_fan() stops PWM then drives pin low
    set_strip(False)
    logger.info("Safety sweep complete")



def _read_active(target: str, pin: int) -> bool:
    """Return the normalised logical state of a beam sensor (True = beam broken)."""
    raw = _GPIO.input(pin)
    return (raw == _GPIO.LOW) if BEAM_ACTIVE_LOW[target] else (raw == _GPIO.HIGH)


def start_monitoring(on_event) -> None:
    """
    Begin monitoring all IR sensors for the duration of a trial.
    """
    for target, pin in BEAM_PINS.items():
        try:
            _GPIO.remove_event_detect(pin)
        except Exception:
            pass

        def _handler(_, t: str = target, p: int = pin) -> None:
            on_event(t, _read_active(t, p))

        _GPIO.add_event_detect(pin, _GPIO.BOTH,
                               callback=_handler,
                               bouncetime=BEAM_DEBOUNCE_MS)

    logger.info("Beam monitoring started")


def stop_monitoring() -> None:
    """Remove all IR event detection; called at trial end."""
    for pin in BEAM_PINS.values():
        try:
            _GPIO.remove_event_detect(pin)
        except Exception:
            pass
    logger.info("Beam monitoring stopped")


def get_snapshot() -> dict:
    """
    Return the current binary state of all hardware as a flat dict.
    For output pins both sources are included so they can be compared:
      *_tracked  — internal _output_state dict (what we wrote)
      *_readback — GPIO.input() on the output pin (what the hardware reports)
    """
    snapshot = {}

    for target, pin in BEAM_PINS.items():
        raw    = _GPIO.input(pin)
        active = (raw == _GPIO.LOW) if BEAM_ACTIVE_LOW[target] else (raw == _GPIO.HIGH)
        snapshot[f"beam_{target}"] = int(active)

    all_output_pins = {
        "led":   LED_PINS,
        "valve": VALVE_PINS,
        "audio": AUDIO_PINS,
    }
    with _output_lock:
        for prefix, pins in all_output_pins.items():
            for target, pin in pins.items():
                tracked  = int(_output_state.get(pin, False))
                readback = int(_GPIO.input(pin) == _GPIO.HIGH)
                snapshot[f"{prefix}_{target}_tracked"]  = tracked
                snapshot[f"{prefix}_{target}_readback"] = readback
                if tracked != readback:
                    logger.warning(
                        "Output state mismatch on %s_%s (pin %d): tracked=%d readback=%d",
                        prefix, target, pin, tracked, readback,
                    )

    snapshot["fan_pwm_duty"] = get_fan_pwm_duty()
    return snapshot
