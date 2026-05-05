"""
Audio click timing measurement — software-only, PREEMPT_RT aware.

Uses sounddevice's outputBufferDacTime converted to CLOCK_MONOTONIC as the
physical play-time reference per callback block.  No GPIO hardware required.

Three quantities recorded per click:
  t_play         — CLOCK_MONOTONIC just before the stream opens each trial
  t_click        — scheduled play time of this click (seconds into buffer)
  t_dac          — inferred CLOCK_MONOTONIC DAC time for this click:
                     block_dac_mono[block_idx] + offset_within_block
  onset_delay_ms — (block_dac_mono[0] - t_play) * 1000: pipeline delay
                   from "I want to play" to "first sample exits DAC"

  timing_error_ms = (t_dac - t_play - t_click) * 1000
    constant part  = onset_delay_ms  (ALSA pipeline delay, varies trial-to-trial)
    variation      = within-trial jitter  (sample clock precision)

Requires PREEMPT_RT kernel.  Run with sudo for SCHED_FIFO scheduling.

Usage:
    sudo python3 debug/latency_measure.py [--n 500] [--rate 40] [--dur 1.0] [--iti 0.5]
    sudo python3 debug/latency_measure.py --out output/myrun.csv
"""

import argparse
import csv
import ctypes
import os
import sys
import threading
import time
from datetime import datetime

import numpy as np
import sounddevice as sd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import audio
from config import AUDIO_DEVICE, AUDIO_SRATE, CLICK_WIDTH_S

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

_CHUNK = 512                              # must match actions._CHUNK
_CLICK = audio.build_click(srate=AUDIO_SRATE)


def _set_rt_priority(priority: int = 80) -> bool:
    """Set SCHED_FIFO on the calling thread.  Requires PREEMPT_RT + root / CAP_SYS_NICE."""
    SCHED_FIFO = 1
    class _Param(ctypes.Structure):
        _fields_ = [("sched_priority", ctypes.c_int)]
    ret = ctypes.CDLL("libc.so.6").sched_setscheduler(0, SCHED_FIFO, ctypes.byref(_Param(priority)))
    return ret == 0


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


def _play_and_measure(left_clicks: list, duration: float) -> tuple:
    """
    Play a click buffer via a callback-based OutputStream.

    Returns (t_play, block_dac_mono):
      t_play         : CLOCK_MONOTONIC just before stream open
      block_dac_mono : per-block inferred DAC time in CLOCK_MONOTONIC seconds

    DAC time conversion:
      t_mono_now  = CLOCK_MONOTONIC at callback entry
      pa_ahead    = outputBufferDacTime - currentTime  (physical interval, PA-time-domain)
      t_dac_block = t_mono_now + pa_ahead
    """
    buf     = audio.build_buffer_from_times(_CLICK, left_clicks, [], srate=AUDIO_SRATE)
    n_total = len(buf)
    pos     = [0]
    done    = threading.Event()
    rt_done = [False]

    block_dac_mono: list = []

    def _callback(outdata, frames, time_info, _status):
        if not rt_done[0]:
            _set_rt_priority(80)
            rt_done[0] = True

        t_now    = time.clock_gettime(time.CLOCK_MONOTONIC)
        pa_ahead = time_info.outputBufferDacTime - time_info.currentTime
        block_dac_mono.append(t_now + pa_ahead)

        i   = pos[0]
        end = min(i + frames, n_total)
        got = end - i
        outdata[:got] = buf[i:end]
        outdata[got:] = 0
        pos[0] += frames

        if pos[0] >= n_total:
            done.set()
            raise sd.CallbackStop()

    t_play = time.clock_gettime(time.CLOCK_MONOTONIC)
    with sd.OutputStream(samplerate=AUDIO_SRATE, channels=2, device=AUDIO_DEVICE,
                         blocksize=_CHUNK, callback=_callback, dtype='float32'):
        done.wait(timeout=duration + 1.5)

    return t_play, block_dac_mono


