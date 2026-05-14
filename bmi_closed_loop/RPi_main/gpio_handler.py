"""
GPIO hardware abstraction layer — pigpio backend.

All pin numbers and all pigpio calls are confined to this module.
Engine and actions interact with hardware exclusively through the functions here.

All beam sensors are monitored continuously for the entire trial with both
entry and exit edges. Callbacks receive a hardware tick timestamp from the
pigpio daemon, which is more accurate than calling clock_gettime inside the
callback because it reflects when the edge was detected by the daemon rather
than when Python woke up.

Requires pigpiod to be running: sudo systemctl start pigpiod
"""

import ctypes
import logging
import mmap
import os
import struct
import threading
import time

import pigpio

from config import (
    LED_PINS, VALVE_PINS, AUDIO_PINS, BEAM_PINS,
    BEAM_ACTIVE_LOW,
    FAN_PIN, STRIP_PIN, FAN_PWM_FREQ, FAN_MIN_DUTY,
)

logger = logging.getLogger(__name__)

# ── pigpio daemon connection ──────────────────────────────────────────────────
_pi: pigpio.pi = None

# ── tick → CLOCK_MONOTONIC anchor (refreshed on every start_monitoring call) ─
_tick_anchor: int   = 0
_mono_anchor: float = 0.0

# ── callback handles (stored so they can be cancelled in stop_monitoring) ─────
_callbacks: list = []

# ── one-shot flag: elevate the pigpio callback thread to SCHED_FIFO on first fire
_gpio_cb_rt_set: bool = False

# ── internal output-state tracking ───────────────────────────────────────────
_output_state: dict[int, bool] = {}
_output_lock = threading.Lock()

# ── fan PWM duty tracking (pigpio PWM is stateless — no object needed) ────────
_fan_pwm_lock  = threading.Lock()
_fan_pwm_duty: float = 0.0
_fan_pwm_active: bool = False

# ── direct /dev/gpiomem mmap for sub-µs output writes (RPi 4 BCM2711) ────────
# GPSET0 (offset 0x1C) sets pins 0-31; GPCLR0 (offset 0x28) clears them.
# These are bit-mask write-only registers — concurrent pigpiod + mmap writes
# to different pins on the same register are safe (no read-modify-write hazard).
_gpio_mem: mmap.mmap | None = None
_GPSET0 = 0x1C
_GPCLR0 = 0x28

# ── fast-reaction hook — set by start_monitoring(), called before queue post ──
_fast_reaction_fn = None


# ── RT scheduling ─────────────────────────────────────────────────────────────

def _set_rt_priority(priority: int = 75) -> None:
    """Elevate the calling thread to SCHED_FIFO and pin it to the RT core."""
    SCHED_FIFO = 1
    class _Param(ctypes.Structure):
        _fields_ = [("sched_priority", ctypes.c_int)]
    ret = ctypes.CDLL("libc.so.6").sched_setscheduler(0, SCHED_FIFO, ctypes.byref(_Param(priority)))
    if ret != 0:
        logger.warning("SCHED_FIFO unavailable — ensure service runs as root")
    try:
        os.sched_setaffinity(0, {3})  # isolate RT threads on core 3 (isolcpus=3)
    except OSError:
        pass


# ── tick → CLOCK_MONOTONIC conversion ────────────────────────────────────────

def _tick_to_mono(tick: int) -> float:
    """Convert a 32-bit pigpio tick (µs since pigpiod start) to CLOCK_MONOTONIC seconds.

    Uses 32-bit unsigned subtraction to handle the ~71.6-minute wrap-around.
    The anchor is refreshed at every trial start so the wrap window is always
    smaller than the 20-minute trial watchdog limit.
    """
    delta_us = (tick - _tick_anchor) & 0xFFFFFFFF
    return _mono_anchor + delta_us / 1_000_000


# ── internal helpers ──────────────────────────────────────────────────────────

