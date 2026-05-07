"""
GPIO PWM click generator — standalone scope capture tool.

Encodes the same click waveform used by actions.py as a 250 kHz PWM signal
on a GPIO pin.  Wire the pin through an RC low-pass filter to a scope channel:

    BCM pin → R=100Ω → [probe tip] → C=100nF → GND

The RC filter (f_c ≈ 15.9 kHz) removes the 250 kHz carrier, leaving the
demodulated click envelope visible on the scope.

Run alongside latency_measure.py to compare the PWM waveform (scope Ch3)
against the audio jack output (scope Ch1) and the GPIO trigger (scope Ch2).

Requires:  sudo pigpiod -t 1   (PCM timing — avoids conflict with audio PWM)

Usage:
    python3 debug/pwm_click_gen.py --pin 27 --rate 20 --dur 2.0
    python3 debug/pwm_click_gen.py --pin 27 --rate 20 --n 50
"""

import argparse
import os
import sys
import time
import threading
import queue as _queue

import numpy as np

try:
    import pigpio as _pigpio
except ImportError:
    print("ERROR: pigpio not installed.")
    print("  Build from source: https://github.com/joan2937/pigpio")
    print("  Then run: sudo pigpiod -t 1")
    sys.exit(1)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import audio
from config import AUDIO_SRATE, CLICK_WIDTH_S


def _build_wave(pi, pin: int, click_samples: np.ndarray,
                srate: int, pwm_freq: int = 250_000) -> int:
    """Encode click_samples as a pigpio DMA waveform. Returns wave_id."""
    carrier_us   = 1_000_000 // pwm_freq
    cycles_per_s = round(pwm_freq / srate)
    pin_mask     = 1 << pin

    pulses = []
    for sample in click_samples:
        duty   = (float(sample) + 1.0) / 2.0
        on_us  = max(1, min(carrier_us - 1, round(duty * carrier_us)))
        off_us = carrier_us - on_us
        for _ in range(cycles_per_s):
            pulses.append(_pigpio.pulse(pin_mask, 0,        on_us))
            pulses.append(_pigpio.pulse(0,        pin_mask, off_us))

    pi.wave_clear()
    pi.wave_add_generic(pulses)
    return pi.wave_create()


def _worker(pi, wave_id: int, q: _queue.Queue) -> None:
    """Fire wave_id at each absolute CLOCK_MONOTONIC time pulled from q."""
    while True:
        t_target = q.get()
        if t_target is None:
            break
        slack = t_target - time.clock_gettime(time.CLOCK_MONOTONIC) - 0.001
        if slack > 0:
            time.sleep(slack)
        now = time.clock_gettime(time.CLOCK_MONOTONIC)
        if now > t_target + 0.002:
            print(f"[pwm] skipped late click ({(now - t_target)*1000:.1f} ms late)")
            continue
        while time.clock_gettime(time.CLOCK_MONOTONIC) < t_target:
            pass
        pi.wave_send_once(wave_id)


def _poisson_train(rate: float, duration: float, rng, min_ici: float) -> list:
    clicks, t, last_t = [], 0.0, float("-inf")
    while True:
        t += rng.exponential(1.0 / rate)
        t  = max(t, last_t + min_ici)
        if t >= duration:
            break
        clicks.append(round(float(t), 4))
        last_t = t
    return clicks


def run(pin: int, n_trials: int, click_rate: float,
        duration: float, iti_s: float) -> None:

    pi = _pigpio.pi()
    if not pi.connected:
        print("ERROR: cannot connect to pigpiod.")
        print("  Start it with: sudo pigpiod -t 1")
        sys.exit(1)

    click_samples = audio.build_click(srate=AUDIO_SRATE)
    wave_id = _build_wave(pi, pin, click_samples, AUDIO_SRATE)
    print(f"Waveform built: {len(click_samples)} samples  wave_id={wave_id}")
    print(f"Pin BCM {pin}  →  R=100Ω  →  [probe]  →  C=100nF  →  GND")
    print(f"Running {n_trials} trials  rate={click_rate:.0f} Hz  "
          f"dur={duration:.1f} s  iti={iti_s:.1f} s\n")

    q = _queue.Queue()
    t = threading.Thread(target=_worker, args=(pi, wave_id, q),
                         daemon=True, name="pwm-worker")
    t.start()

    rng = np.random.default_rng()
    min_ici = CLICK_WIDTH_S

    try:
        for i in range(n_trials):
            clicks = _poisson_train(click_rate, duration, rng, min_ici)
            if not clicks:
                continue
            t0 = time.clock_gettime(time.CLOCK_MONOTONIC)
            for t_c in clicks:
                q.put_nowait(t0 + t_c)
            print(f"  Trial {i:4d}: {len(clicks)} clicks")
            time.sleep(duration + iti_s)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        q.put(None)
        t.join(timeout=1.0)
        pi.wave_delete(wave_id)
        pi.stop()
        print("Done.")


def main():
    p = argparse.ArgumentParser(description="GPIO PWM click generator for scope capture")
    p.add_argument("--pin",  type=int,   required=True,  help="BCM pin number")
    p.add_argument("--n",    type=int,   default=100,    help="Number of trials (default: 100)")
    p.add_argument("--rate", type=float, default=20.0,   help="Click rate Hz (default: 20)")
    p.add_argument("--dur",  type=float, default=2.0,    help="Trial duration s (default: 2.0)")
    p.add_argument("--iti",  type=float, default=0.5,    help="ITI s (default: 0.5)")
    args = p.parse_args()

    run(args.pin, args.n, args.rate, args.dur, args.iti)


if __name__ == "__main__":
    main()
