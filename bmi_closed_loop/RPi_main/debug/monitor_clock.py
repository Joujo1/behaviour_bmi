"""
GPS-PPS clock drift monitor — runs alongside the main server as a separate process.

Spawns the compiled pps_log binary and reads its output line by line (one line
per GPS second). Computes running CLOCK_MONOTONIC drift against GPS truth,
prints a live terminal dashboard, and writes every pulse to CSV.

On Ctrl+C: saves a final drift plot via clock_plot.py (3-panel, outage-aware).

GPS truth: each sequence increment is exactly 1 second. Any deviation of
CLOCK_MONOTONIC's elapsed time from the GPS elapsed time is clock drift.

Usage:
    python3 debug/monitor_clock.py [--pps-log debug/pps_log] [--out output/clock_drift.csv]

Build pps_log first if needed (one-time setup):
    sudo wget https://raw.githubusercontent.com/redlab-i/pps-tools/master/timepps.h -O /usr/local/include/timepps.h
    gcc -O2 -I/usr/local/include -o debug/pps_log debug/pps_log.c
"""

import argparse
import csv
import os
import signal
import subprocess
import sys
from datetime import datetime

import numpy as np

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# How often to print a live summary line (every N pulses = N seconds)
PRINT_EVERY = 10


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_pps = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "pps_log")
    default_out = os.path.join(OUTPUT_DIR, f"clock_drift_{ts}.csv")

    p = argparse.ArgumentParser(description="GPS-PPS clock drift monitor")
    p.add_argument("--pps-log", default=default_pps,
                   help="Path to compiled pps_log binary")
    p.add_argument("--out", default=default_out,
                   help="Output CSV path")
    args = p.parse_args()

    pps_bin = os.path.abspath(args.pps_log)
    if not os.path.isfile(pps_bin):
        print(f"ERROR: pps_log binary not found at {pps_bin}")
        print("Build it with:  gcc -O2 -I/usr/local/include -o debug/pps_log debug/pps_log.c")
        print("(First time: sudo wget https://raw.githubusercontent.com/redlab-i/pps-tools/master/timepps.h -O /usr/local/include/timepps.h)")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Data arrays (grow dynamically)
    pps_rt_ns_arr  = []
    mono_ns_arr    = []
    seq_arr        = []
    elapsed_s_arr  = []
    drift_ms_arr   = []

    csv_file   = open(args.out, "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["pps_realtime_ns", "monotonic_ns", "seq",
                         "elapsed_s", "drift_ms"])

    proc = subprocess.Popen(
        [pps_bin],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    print(f"pps_log PID {proc.pid} started")
    print(f"Output → {args.out}")
    print(f"{'Elapsed':>10}  {'Drift':>10}  {'Rate':>12}  {'Resid std':>10}")
    print("─" * 50)

    seq0 = mono0 = None

    def finish(signum=None, frame=None):
        proc.terminate()
        csv_file.close()
        print(f"\nStopped. {len(seq_arr)} pulses recorded → {args.out}")
        if len(seq_arr) >= 10:
            _save_plot(pps_rt_ns_arr, mono_ns_arr, seq_arr, args.out)
        sys.exit(0)

    signal.signal(signal.SIGINT,  finish)
    signal.signal(signal.SIGTERM, finish)

    try:
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line or line.startswith("pps_realtime"):
                continue   # header or blank

            parts = line.split()
            if len(parts) != 3:
                continue
            try:
                pps_rt  = int(parts[0])
                mono_ns = int(parts[1])
                seq     = int(parts[2])
            except ValueError:
                continue

            # Initialise reference on first pulse
            if seq0 is None:
                seq0  = seq
                mono0 = mono_ns

            # Detect dropped pulses
            if seq_arr and seq - seq_arr[-1] > 1:
                n_dropped = seq - seq_arr[-1] - 1
                print(f"  *** {n_dropped} dropped pulse(s) at seq {seq_arr[-1]+1}–{seq-1} ***")

            gps_elapsed_ns  = (seq - seq0) * 1_000_000_000.0
            mono_elapsed_ns = float(mono_ns - mono0)
            drift_ms        = (mono_elapsed_ns - gps_elapsed_ns) / 1_000_000.0
            elapsed_s       = gps_elapsed_ns / 1_000_000_000.0

            pps_rt_ns_arr.append(pps_rt)
            mono_ns_arr.append(mono_ns)
            seq_arr.append(seq)
            elapsed_s_arr.append(elapsed_s)
            drift_ms_arr.append(drift_ms)

            csv_writer.writerow([pps_rt, mono_ns, seq, f"{elapsed_s:.3f}",
                                  f"{drift_ms:.6f}"])
            csv_file.flush()

            n = len(drift_ms_arr)
            if n % PRINT_EVERY == 0:
                # Drift rate from last 60 pulses (or all if fewer)
                window = min(60, n)
                if window >= 2:
                    t_w = elapsed_s_arr[-window:]
                    d_w = drift_ms_arr[-window:]
                    rate_ms_per_s = np.polyfit(t_w, d_w, 1)[0]
                    rate_us_per_s = rate_ms_per_s * 1000.0
                else:
                    rate_us_per_s = float("nan")

                # Residual std after removing linear fit from all data
                if n >= 5:
                    fit = np.polyfit(elapsed_s_arr, drift_ms_arr, 1)
                    resid_us = (np.array(drift_ms_arr)
                                - np.polyval(fit, elapsed_s_arr)) * 1000.0
                    resid_std = resid_us.std()
                else:
                    resid_std = float("nan")

                h = int(elapsed_s) // 3600
                m = (int(elapsed_s) % 3600) // 60
                s = int(elapsed_s) % 60
                print(f"  {h:02d}:{m:02d}:{s:02d}  "
                      f"drift={drift_ms:+8.3f} ms  "
                      f"rate={rate_us_per_s:+7.3f} µs/s  "
                      f"resid_std={resid_std:.3f} µs")

    except Exception as e:
        print(f"Error reading pps_log: {e}")
    finally:
        finish()


def _save_plot(pps_rt_ns_arr, mono_ns_arr, seq_arr, csv_path):
    import clock_plot
    r = clock_plot.analyse(
        np.array(pps_rt_ns_arr, dtype=np.int64),
        np.array(mono_ns_arr,   dtype=np.int64),
        np.array(seq_arr,       dtype=np.int64),
    )
    out_png = csv_path.replace(".csv", ".png")
    clock_plot.plot(r, out_png)


if __name__ == "__main__":
    main()
