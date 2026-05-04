"""
Audio loopback latency measurement — standalone debug script.

Plays real Poisson click trains (left channel only) and records three
CLOCK_MONOTONIC timestamps per click:
  t_buffer   — just before the first stream.write() for this trial
  t_speaker  — GPIO rising edge on AUDIO_LOOPBACK_PIN
  t_click    — scheduled play time of this click (seconds into buffer)

timing_error_ms = (t_speaker - t_buffer - t_click) * 1000
  constant part  = ALSA pipeline delay
  variation      = jitter — what actually matters for the experiment

Run with the main server STOPPED (this script owns GPIO setup/cleanup).
Wire line-out left channel → BCM pin AUDIO_LOOPBACK_PIN via 10kΩ series resistor.

Usage:
    python3 debug/latency_measure.py [--n 500] [--rate 40] [--dur 1.0] [--iti 0.5]
    python3 debug/latency_measure.py --out output/myrun.csv
"""

import argparse
import csv
import os
import sys
import threading
import time
from datetime import datetime

import numpy as np

# Add RPi_main to path so we can import gpio_handler, actions, config, audio
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import gpio_handler
import actions as _actions
from config import AUDIO_LOOPBACK_PIN

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _poisson_train(rate: float, duration: float, rng, min_ici: float) -> list:
    if rate <= 0:
        return []
    clicks, t, last_t = [], 0.0, float("-inf")
    while True:
        t += rng.exponential(1.0 / rate)
        t = max(t, last_t + min_ici)
        if t >= duration:
            break
        clicks.append(round(float(t), 4))
        last_t = t
    return clicks


def run(n_trials: int, click_rate: float, duration: float,
        iti_s: float, csv_path: str) -> None:

    gpio_handler.setup()

    min_ici   = 0.003
    all_rows  = []
    _buf_ts   = [None]
    buf_ready = threading.Event()
    _spk_edges: list = []

    def on_latency(_t_sched: float, t_buffer: float) -> None:
        _buf_ts[0] = t_buffer
        buf_ready.set()

    def on_speaker(_ch) -> None:
        _spk_edges.append(time.clock_gettime(time.CLOCK_MONOTONIC))

    gpio_handler.setup_loopback_monitor(on_speaker)
    rng = np.random.default_rng()

    print(f"Starting: {n_trials} trials  rate={click_rate:.0f} Hz  "
          f"dur={duration:.1f} s  iti={iti_s:.1f} s")
    print(f"Output → {csv_path}\n")

    try:
        for i in range(n_trials):
            del _spk_edges[:]
            _buf_ts[0] = None
            buf_ready.clear()

            left_clicks = _poisson_train(click_rate, duration, rng, min_ici)
            if not left_clicks:
                continue

            _actions._play_clicks(left_clicks, [], latency_cb=on_latency)

            if not buf_ready.wait(timeout=2.0):
                print(f"  Trial {i:4d}: TIMEOUT waiting for buffer write — skipping")
                time.sleep(iti_s)
                continue

            time.sleep(duration + 0.15)   # wait for entire train to play out

            t_buf     = _buf_ts[0]
            edges     = sorted(_spk_edges[:])
            n_sch     = len(left_clicks)
            n_edge    = len(edges)
            n_matched = min(n_sch, n_edge)

            if n_edge != n_sch:
                print(f"  Trial {i:4d}: {n_sch} clicks but {n_edge} edges "
                      "(check loopback signal level)")

            trial_errors = []
            for k in range(n_matched):
                err = (edges[k] - t_buf - left_clicks[k]) * 1000.0
                trial_errors.append(err)
                all_rows.append({
                    "trial":           i,
                    "click_idx":       k,
                    "t_click":         left_clicks[k],
                    "t_buffer":        t_buf,
                    "t_speaker":       edges[k],
                    "timing_error_ms": err,
                })

            if trial_errors:
                mean_e = sum(trial_errors) / len(trial_errors)
                std_e  = (sum((e - mean_e) ** 2 for e in trial_errors)
                          / len(trial_errors)) ** 0.5
                print(f"  Trial {i:4d}: {n_matched:3d}/{n_sch:3d} clicks  "
                      f"mean={mean_e:7.2f} ms  std={std_e:.3f} ms")

            time.sleep(iti_s)

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        gpio_handler.remove_loopback_monitor()
        gpio_handler.cleanup()

    if not all_rows:
        print("No valid data recorded.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    errors  = [r["timing_error_ms"] for r in all_rows]
    n       = len(errors)
    mean_e  = sum(errors) / n
    std_e   = (sum((e - mean_e) ** 2 for e in errors) / n) ** 0.5
    s_err   = sorted(errors)
    print(f"\nDone: {n} clicks across {n_trials} trials")
    print(f"  timing_error  mean={mean_e:.2f} ms  std={std_e:.3f} ms  "
          f"p5={s_err[int(0.05*n)]:.2f} ms  p95={s_err[int(0.95*n)]:.2f} ms")
    print(f"Saved → {csv_path}")


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = os.path.join(OUTPUT_DIR, f"latency_{ts}.csv")

    p = argparse.ArgumentParser(description="Audio loopback latency measurement")
    p.add_argument("--n",    type=int,   default=500,            help="Number of trials (default: 500)")
    p.add_argument("--rate", type=float, default=40.0,           help="Click rate Hz, left ch only (default: 40)")
    p.add_argument("--dur",  type=float, default=1.0,            help="Train duration s (default: 1.0)")
    p.add_argument("--iti",  type=float, default=0.5,            help="ITI s (default: 0.5)")
    p.add_argument("--out",  default=default_out,                help="Output CSV path")
    args = p.parse_args()

    run(args.n, args.rate, args.dur, args.iti, args.out)


if __name__ == "__main__":
    main()
