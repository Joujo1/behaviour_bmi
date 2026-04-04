"""
Action registry for the trial state machine engine.

Each entry in ACTIONS maps a JSON action "type" string to a Python function.
All hardware interaction goes exclusively through gpio_handler.
"""

import logging
import threading
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

# Module-level stop event; replaced each time _play_clicks() is called.
# Setting it stops all click threads that share a reference to the same event.
_click_stop: threading.Event = threading.Event()
_click_stop.set()   # start in the "stopped / idle" state


def _click_loop(side: str, click_times: list, stop_event: threading.Event) -> None:
    """Play pre-computed click times for one side, interruptible via stop_event."""
    t0 = time.monotonic()
    for click_t in click_times:
        remaining = click_t - (time.monotonic() - t0)
        if remaining > 0:
            if stop_event.wait(timeout=remaining):
                return
        if stop_event.is_set():
            return
        _play_audio(side)


def _play_clicks(left_clicks: list, right_clicks: list, on_complete=None) -> None:
    """
    Play two independent Poisson click trains (one per ear) in background threads.

    When both threads finish naturally (i.e. stop_clicks() was NOT called),
    on_complete() is fired so the engine can trigger the clicks_done transition.
    """
    global _click_stop
    _click_stop.set()               # cancel any previous playback
    _click_stop = threading.Event() # fresh event for this run
    stop = _click_stop              # local ref shared by all threads below

    t_left  = threading.Thread(target=_click_loop,
                               args=("left",  left_clicks,  stop),
                               daemon=True, name="clicks-left")
    t_right = threading.Thread(target=_click_loop,
                               args=("right", right_clicks, stop),
                               daemon=True, name="clicks-right")

    def _watcher():
        t_left.join()
        t_right.join()
        if not stop.is_set() and on_complete is not None:
            logger.info("Click trains finished — firing on_complete")
            on_complete()

    t_left.start()
    t_right.start()
    threading.Thread(target=_watcher, daemon=True, name="clicks-watcher").start()
    logger.info("Click trains started: %d left, %d right", len(left_clicks), len(right_clicks))


# Note frequencies in Hz
_NOTES = {
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23,
    "G4": 392.00, "A4": 440.00, "Bb4": 466.16, "C5": 523.25,
    "R":  0.0,  # rest
}

# Happy Birthday: (note, duration_seconds) at ~100 BPM, quarter = 0.6s
_HAPPY_BIRTHDAY = [
    ("C4", 0.3), ("C4", 0.3), ("D4", 0.6), ("C4", 0.6), ("F4", 0.6), ("E4", 1.2),
    ("C4", 0.3), ("C4", 0.3), ("D4", 0.6), ("C4", 0.6), ("G4", 0.6), ("F4", 1.2),
    ("C4", 0.3), ("C4", 0.3), ("C5", 0.6), ("A4", 0.6), ("F4", 0.6), ("E4", 0.6), ("D4", 1.2),
    ("Bb4", 0.3), ("Bb4", 0.3), ("A4", 0.6), ("F4", 0.6), ("G4", 0.6), ("F4", 1.5),
]


def _buzz_note(target: str, frequency: float, duration: float) -> None:
    """Buzz the audio pin at the given frequency for the given duration."""
    if frequency == 0.0:
        time.sleep(duration)
        return
    pulse = CLICK_PULSE_US / 1_000_000
    period = 1.0 / frequency
    low_time = period - pulse
    end = time.time() + duration
    while time.time() < end:
        gpio_handler.set_audio(target, True)
        time.sleep(pulse)
        gpio_handler.set_audio(target, False)
        time.sleep(max(0.0, low_time))


def _play_birthday(target: str) -> None:
    """Play Happy Birthday on the given audio channel in a background thread."""
    def _run():
        for note, duration in _HAPPY_BIRTHDAY:
            _buzz_note(target, _NOTES[note], duration)
            time.sleep(0.05)  # brief gap between notes
    threading.Thread(target=_run, daemon=True, name="happy-birthday").start()


def stop_clicks() -> None:
    """Interrupt any in-progress click train playback immediately."""
    _click_stop.set()
    logger.info("Click trains stopped")


ACTIONS: dict = {
    "led_on":        _led_on,
    "led_off":       _led_off,
    "valve_open":    _valve_open,
    "valve_close":   _valve_close,
    "play_audio":    _play_audio,
    "stop_audio":    _stop_audio,
    "play_birthday": _play_birthday,
    "play_clicks":   _play_clicks,
}


def dispatch(action_dict: dict, on_complete=None) -> None:
    """
    Look up the action type, pass remaining fields as kwargs, and execute it.

    on_complete is forwarded only for the 'play_clicks' action type, so the
    engine can receive a callback when both click trains finish naturally.
    """
    action_dict = dict(action_dict)
    action_type = action_dict.pop("type", None)

    if action_type is None:
        logger.error("Action dict missing 'type' key: %s", action_dict)
        return

    fn = ACTIONS.get(action_type)
    if fn is None:
        logger.error("Unknown action type '%s' — skipping", action_type)
        return

    if action_type == "play_clicks" and on_complete is not None:
        action_dict["on_complete"] = on_complete

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
