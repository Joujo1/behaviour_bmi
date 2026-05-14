"""
GPIO hardware abstraction layer — pigpio + gpiod backend.

All pin numbers and all pigpio/gpiod calls are confined to this module.
Engine and actions interact with hardware exclusively through the functions here.

Input monitoring (beam sensors) uses the kernel GPIO character device via gpiod,
which delivers hardware interrupts directly to poll() — no DMA ring buffer or
IPC hop. Output writes use /dev/gpiomem mmap for sub-µs latency.

pigpiod is still used for initial pin setup and fan PWM.

Requires:
  sudo systemctl start pigpiod
  sudo apt install python3-gpiod
"""

import ctypes
import logging
import mmap
import os
import select as _select
import struct
import threading

import gpiod
import pigpio

from config import (
    LED_PINS, VALVE_PINS, AUDIO_PINS, BEAM_PINS,
    BEAM_ACTIVE_LOW,
    FAN_PIN, STRIP_PIN, FAN_PWM_FREQ, FAN_MIN_DUTY,
)

logger = logging.getLogger(__name__)

# ── pigpio daemon conection (used for setup and fan PWM only) ───────────────
_pi: pigpio.pi = None

# ── gpiod input monitoring ────────────────────────────────────────────────────
_gpiod_chip: gpiod.Chip | None = None
_gpiod_fd_map: dict = {}   # event_fd → (target, line)
_monitoring: bool  = False

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

    # Beam pins are NOT configured here — gpiod owns them exclusively.
    # Configuring them via pigpiod AND gpiod causes a register write conflict.

    all_output_pins = (list(LED_PINS.values()) + list(VALVE_PINS.values()) +
                       list(AUDIO_PINS.values()) + [FAN_PIN, STRIP_PIN])
    with _output_lock:
        for pin in all_output_pins:
            _output_state[pin] = False

    _init_fast_gpio()
    logger.info("GPIO setup complete (pigpio for outputs + fan PWM; gpiod for beam inputs)")


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
    """Begin monitoring all IR sensors via kernel GPIO interrupts (gpiod).

    Uses poll() on hardware interrupt event fds — no DMA ring buffer or pigpiod
    IPC hop. The monitor thread is elevated to SCHED_FIFO 75 and pinned to the
    RT core. The kernel timestamps edges at interrupt time (CLOCK_MONOTONIC).

    fast_reaction(target, is_active), if provided, is called before on_event
    so LED/valve writes happen immediately without a queue hop.
    """
    global _gpiod_chip, _gpiod_fd_map, _monitoring, _fast_reaction_fn

    _fast_reaction_fn = fast_reaction
    _monitoring       = True
    _gpiod_chip       = gpiod.Chip('gpiochip0')
    _gpiod_fd_map     = {}

    for target, pin in BEAM_PINS.items():
        line  = _gpiod_chip.get_line(pin)
        flags = (gpiod.LINE_REQ_FLAG_BIAS_PULL_UP if BEAM_ACTIVE_LOW[target]
                 else gpiod.LINE_REQ_FLAG_BIAS_PULL_DOWN)
        line.request(consumer='bmi-beam',
                     type=gpiod.LINE_REQ_EV_BOTH_EDGES,
                     flags=flags)
        _gpiod_fd_map[line.event_get_fd()] = (target, line)

    threading.Thread(target=_gpiod_monitor, args=(on_event,),
                     daemon=True, name='gpio-mon').start()
    logger.info("Beam monitoring started (gpiod hardware interrupts)")


def _gpiod_monitor(on_event) -> None:
    """Monitor thread: blocks on poll(), fires on hardware GPIO interrupt."""
    _set_rt_priority(75)
    fds = list(_gpiod_fd_map.keys())
    while _monitoring:
        ready = _select.select(fds, [], [], 0.1)[0]
        for fd in ready:
            if not _monitoring:
                return
            target, line = _gpiod_fd_map[fd]
            ev        = line.event_read()
            is_active = (ev.type == gpiod.LineEvent.FALLING_EDGE) \
                        if BEAM_ACTIVE_LOW[target] \
                        else (ev.type == gpiod.LineEvent.RISING_EDGE)
            t_mono    = ev.sec + ev.nsec / 1e9  # kernel interrupt timestamp, CLOCK_MONOTONIC
            if _fast_reaction_fn is not None:
                _fast_reaction_fn(target, is_active)
            on_event(target, is_active, t_mono)


def stop_monitoring() -> None:
    """Stop the gpiod monitor thread and release all beam sensor lines."""
    global _monitoring, _gpiod_fd_map, _gpiod_chip, _fast_reaction_fn
    _monitoring       = False
    _fast_reaction_fn = None
    for _, line in _gpiod_fd_map.values():
        try:
            line.release()
        except Exception:
            pass
    _gpiod_fd_map = {}
    if _gpiod_chip is not None:
        _gpiod_chip.close()
        _gpiod_chip = None
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
