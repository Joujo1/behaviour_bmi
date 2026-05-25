"""
GPIO hardware abstraction layer — gpiod v2 + /dev/gpiomem mmap, no pigpiod.

All pin numbers and all GPIO calls are confined to this module.
Engine and actions interact with hardware exclusively through the functions here.

Input monitoring  : kernel GPIO character device via gpiod v2 (hardware interrupts
                    delivered to poll() — no DMA ring buffer or IPC hop).
Output writes     : /dev/gpiomem mmap GPSET0/GPCLR0 (~1µs, no IPC).
Fan PWM           : software PWM thread (200 Hz) — GPIO8 has no hardware PWM.
pigpiod           : NOT used. Can be stopped/disabled.

Requires:
  sudo apt install python3-gpiod   # must be gpiod v2.x
"""

import ctypes
import logging
import mmap
import os
import select as _select
import struct
import threading

import gpiod
from gpiod.line import Bias, Direction, Edge, Value

from config import (
    LED_PINS, VALVE_PINS, AUDIO_PINS, BEAM_PINS,
    BEAM_ACTIVE_LOW,
    FAN_PIN, STRIP_PIN, FAN_PWM_FREQ, FAN_MIN_DUTY,
)

logger = logging.getLogger(__name__)

# gpiod v2 output request (all output pins, held open for process lifetime)
_gpiod_out_req: gpiod.LineRequest | None = None

# gpiod v2 input monitoring
_gpiod_in_req:  gpiod.LineRequest | None = None
_pin_to_target: dict                     = {}   # beam pin → target name
_monitoring:    bool                     = False

# internal output-state tracking
_output_state: dict[int, bool] = {}
_output_lock   = threading.Lock()

# fan software PWM
_fan_pwm_lock:   threading.Lock  = threading.Lock()
_fan_pwm_duty:   float           = 0.0
_fan_pwm_active: bool            = False
_fan_pwm_stop:   threading.Event = threading.Event()
_fan_pwm_thread: threading.Thread | None = None

# /dev/gpiomem mmap — BCM2711 GPIO register offsets
_gpio_mem: mmap.mmap | None = None
_GPSET0 = 0x1C   # set   pins 0-31 (bit-mask, write-only semantics)
_GPCLR0 = 0x28   # clear pins 0-31
_GPLEV0 = 0x34   # read  pins 0-31

# per-trial callback (swapped each trial, None between trials)
_on_event_fn = None


# -- RT scheduling --

def _set_rt_priority(priority: int = 75) -> None:
    """Elevate the calling thread to SCHED_FIFO and pin it to the RT core."""
    class _Param(ctypes.Structure):
        _fields_ = [("sched_priority", ctypes.c_int)]
    _libc = ctypes.CDLL("libc.so.6")
    if os.environ.get("DISABLE_FIFO", "0") != "1":
        ret = _libc.sched_setscheduler(0, 1, ctypes.byref(_Param(priority)))  # SCHED_FIFO=1
        if ret != 0:
            logger.warning("SCHED_FIFO unavailable — ensure service runs as root")
    else:
        _libc.sched_setscheduler(0, 0, ctypes.byref(_Param(0)))  # SCHED_OTHER=0
    if os.environ.get("DISABLE_AFFINITY", "0") != "1":
        try:
            os.sched_setaffinity(0, {3})
        except OSError:
            pass
    else:
        try:
            os.sched_setaffinity(0, set(range(os.cpu_count() or 4)))
        except OSError:
            pass


# -- Internal helpers --

