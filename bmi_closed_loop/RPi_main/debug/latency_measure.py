"""
Audio click timing measurement — software DAC timestamp + optional oscilloscope marker.

Uses the same persistent-stream design as actions.py: one OutputStream stays open
for the entire run, outputting silence between trials.  t_play is captured just
before _active is armed, so onset_delay_ms reflects only the time until the next
period boundary (~0–10 ms) rather than ALSA cold-start (~60 ms).

Three quantities recorded per click:
  t_play         — CLOCK_MONOTONIC just before _active is armed each trial
  t_click        — scheduled play time of this click (seconds into buffer)
  t_dac          — inferred CLOCK_MONOTONIC DAC time for this click:
                     block_dac_mono[block_idx] + offset_within_block
  onset_delay_ms — (block_dac_mono[0] - t_play) * 1000: time from arming
                   to first callback serving audio (~0–10 ms with persistent stream)

  timing_error_ms = (t_dac - t_play - t_click) * 1000
    constant part  = onset_delay_ms
    variation      = within-trial jitter (sample clock precision)

Oscilloscope verification (--osci-pin):
  Fires a 400 µs GPIO pulse at each click's predicted DAC time so the scope
  can compare "software's prediction" (Ch2/GPIO) against "actual waveform" (Ch1/audio).
  Wire: BCM pin → scope Ch2 probe tip.  Pi GND → scope Ch2 ground clip.
  Export scope CSV (time, ch1_V, ch2_V) and load with latency_plot.py --osci-csv.

Usage:
    python3 debug/latency_measure.py [--n 500] [--rate 40] [--dur 1.0] [--iti 0.5]
    python3 debug/latency_measure.py --osci-pin 17 --n 100
    python3 debug/latency_measure.py --out output/myrun.csv
"""

import argparse
import ctypes
import csv
import os
import sys
import threading
import time
import queue as _queue
from datetime import datetime

import numpy as np
import sounddevice as sd

try:
    import RPi.GPIO as _GPIO
    _HAS_GPIO = True
except ImportError:
    _HAS_GPIO = False

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import audio
from config import AUDIO_DEVICE, AUDIO_SRATE, CLICK_WIDTH_S

OUTPUT_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
_CHUNK       = 512                              # must match actions._CHUNK
OSCI_PULSE_S = 0.003   # 3 ms GPIO pulse — matches click duration

# Measurement click: prepend a 200 µs full-amplitude step so the LP-filtered
# waveform has a sharp rising edge for reliable threshold detection.
# This is only used in latency_measure.py — audio.py's click is unchanged.
_CLICK = audio.build_click(srate=AUDIO_SRATE)
_N_ONSET = max(1, round(AUDIO_SRATE * 0.0002))   # 200 µs
_CLICK[:_N_ONSET] = 1.0

# Persistent stream state — mirrors actions.py exactly
_stream:  sd.OutputStream | None = None
_active:  dict | None            = None
_rt_done: list                   = [False]


def _set_rt_priority(priority: int = 85) -> None:
    SCHED_FIFO = 1
    class _Param(ctypes.Structure):
        _fields_ = [("sched_priority", ctypes.c_int)]
    ctypes.CDLL("libc.so.6").sched_setscheduler(0, SCHED_FIFO, ctypes.byref(_Param(priority)))


def _stream_callback(outdata, frames, time_info, _status) -> None:
    global _active
    if not _rt_done[0]:
        _set_rt_priority(85)
        _rt_done[0] = True

    t_now       = time.clock_gettime(time.CLOCK_MONOTONIC)
    pa_ahead    = time_info.outputBufferDacTime - time_info.currentTime
    t_dac_block = t_now + pa_ahead

    a = _active
    if a is None:
        outdata[:] = 0
        return

    block_idx = a['block_idx'][0]
    a['block_dac_mono'].append(t_dac_block)
    a['block_idx'][0] += 1

    if a['marker_q'] is not None:
        block_s = a['block_s']
        for t_c in a['left_clicks']:
            b = int(t_c / block_s)
            if b == block_idx:
                t_marker = t_dac_block + (t_c - b * block_s)
                print(f"[marker] queued click t_c={t_c:.4f} → DAC {t_marker:.4f}")
                a['marker_q'].put_nowait(t_marker)

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


