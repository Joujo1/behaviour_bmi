"""
Action registry for the trial state machine engine.

Each entry in ACTIONS maps a JSON action "type" string to a Python function.
All hardware interaction goes exclusively through gpio_handler.
"""

import ctypes
import logging
import threading
import time

import sounddevice as sd

import audio
import gpio_handler
from config import LED_PINS, VALVE_PINS, AUDIO_PINS, CLICK_PULSE_US, AUDIO_DEVICE, AUDIO_SRATE

logger = logging.getLogger(__name__)


def _set_rt_priority(priority: int = 80) -> None:
    """Elevate the calling thread to SCHED_FIFO.  Requires root / CAP_SYS_NICE."""
    SCHED_FIFO = 1
    class _Param(ctypes.Structure):
        _fields_ = [("sched_priority", ctypes.c_int)]
    ret = ctypes.CDLL("libc.so.6").sched_setscheduler(0, SCHED_FIFO, ctypes.byref(_Param(priority)))
    if ret != 0:
        logger.warning("SCHED_FIFO unavailable — run as root for best audio timing")


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

# Pre-built click waveform — constructed once at import time.
_CLICK = audio.build_click(srate=AUDIO_SRATE)

_CHUNK = 48

# Persistent OutputStream with a global callback.
_stream:  sd.OutputStream | None = None
_active:  dict | None            = None   # {'buf','pos','done','stop'}
_rt_done: list                   = [False]

# Module-level stop event; replaced on each _play_clicks() call.
_click_stop: threading.Event = threading.Event()
_click_stop.set()


def _stream_callback(outdata, frames, _time_info, _status) -> None:
    global _active
    if not _rt_done[0]:
        _set_rt_priority(85)
        _rt_done[0] = True

    a = _active
    if a is None or a['stop'].is_set():
        outdata[:] = 0
        if a is not None:
            _active = None
            a['done'].set()
        return

    buf = a['buf']
    pos = a['pos']
    i   = pos[0]
    end = min(i + frames, len(buf))
    got = end - i
    outdata[:got] = buf[i:end]
    outdata[got:] = 0
    pos[0] += frames

    if pos[0] >= len(buf):
        _active = None
        a['done'].set()


def _open_stream() -> None:
    """Open (or reopen) the persistent callback OutputStream."""
    global _stream
    if _stream is not None and _stream.active:
        return
    if _stream is not None:
        try:
            _stream.close()
        except Exception:
            pass
    _stream = sd.OutputStream(samplerate=AUDIO_SRATE, channels=2, device=AUDIO_DEVICE,
                               blocksize=_CHUNK, callback=_stream_callback, dtype='int16')
    _stream.start()
    logger.info("Audio stream opened")


def _play_clicks(left_clicks: list, right_clicks: list, on_complete=None,
                 log_cb=None, latency_cb=None) -> None:
    """
    Render both click trains into a stereo buffer and hand it to the
    persistent callback OutputStream.
    """
    global _click_stop, _active
    _click_stop.set()
    _click_stop = threading.Event()
    stop = _click_stop

    t_scheduled = time.clock_gettime(time.CLOCK_MONOTONIC)

    if log_cb:
        log_cb("clicks", True)

    buf  = (audio.build_buffer_from_times(_CLICK, left_clicks, right_clicks,
                                          srate=AUDIO_SRATE) * 32767).astype('int16')
    done = threading.Event()

    def _player():
        global _active
        _open_stream()
        t_buffer = time.clock_gettime(time.CLOCK_MONOTONIC)
        if latency_cb is not None:
            latency_cb(t_scheduled, t_buffer)
        _active = {'buf': buf, 'pos': [0], 'done': done, 'stop': stop}
        done.wait()
        if not stop.is_set() and on_complete is not None:
            logger.info("Click trains finished — firing on_complete")
            on_complete()

    threading.Thread(target=_player, daemon=True, name="clicks-player").start()
    logger.info("Click trains started: %d left, %d right", len(left_clicks), len(right_clicks))



def init_audio() -> None:
    """Pre-open the persistent audio stream at startup so the first trial has no cold-start delay."""
    _open_stream()
    logger.info("Audio stream pre-opened")


def stop_clicks() -> None:
    """Interrupt any in-progress click train playback immediately."""
    _click_stop.set()
    logger.debug("Click trains stopped")


ACTIONS: dict = {
    "led_on":        _led_on,
    "led_off":       _led_off,
    "valve_open":    _valve_open,
    "valve_close":   _valve_close,
    "play_clicks":   _play_clicks,
}


def dispatch(action_dict: dict, on_complete=None, log_cb=None, latency_cb=None) -> None:
    """
    Look up the action type, pass remaining fields as kwargs, and execute it.
    on_complete, log_cb, and latency_cb are forwarded only for play_clicks.
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
        if latency_cb is not None:
            action_dict["latency_cb"] = latency_cb

    try:
        logger.debug("Action  %s  %s", action_type, action_dict)
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