def _init_fast_gpio() -> None:
    """Open /dev/gpiomem and mmap the BCM GPIO registers for direct writes."""
    global _gpio_mem
    try:
        fd = os.open('/dev/gpiomem', os.O_RDWR | os.O_SYNC)
        _gpio_mem = mmap.mmap(fd, 256, mmap.MAP_SHARED,
                              mmap.PROT_READ | mmap.PROT_WRITE)
        os.close(fd)
        logger.info("Direct GPIO mmap enabled — output writes ~1µs")
    except Exception as e:
        logger.warning("Direct GPIO mmap unavailable: %s — falling back to pigpio", e)


def _drive(pin: int, state: bool) -> None:
    """Write a digital value to an output pin and record the new state.

    Uses /dev/gpiomem (BCM GPSET0/GPCLR0) when available (~1µs) instead of
    the pigpiod socket (~200µs).
    """
    if _gpio_mem is not None:
        struct.pack_into('I', _gpio_mem, _GPSET0 if state else _GPCLR0, 1 << pin)
    else:
        _pi.write(pin, 1 if state else 0)
    with _output_lock:
        _output_state[pin] = state


# ── public API ────────────────────────────────────────────────────────────────

def setup() -> None:
    """Connect to pigpiod, configure all GPIO pins; must be called once at process start."""
    global _pi, _tick_anchor, _mono_anchor

    _pi = pigpio.pi()
    if not _pi.connected:
        raise RuntimeError(
            "Cannot connect to pigpiod — start it with: sudo systemctl start pigpiod"
        )

    for pin in LED_PINS.values():
        _pi.set_mode(pin, pigpio.OUTPUT)
        _pi.write(pin, 0)
    for pin in VALVE_PINS.values():
        _pi.set_mode(pin, pigpio.OUTPUT)
        _pi.write(pin, 0)
    for pin in AUDIO_PINS.values():
        _pi.set_mode(pin, pigpio.OUTPUT)
        _pi.write(pin, 0)
    _pi.set_mode(FAN_PIN,   pigpio.OUTPUT)
    _pi.write(FAN_PIN, 0)
    _pi.set_mode(STRIP_PIN, pigpio.OUTPUT)
    _pi.write(STRIP_PIN, 0)

    # Configure PWM range for fan once so set_fan_pwm can use 0–100 directly
    _pi.set_PWM_range(FAN_PIN, 100)

    for target, pin in BEAM_PINS.items():
        pull = pigpio.PUD_UP if BEAM_ACTIVE_LOW[target] else pigpio.PUD_DOWN
        _pi.set_mode(pin, pigpio.INPUT)
        _pi.set_pull_up_down(pin, pull)

    all_output_pins = (list(LED_PINS.values()) + list(VALVE_PINS.values()) +
                       list(AUDIO_PINS.values()) + [FAN_PIN, STRIP_PIN])
    with _output_lock:
        for pin in all_output_pins:
            _output_state[pin] = False

    # Record tick/monotonic anchor for timestamp conversion
    _mono_anchor = time.clock_gettime(time.CLOCK_MONOTONIC)
    _tick_anchor  = _pi.get_current_tick()

    _init_fast_gpio()
    logger.info("GPIO setup complete (pigpio daemon connected)")


def cleanup() -> None:
    """Run safety sweep, cancel callbacks, and disconnect from pigpiod."""
    stop_monitoring()
    safety_sweep()
    _pi.stop()
    logger.info("GPIO cleaned up")


def set_led(target: str, state: bool) -> None:
    _drive(LED_PINS[target], state)


def set_valve(target: str, state: bool) -> None:
    _drive(VALVE_PINS[target], state)


def set_audio(target: str, state: bool) -> None:
    _drive(AUDIO_PINS[target], state)


def set_fan(state: bool) -> None:
    """Drive fan fully on or off (binary). Stops any active PWM first."""
    global _fan_pwm_active, _fan_pwm_duty
    with _fan_pwm_lock:
        if _fan_pwm_active:
            _pi.set_PWM_dutycycle(FAN_PIN, 0)
            _fan_pwm_active = False
            _fan_pwm_duty   = 0.0
    _drive(FAN_PIN, state)