def _init_fast_gpio() -> None:
    """Open /dev/gpiomem and mmap the BCM GPIO registers for direct writes."""
    global _gpio_mem
    try:
        fd = os.open('/dev/gpiomem', os.O_RDWR | os.O_SYNC)
        _gpio_mem = mmap.mmap(fd, 256, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        os.close(fd)
        logger.info("Direct GPIO mmap enabled — output writes ~1µs")
    except Exception as e:
        logger.warning("Direct GPIO mmap unavailable: %s — falling back to gpiod", e)


def _drive(pin: int, state: bool) -> None:
    """Write a digital value to an output pin via mmap (or gpiod v2 fallback)."""
    if _gpio_mem is not None:
        struct.pack_into('I', _gpio_mem, _GPSET0 if state else _GPCLR0, 1 << pin)
    elif _gpiod_out_req is not None:
        _gpiod_out_req.set_value(pin, Value.ACTIVE if state else Value.INACTIVE)
    with _output_lock:
        _output_state[pin] = state


def _read_pin_level(pin: int) -> bool:
    """Read the current level of any pin via mmap GPLEV0 (or gpiod v2 fallback)."""
    if _gpio_mem is not None:
        return bool(struct.unpack_from('I', _gpio_mem, _GPLEV0)[0] & (1 << pin))
    try:
        if _gpiod_out_req is not None:
            return _gpiod_out_req.get_value(pin) == Value.ACTIVE
    except Exception:
        pass
    try:
        if _gpiod_in_req is not None:
            return _gpiod_in_req.get_value(pin) == Value.ACTIVE
    except Exception:
        pass
    return False


# -- Public API --

def setup() -> None:
    """Configure all output GPIO pins via gpiod v2. Call once at process start."""
    global _gpiod_out_req

    _init_fast_gpio()

    output_pins = (list(LED_PINS.values()) + list(VALVE_PINS.values()) +
                   list(AUDIO_PINS.values()) + [FAN_PIN, STRIP_PIN])

    _gpiod_out_req = gpiod.request_lines(
        '/dev/gpiochip0',
        consumer='bmi-out',
        config={
            pin: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE)
            for pin in output_pins
        },
    )

    with _output_lock:
        for pin in output_pins:
            _output_state[pin] = False

    logger.info("GPIO setup complete (gpiod v2 + mmap, pigpiod not used)")


def cleanup() -> None:
    """Safety sweep and release all GPIO resources."""
    global _gpiod_out_req
    stop_monitoring()
    safety_sweep()
    _stop_fan_pwm_thread()
    if _gpiod_out_req is not None:
        try:
            _gpiod_out_req.release()
        except Exception:
            pass
        _gpiod_out_req = None
    logger.info("GPIO cleaned up")


def set_led(target: str, state: bool) -> None:
    _drive(LED_PINS[target], state)


def set_valve(target: str, state: bool) -> None:
    _drive(VALVE_PINS[target], state)


def set_audio(target: str, state: bool) -> None:
    _drive(AUDIO_PINS[target], state)


# -- Fan --

def _stop_fan_pwm_thread() -> None:
    global _fan_pwm_thread, _fan_pwm_active, _fan_pwm_duty
    _fan_pwm_stop.set()
    if _fan_pwm_thread is not None and _fan_pwm_thread.is_alive():
        _fan_pwm_thread.join(timeout=0.5)
    _fan_pwm_thread  = None
    _fan_pwm_active  = False
    _fan_pwm_duty    = 0.0


def set_fan(state: bool) -> None:
    """Drive fan fully on or off. Stops any active software PWM first."""
    with _fan_pwm_lock:
        if _fan_pwm_active:
            _stop_fan_pwm_thread()
    _drive(FAN_PIN, state)


def set_fan_pwm(duty: float, freq: float = FAN_PWM_FREQ) -> None:
    """Control fan speed via software PWM thread. duty is 0–100 (percent)."""
    global _fan_pwm_thread, _fan_pwm_active, _fan_pwm_duty

    duty = max(0.0, min(100.0, float(duty)))
    if duty < FAN_MIN_DUTY:
        set_fan(False)
        return
    if duty >= 100.0:
        set_fan(True)
        return

    with _fan_pwm_lock:
        _stop_fan_pwm_thread()
        _fan_pwm_stop.clear()
        period   = 1.0 / freq
        on_time  = period * duty / 100.0
        off_time = period - on_time
        _fan_pwm_duty   = duty
        _fan_pwm_active = True

        def _pwm_loop():
            while not _fan_pwm_stop.is_set():
                _drive(FAN_PIN, True)
                _fan_pwm_stop.wait(on_time)
                if _fan_pwm_stop.is_set():
                    break
                _drive(FAN_PIN, False)
                _fan_pwm_stop.wait(off_time)
            _drive(FAN_PIN, False)

        _fan_pwm_thread = threading.Thread(target=_pwm_loop, daemon=True, name='fan-pwm')
        _fan_pwm_thread.start()

    with _output_lock:
        _output_state[FAN_PIN] = True
    logger.debug("Fan PWM: duty=%.1f%% freq=%.1fHz", duty, freq)