def _play_and_measure(left_clicks: list, duration: float,
                      marker_q: _queue.Queue | None = None) -> tuple:
    """
    Arm the persistent stream with a new click buffer.

    Returns (t_play, block_dac_mono):
      t_play         : CLOCK_MONOTONIC just before _active is set
      block_dac_mono : per-block inferred DAC time in CLOCK_MONOTONIC seconds
    """
    global _active
    buf  = (audio.build_buffer_from_times(_CLICK, left_clicks, [], srate=AUDIO_SRATE)
            * 32767).astype('int16')
    done           = threading.Event()
    block_dac_mono: list = []

    t_play  = time.clock_gettime(time.CLOCK_MONOTONIC)
    _active = {
        'buf':            buf,
        'pos':            [0],
        'done':           done,
        'block_dac_mono': block_dac_mono,
        'block_idx':      [0],
        'marker_q':       marker_q,
        'left_clicks':    left_clicks,
        'block_s':        _CHUNK / AUDIO_SRATE,
    }
    done.wait(timeout=duration + 1.5)
    return t_play, block_dac_mono


def _marker_worker(pin: int, q: _queue.Queue) -> None:
    """
    Pull predicted DAC times from q and fire a short GPIO pulse at each one.
    Sleeps to within 1 ms then busy-waits for microsecond-level precision.
    Stopped by putting None into the queue.
    """
    print(f"[marker] worker started on BCM pin {pin}")
    _GPIO.setmode(_GPIO.BCM)
    _GPIO.setup(pin, _GPIO.OUT, initial=_GPIO.LOW)
    try:
        while True:
            t_target = q.get()
            if t_target is None:
                break
            print(f"[marker] firing pulse at {t_target:.4f}")
            slack = t_target - time.clock_gettime(time.CLOCK_MONOTONIC) - 0.001
            if slack > 0:
                time.sleep(slack)
            while time.clock_gettime(time.CLOCK_MONOTONIC) < t_target:
                pass
            _GPIO.output(pin, _GPIO.HIGH)
            time.sleep(OSCI_PULSE_S)
            _GPIO.output(pin, _GPIO.LOW)
    finally:
        _GPIO.output(pin, _GPIO.LOW)
        _GPIO.cleanup(pin)


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
        iti_s: float, csv_path: str,
        osci_pin: int | None = None) -> None:

    min_ici = CLICK_WIDTH_S * 2   # 3 ms click + 3 ms gap between end and next start
    block_s = _CHUNK / AUDIO_SRATE
    all_rows: list = []
    rng = np.random.default_rng()

    marker_q      = None
    marker_thread = None
    if osci_pin is not None:
        if not _HAS_GPIO:
            print("WARNING: RPi.GPIO not available — oscilloscope marker disabled")
        else:
            marker_q = _queue.Queue()
            marker_thread = threading.Thread(
                target=_marker_worker, args=(osci_pin, marker_q),
                daemon=True, name="osci-marker",
            )
            marker_thread.start()
            print(f"Oscilloscope marker on BCM {osci_pin}  (connect to scope Ch2)")

    # Open stream once — stays open between trials, outputting silence.
    _open_stream()

    print(f"Starting: {n_trials} trials  rate={click_rate:.0f} Hz  "
          f"dur={duration:.1f} s  iti={iti_s:.1f} s")
    print(f"Output → {csv_path}\n")

    try:
        for i in range(n_trials):
            left_clicks = _poisson_train(click_rate, duration, rng, min_ici)
            if not left_clicks:
                continue

            t_play, block_dac_mono = _play_and_measure(left_clicks, duration, marker_q)

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
    finally:
        if marker_q is not None:
            marker_q.put(None)
            if marker_thread:
                marker_thread.join(timeout=1.0)

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
    print(f"  onset_delay   mean={mean_o:.2f} ms  std={std_o:.4f} ms  (time to next period boundary)")
    print(f"Saved → {csv_path}")


def main():
    ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = os.path.join(OUTPUT_DIR, f"latency_{ts}.csv")

    p = argparse.ArgumentParser(description="Click timing measurement (persistent stream, software DAC timestamp)")
    p.add_argument("--n",        type=int,   default=500,  help="Number of trials (default: 500)")
    p.add_argument("--rate",     type=float, default=40.0, help="Click rate Hz (default: 40)")
    p.add_argument("--dur",      type=float, default=1.0,  help="Train duration s (default: 1.0)")
    p.add_argument("--iti",      type=float, default=0.5,  help="ITI s (default: 0.5)")
    p.add_argument("--out",      default=default_out,      help="Output CSV path")
    p.add_argument("--osci-pin", type=int,   default=None,
                   help="BCM pin for oscilloscope marker GPIO output (default: disabled). "
                        "Wire this pin to scope Ch2. Line-out left channel to scope Ch1.")
    args = p.parse_args()

    run(args.n, args.rate, args.dur, args.iti, args.out, osci_pin=args.osci_pin)


if __name__ == "__main__":
    main()
