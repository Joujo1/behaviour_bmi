"""
GPIO hardware abstraction layer.

All pin numbers and all RPi.GPIO calls are confined to this module.
Engine and actions interact with hardware exclusively through the functions here.

All beam sensors are monitored continuously for the entire trial with both
entry and exit edges.

Audio is GPIO-based: a brief HIGH pulse on an AUDIO_PIN drives the PAM8302
amplifier input directly, producing an audible click.
On non-Pi machines the module loads normally using a minimal mock, allowing
development and testing on the Linux PC without any hardware present.
"""

import logging
import threading

logger = logging.getLogger(__name__)


import RPi.GPIO as _GPIO



from config import (
    LED_PINS, VALVE_PINS, BEAM_PINS, AUDIO_PINS,
    BEAM_ACTIVE_LOW, BEAM_DEBOUNCE_MS,
)

# Internal output-state tracking
_output_state: dict[int, bool] = {}
_output_lock = threading.Lock()


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

    for target, pin in BEAM_PINS.items():
        pull = _GPIO.PUD_DOWN if BEAM_ACTIVE_LOW[target] else _GPIO.PUD_UP
        _GPIO.setup(pin, _GPIO.IN, pull_up_down=pull)

    all_output_pins = (list(LED_PINS.values()) + list(VALVE_PINS.values()) + list(AUDIO_PINS.values()))
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


def safety_sweep() -> None:
    """Force all outputs off; called on trial abort, watchdog, or shutdown."""
    for target in LED_PINS:
        set_led(target, False)
    for target in VALVE_PINS:
        set_valve(target, False)
    for target in AUDIO_PINS:
        set_audio(target, False)
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

    return snapshot