def run(n_trials: int, click_rate: float, duration: float,
        iti_s: float, csv_path: str) -> None:

    rt_ok = _set_rt_priority(80)
    print(f"RT priority (main thread): {'ok' if rt_ok else 'FAILED — run as sudo on PREEMPT_RT kernel'}")

    min_ici = CLICK_WIDTH_S
    block_s = _CHUNK / AUDIO_SRATE
    all_rows: list = []
    rng = np.random.default_rng()

    print(f"Starting: {n_trials} trials  rate={click_rate:.0f} Hz  "
          f"dur={duration:.1f} s  iti={iti_s:.1f} s")
    print(f"Output → {csv_path}\n")

    try:
        for i in range(n_trials):
            left_clicks = _poisson_train(click_rate, duration, rng, min_ici)
            if not left_clicks:
                continue

            t_play, block_dac_mono = _play_and_measure(left_clicks, duration)

            if not block_dac_mono:
                print(f"  Trial {i:4d}: no callback blocks — skipping")
                time.sleep(iti_s)
                continue

            onset_delay_ms = (block_dac_mono[0] - t_play) * 1000.0
            trial_errors: list = []

            for k, t_click in enumerate(left_clicks):
                b = int(t_click / block_s)
                if b >= len(block_dac_mono):
                    continue
                t_dac = block_dac_mono[b] + (t_click - b * block_s)
                err   = (t_dac - t_play - t_click) * 1000.0
                trial_errors.append(err)
                all_rows.append({
                    "trial":           i,
                    "click_idx":       k,
                    "t_click":         t_click,
                    "t_play":          t_play,
                    "t_dac":           t_dac,
                    "onset_delay_ms":  onset_delay_ms,
                    "timing_error_ms": err,
                })

            if trial_errors:
                mean_e = sum(trial_errors) / len(trial_errors)
                std_e  = (sum((e - mean_e) ** 2 for e in trial_errors)
                          / len(trial_errors)) ** 0.5
                print(f"  Trial {i:4d}: {len(trial_errors):3d}/{len(left_clicks):3d} clicks  "
                      f"onset={onset_delay_ms:7.2f} ms  "
                      f"mean_err={mean_e:8.4f} ms  std={std_e:.4f} ms")

            time.sleep(iti_s)

    except KeyboardInterrupt:
        print("\nInterrupted.")

    if not all_rows:
        print("No valid data recorded.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    errors  = [r["timing_error_ms"] for r in all_rows]
    onsets  = [r["onset_delay_ms"]  for r in all_rows]
    n       = len(errors)
    mean_e  = sum(errors) / n
    std_e   = (sum((e - mean_e) ** 2 for e in errors) / n) ** 0.5
    mean_o  = sum(onsets) / len(onsets)
    std_o   = (sum((o - mean_o) ** 2 for o in onsets) / len(onsets)) ** 0.5
    s_err   = sorted(errors)

    print(f"\nDone: {n} clicks across {n_trials} trials")
    print(f"  timing_error  mean={mean_e:.4f} ms  std={std_e:.4f} ms  "
          f"p5={s_err[int(0.05*n)]:.4f} ms  p95={s_err[int(0.95*n)]:.4f} ms")
    print(f"  onset_delay   mean={mean_o:.2f} ms  std={std_o:.4f} ms  (pipeline delay)")
    print(f"Saved → {csv_path}")


def main():
    ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = os.path.join(OUTPUT_DIR, f"latency_{ts}.csv")

    p = argparse.ArgumentParser(description="Click timing measurement (PREEMPT_RT, software)")
    p.add_argument("--n",    type=int,   default=500,  help="Number of trials (default: 500)")
    p.add_argument("--rate", type=float, default=40.0, help="Click rate Hz (default: 40)")
    p.add_argument("--dur",  type=float, default=1.0,  help="Train duration s (default: 1.0)")
    p.add_argument("--iti",  type=float, default=0.5,  help="ITI s (default: 0.5)")
    p.add_argument("--out",  default=default_out,      help="Output CSV path")
    args = p.parse_args()

    run(args.n, args.rate, args.dur, args.iti, args.out)


if __name__ == "__main__":
    main()
