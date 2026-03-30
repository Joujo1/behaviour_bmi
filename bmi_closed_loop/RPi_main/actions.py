"""
Action registry for the trial state machine engine.

Each entry in ACTIONS maps a JSON action "type" string to a Python function.
All hardware interaction goes exclusively through gpio_handler.
"""

import logging
import time

import gpio_handler
from config import LED_PINS, VALVE_PINS, AUDIO_PINS, CLICK_PULSE_US

logger = logging.getLogger(__name__)


def _led_on(target: str) -> None:
    """Turn on the LED at the given target port."""
    gpio_handler.set_led(target, True)


def _led_off(target: str) -> None:
    """Turn off the LED at the given target port."""
    gpio_handler.set_led(target, False)


def _valve_open(target: str) -> None:
    """Open the reward valve at the given target port."""
    gpio_handler.set_valve(target, True)


def _valve_close(target: str) -> None:
    """Close the reward valve at the given target port."""
    gpio_handler.set_valve(target, False)


def _play_audio(target: str) -> None:
    """Emit a single click on the given audio channel via a GPIO pulse."""
    gpio_handler.set_audio(target, True)
    time.sleep(CLICK_PULSE_US / 1_000_000)
    gpio_handler.set_audio(target, False)


def _stop_audio(target: str) -> None:
    """No-op for GPIO-based audio — clicks are instantaneous pulses."""
    pass


ACTIONS: dict = {
    "led_on":      _led_on,
    "led_off":     _led_off,
    "valve_open":  _valve_open,
    "valve_close": _valve_close,
    "play_audio":  _play_audio,
    "stop_audio":  _stop_audio,
}


def dispatch(action_dict: dict) -> None:
    """Look up the action type, pass remaining fields as kwargs, and execute it."""
    action_dict = dict(action_dict)
    action_type = action_dict.pop("type", None)

    if action_type is None:
        logger.error("Action dict missing 'type' key: %s", action_dict)
        return

    fn = ACTIONS.get(action_type)
    if fn is None:
        logger.error("Unknown action type '%s' — skipping", action_type)
        return

    try:
        logger.info("Action  %s  %s", action_type, action_dict)
        fn(**action_dict)
    except TypeError as e:
        logger.error("Bad arguments for action '%s': %s", action_type, e)
    except Exception as e:
        logger.error("Action '%s' raised an unexpected error: %s", action_type, e)


def safety_sweep() -> None:
    """Force all LEDs and valves off; call on trial abort, watchdog, or shutdown."""
    for target in LED_PINS:
        gpio_handler.set_led(target, False)
    for target in VALVE_PINS:
        gpio_handler.set_valve(target, False)
    for target in AUDIO_PINS:
        gpio_handler.set_audio(target, False)
    logger.info("actions.safety_sweep complete")
