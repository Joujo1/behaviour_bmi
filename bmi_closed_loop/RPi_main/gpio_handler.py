"""
GPIO hardware abstraction layer.

All pin numbers and all RPi.GPIO calls are confined to this module.
Engine and actions interact with hardware exclusively through the functions here.

All IR sensors are monitored continuously for the entire trial with both
entry and exit edges.

Audio is GPIO-based: a brief HIGH pulse on an AUDIO_PIN drives the PAM8302
amplifier input directly, producing an audible click.

On non-Pi machines the module loads normally using a minimal mock, allowing
development and testing on the Linux PC without any hardware present.
"""

import logging
import threading

logger = logging.getLogger(__name__)


try:
    import RPi.GPIO as _GPIO
    _ON_PI = True
    logger.debug("RPi.GPIO loaded")
except ImportError:
    _ON_PI = False
    logger.warning("RPi.GPIO not available — using mock GPIO (non-Pi machine)")

    class _MockGPIO:
        """Minimal mock with correct constant values so comparisons work."""
        BCM      = 11
        IN       = 1
        OUT      = 0
        HIGH     = 1
        LOW      = 0
        RISING   = 31
        FALLING  = 32
        BOTH     = 33
        PUD_UP   = 22
        PUD_DOWN = 21

        def setmode(self, mode):                                    pass
        def setwarnings(self, w):                                   pass
        def setup(self, pin, direction, pull_up_down=None,
                  initial=None):                                    pass
        def output(self, pin, value):                               pass
        def input(self, pin):                                       return 0
        def add_event_detect(self, pin, edge, callback=None,
                             bouncetime=0):                         pass
        def remove_event_detect(self, pin):                         pass
        def cleanup(self):                                          pass

    _GPIO = _MockGPIO()



from config import (
    LED_PINS, VALVE_PINS, IR_PINS, AUDIO_PINS,
    IR_ACTIVE_LOW, IR_DEBOUNCE_MS,
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

    for target, pin in IR_PINS.items():
        pull = _GPIO.PUD_UP if IR_ACTIVE_LOW[target] else _GPIO.PUD_DOWN
        _GPIO.setup(pin, _GPIO.IN, pull_up_down=pull)

    all_output_pins = (list(LED_PINS.values()) + list(VALVE_PINS.values()) + list(AUDIO_PINS.values()))
    with _output_lock:
        for pin in all_output_pins:
            _output_state[pin] = False

    logger.info("GPIO setup complete (on_pi=%s)", _ON_PI)


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
    """Return the normalised logical state of an IR sensor (True = beam broken)."""
    raw = _GPIO.input(pin)
    return (raw == _GPIO.LOW) if IR_ACTIVE_LOW[target] else (raw == _GPIO.HIGH)


def start_monitoring(on_event) -> None:
    """
    Begin monitoring all IR sensors for the duration of a trial.
    """
    for target, pin in IR_PINS.items():
        try:
            _GPIO.remove_event_detect(pin)
        except Exception:
            pass

        def _handler(_, t: str = target, p: int = pin) -> None:
            on_event(t, _read_active(t, p))

        _GPIO.add_event_detect(pin, _GPIO.BOTH,
                               callback=_handler,
                               bouncetime=IR_DEBOUNCE_MS)

    logger.debug("IR monitoring started")


def stop_monitoring() -> None:
    """Remove all IR event detection; called at trial end."""
    for pin in IR_PINS.values():
        try:
            _GPIO.remove_event_detect(pin)
        except Exception:
            pass
    logger.debug("IR monitoring stopped")


def get_snapshot() -> dict:
    """
    Return the current binary state of all hardware as a flat dict.

    IR values are normalised to logical 'active' level (1 = beam broken /
    animal present) regardless of pull direction.  Output values come from
    internal tracking, not hardware read-back.
    """
    snapshot = {}

    for target, pin in IR_PINS.items():
        raw    = _GPIO.input(pin)
        active = (raw == _GPIO.LOW) if IR_ACTIVE_LOW[target] else (raw == _GPIO.HIGH)
        snapshot[f"ir_{target}"] = int(active)

    with _output_lock:
        for target, pin in LED_PINS.items():
            snapshot[f"led_{target}"] = int(_output_state.get(pin, False))
        for target, pin in VALVE_PINS.items():
            snapshot[f"valve_{target}"] = int(_output_state.get(pin, False))
        for target, pin in AUDIO_PINS.items():
            snapshot[f"audio_{target}"] = int(_output_state.get(pin, False))

    return snapshot