def set_fan_pwm(duty: float, freq: float = FAN_PWM_FREQ) -> None:
    """Control fan speed via PWM. duty is 0–100 (percent)."""
    global _fan_pwm_active, _fan_pwm_duty
    duty = max(0.0, min(100.0, float(duty)))

    if duty < FAN_MIN_DUTY:
        set_fan(False)
        return
    if duty >= 100.0:
        set_fan(True)
        return

    with _fan_pwm_lock:
        _pi.set_PWM_frequency(FAN_PIN, int(freq))
        _pi.set_PWM_dutycycle(FAN_PIN, int(duty))
        _fan_pwm_active = True
        _fan_pwm_duty   = duty

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


def _read_active(target: str, pin: int) -> bool:
    """Return the normalised logical state of a beam sensor (True = beam broken)."""
    raw = _pi.read(pin)
    return (raw == 0) if BEAM_ACTIVE_LOW[target] else (raw == 1)


def start_monitoring(on_event, fast_reaction=None) -> None:
    """Begin monitoring all IR sensors for the duration of a trial.

    on_event(target, is_active, t_mono) is called from the pigpio callback
    thread with a hardware tick timestamp converted to CLOCK_MONOTONIC seconds.
    The callback thread is elevated to SCHED_FIFO priority 75 on its first
    invocation so it is never preempted by the FSM thread (priority 70).

    fast_reaction(target, is_active), if provided, is called BEFORE on_event
    so that LED/valve writes happen in the callback thread itself, cutting
    out the queue-to-FSM-thread hop (~1.5–2ms).
    """
    global _callbacks, _tick_anchor, _mono_anchor, _gpio_cb_rt_set, _fast_reaction_fn

    # Refresh anchor at every trial start to keep the wrap window well below
    # the 71.6-minute tick rollover (trials are max 20 minutes)
    _mono_anchor       = time.clock_gettime(time.CLOCK_MONOTONIC)
    _tick_anchor       = _pi.get_current_tick()
    _gpio_cb_rt_set    = False
    _callbacks         = []
    _fast_reaction_fn  = fast_reaction

    for target, pin in BEAM_PINS.items():
        def _handler(gpio, level, tick, t=target, p=pin):
            global _gpio_cb_rt_set
            if not _gpio_cb_rt_set:
                _set_rt_priority(75)
                _gpio_cb_rt_set = True
            is_active = (level == 0) if BEAM_ACTIVE_LOW[t] else (level == 1)
            if _fast_reaction_fn is not None:
                _fast_reaction_fn(t, is_active)
            on_event(t, is_active, _tick_to_mono(tick))

        _callbacks.append(_pi.callback(pin, pigpio.EITHER_EDGE, _handler))

    logger.info("Beam monitoring started")


def stop_monitoring() -> None:
    """Cancel all beam callbacks; called at trial end."""
    global _callbacks, _fast_reaction_fn
    for cb in _callbacks:
        cb.cancel()
    _callbacks        = []
    _fast_reaction_fn = None
    logger.info("Beam monitoring stopped")


def get_snapshot() -> dict:
    """
    Return the current binary state of all hardware as a flat dict.
    For output pins both sources are included so they can be compared:
      *_tracked  — internal _output_state dict (what we wrote)
      *_readback — pigpio read on the output pin (what the hardware reports)
    """
    snapshot = {}

    for target, pin in BEAM_PINS.items():
        raw    = _pi.read(pin)
        active = (raw == 0) if BEAM_ACTIVE_LOW[target] else (raw == 1)
        snapshot[f"beam_{target}"] = int(active)

    all_output_pins = {
        "led":   LED_PINS,
        "valve": VALVE_PINS,
    }
    with _output_lock:
        for prefix, pins in all_output_pins.items():
            for target, pin in pins.items():
                tracked  = int(_output_state.get(pin, False))
                readback = int(_pi.read(pin))
                snapshot[f"{prefix}_{target}_tracked"]  = tracked
                snapshot[f"{prefix}_{target}_readback"] = readback
                if tracked != readback:
                    logger.warning(
                        "Output state mismatch on %s_%s (pin %d): tracked=%d readback=%d",
                        prefix, target, pin, tracked, readback,
                    )

    snapshot["fan_pwm_duty"] = get_fan_pwm_duty()
    return snapshot
