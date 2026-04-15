"""
drift_logger.py — per-second Pi/PC clock drift sampler.

Records one row per second per cage:
    pc_ts  : float  — PC wall-clock at UDP receive (time.time(), Unix epoch seconds)
    pi_ts  : int    — Pi frame timestamp (microseconds; monotonic-since-boot from
                      picamera2, or Unix epoch μs as fallback — see streamer.py)
    pi_seq : int    — Pi frame counter (detects logging gaps)

Drift metric computed offline (plot_drift.py):
    delta(t)   = pc_ts * 1e6 - pi_ts        # μs, arbitrary baseline
    drift_ms(t)= (delta(t) - delta(t0)) / 1000

To remove this entirely: delete this file and the three marked lines in
acquisition_main.py (search "# DRIFT").
"""

import csv
import os


class DriftLogger:
    def __init__(self, session_dir: str, n_cages: int):
        os.makedirs(session_dir, exist_ok=True)
        self._last: dict[int, float] = {}   # cage_id → pc_ts of last logged row
        self._writers: dict[int, csv.writer] = {}
        self._files: list = []

        for cage_id in range(1, n_cages + 1):
            path = os.path.join(session_dir, f"drift_cage_{cage_id}.csv")
            f = open(path, "w", newline="", buffering=1)   # line-buffered flush
            self._files.append(f)
            w = csv.writer(f)
            w.writerow(["pc_ts", "pi_ts", "pi_seq"])
            self._writers[cage_id] = w
            self._last[cage_id] = 0.0

    def record(self, cage_id: int, pc_ts: float, pi_ts: int, pi_seq: int):
        """Call once per received frame; logs at most one row per second."""
        if pc_ts - self._last[cage_id] >= 1.0:
            self._writers[cage_id].writerow([round(pc_ts, 6), pi_ts, pi_seq])
            self._last[cage_id] = pc_ts

    def stop(self):
        for f in self._files:
            f.close()
