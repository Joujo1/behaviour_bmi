"""
Action registry for the trial state machine engine.

Each entry in ACTIONS maps a JSON action "type" string to a Python function.
All hardware interaction goes exclusively through gpio_handler.
"""

import logging
import threading
import time

import sounddevice as sd

import audio
import gpio_handler
from config import LED_PINS, VALVE_PINS, AUDIO_PINS, CLICK_PULSE_US, AUDIO_DEVICE, AUDIO_SRATE

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
    """No-op — audio output is now via the audio jack (sounddevice)."""
    # gpio_handler.set_audio(target, True)
    # time.sleep(CLICK_PULSE_US / 1_000_000)
    # gpio_handler.set_audio(target, False)


def _stop_audio(target: str) -> None:
    """No-op — audio output is now via the audio jack (sounddevice)."""
    pass

# Module-level stop event; replaced each time _play_clicks() is called.
# Setting it signals the player thread to stop feeding the stream.
_click_stop: threading.Event = threading.Event()
_click_stop.set()   # start in the "stopped / idle" state

# Pre-built click waveform — constructed once at import time.
_CLICK = audio.build_click(srate=AUDIO_SRATE)

# Persistent OutputStream — opened once, kept alive between trials so there
# is no per-trial stream startup transient.
_stream: sd.OutputStream | None = None
_CHUNK = 512    # samples per write (~10 ms at 48 kHz); stop flag checked between chunks


def _open_stream() -> sd.OutputStream:
    """Return the running OutputStream, (re-)opening it if necessary."""
    global _stream
    if _stream is not None and _stream.active:
        return _stream
    if _stream is not None:
        try:
            _stream.close()
        except Exception:
            pass
    _stream = sd.OutputStream(samplerate=AUDIO_SRATE, channels=2,
                               device=AUDIO_DEVICE, dtype='float32')
    _stream.start()
    logger.info("Audio OutputStream opened")
    return _stream


def _play_clicks(left_clicks: list, right_clicks: list, on_complete=None,
                 log_cb=None) -> None:
    """
    Render both click trains into a stereo float32 buffer and stream it via
    a persistent OutputStream.

    The buffer is fed in small chunks so the stop flag is checked frequently.
    When playback ends naturally (i.e. stop_clicks() was NOT called),
    on_complete() is fired so the engine can trigger the clicks_done transition.
    """
    global _click_stop
    _click_stop.set()                # signal any running player to stop
    _click_stop = threading.Event()  # fresh event for this run
    stop = _click_stop

    if log_cb:
        log_cb("clicks", True)

    buf = audio.build_buffer_from_times(_CLICK, left_clicks, right_clicks,
                                        srate=AUDIO_SRATE)

    def _player():
        stream = _open_stream()
        i = 0
        try:
            while i < len(buf) and not stop.is_set():
                stream.write(buf[i:i + _CHUNK])
                i += _CHUNK
        except Exception as e:
            logger.warning("Click player error: %s", e)
        if not stop.is_set() and on_complete is not None:
            logger.info("Click trains finished — firing on_complete")
            on_complete()

    threading.Thread(target=_player, daemon=True, name="clicks-player").start()
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


def dispatch(action_dict: dict, on_complete=None, log_cb=None) -> None:
    """
    Look up the action type, pass remaining fields as kwargs, and execute it.

    on_complete and log_cb are forwarded only for the 'play_clicks' action type.
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

    if action_type == "play_clicks":
        if on_complete is not None:
            action_dict["on_complete"] = on_complete
        if log_cb is not None:
            action_dict["log_cb"] = log_cb

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
    # Audio pins not driven — output via audio jack now
    # for target in AUDIO_PINS:
    #     gpio_handler.set_audio(target, False)
    logger.info("actions.safety_sweep complete")