def get_fan_pwm_duty() -> float:
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
    set_fan(False)
    set_strip(False)
    logger.info("Safety sweep complete")


# -- Beam sensor monitoring --

def start_monitoring() -> None:
    """Open beam sensor lines and start the persistent monitor thread.

    Called once at process start. Callbacks are initially None (events dropped
    between trials). Use update_callbacks() each trial to register/clear them.
    """
    global _gpiod_in_req, _pin_to_target, _monitoring

    _monitoring    = True
    _pin_to_target = {pin: tgt for tgt, pin in BEAM_PINS.items()}

    _gpiod_in_req = gpiod.request_lines(
        '/dev/gpiochip0',
        consumer='bmi-beam',
        config={
            pin: gpiod.LineSettings(
                direction=Direction.INPUT,
                edge_detection=Edge.BOTH,
                bias=Bias.PULL_UP if BEAM_ACTIVE_LOW[tgt] else Bias.PULL_DOWN,
            )
            for tgt, pin in BEAM_PINS.items()
        },
    )

    threading.Thread(target=_gpiod_monitor, daemon=True, name='gpio-mon').start()
    logger.info("Beam monitoring started (persistent, gpiod v2)")


def update_callbacks(on_event) -> None:
    """Swap the per-trial beam callback. Pass None to silence events (ITI)."""
    global _on_event_fn
    _on_event_fn = on_event


def _gpiod_monitor() -> None:
    """Monitor thread: blocks on poll(), fires immediately on GPIO interrupt."""
    _set_rt_priority(75)
    req = _gpiod_in_req
    fd  = req.fd
    while _monitoring:
        ready = _select.select([fd], [], [], 0.1)[0]
        if not ready or not _monitoring:
            continue
        for ev in req.read_edge_events():
            if not _monitoring:
                return
            pin    = ev.line_offset
            target = _pin_to_target.get(pin)
            if target is None:
                continue
            is_active = (ev.event_type.name == 'FALLING_EDGE') \
                        if BEAM_ACTIVE_LOW[target] \
                        else (ev.event_type.name == 'RISING_EDGE')
            t_mono = ev.timestamp_ns / 1e9   # kernel interrupt timestamp (CLOCK_MONOTONIC)
            fn = _on_event_fn                 # snapshot global — GIL-atomic read
            if fn is not None:
                fn(target, is_active, t_mono)


def stop_monitoring() -> None:
    """Stop the monitor thread and release beam sensor lines. Call at shutdown only."""
    global _monitoring, _gpiod_in_req, _pin_to_target, _on_event_fn
    _monitoring  = False
    _on_event_fn = None
    _pin_to_target    = {}
    if _gpiod_in_req is not None:
        try:
            _gpiod_in_req.release()
        except Exception:
            pass
        _gpiod_in_req = None
    logger.info("Beam monitoring stopped")


def get_snapshot() -> dict:
    """Return the current binary state of all hardware as a flat dict."""
    snapshot = {}

    for target, pin in BEAM_PINS.items():
        active = _read_pin_level(pin)
        if BEAM_ACTIVE_LOW[target]:
            active = not active
        snapshot[f"beam_{target}"] = int(active)

    with _output_lock:
        for prefix, pins in {"led": LED_PINS, "valve": VALVE_PINS}.items():
            for target, pin in pins.items():
                tracked  = int(_output_state.get(pin, False))
                readback = int(_read_pin_level(pin))
                snapshot[f"{prefix}_{target}_tracked"]  = tracked
                snapshot[f"{prefix}_{target}_readback"] = readback
                if tracked != readback:
                    logger.warning(
                        "Output state mismatch on %s_%s (pin %d): tracked=%d readback=%d",
                        prefix, target, pin, tracked, readback,
                    )

    snapshot["fan_pwm_duty"] = get_fan_pwm_duty()
    return snapshot
