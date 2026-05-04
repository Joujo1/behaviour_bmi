"""
GPS-PPS clock drift analysis with post-hoc piecewise-linear correction.

Four-panel output:
  1. Cumulative drift (raw)
  2. Drift rate over time (per-pulse + 60-s rolling mean)
  3. Residuals after global linear-drift removal
  4. Residuals after 60-s piecewise-linear correction

Outage-aware: GPS dropouts (where seq advances but the realtime stamp
jumps multiple seconds) are masked from the analysis but reported
in the title.

Can be:
  (a) imported by monitor_clock.py — call `analyse()` then `plot()`
  (b) run standalone on a CSV file:
      python3 clock_plot.py output/clock_drift_<timestamp>.csv
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


OUTAGE_THRESHOLD_S = 1.5   # pps_rt step larger than this = GPS outage
CALIB_INTERVAL_S   = 60.0  # piecewise calibration window
ROLLING_S          = 60.0  # rolling-mean window for panel 2


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

@dataclass
class Result:
    t_h:              np.ndarray   # GPS elapsed time, hours
    drift_ms:         np.ndarray   # mono − GPS elapsed, ms
    drift_fit_ms:     np.ndarray   # global linear fit
    drift_rate_ppm:   np.ndarray   # per-pulse instantaneous rate
    rolling_ppm:      np.ndarray   # 60-s rolling mean of drift rate
    resid_global_us:  np.ndarray   # residual after global linear fit
    resid_piece_us:   np.ndarray   # residual after 60-s piecewise correction
    drift_ppm:        float        # global drift rate
    n_outages:        int
    s_lost:           float        # total seconds masked


def analyse(pps_rt_ns: np.ndarray,
            mono_ns:   np.ndarray,
            seq:       np.ndarray) -> Result:
    """Compute drift, residuals, and piecewise-corrected residuals.

    Inputs are arrays from pps_log (one entry per GPS second).
    """
    pps_rt_ns = np.asarray(pps_rt_ns, dtype=np.float64)
    mono_ns   = np.asarray(mono_ns,   dtype=np.float64)
    seq       = np.asarray(seq,       dtype=np.int64)

    # ---- Detect outages: pps_rt jumps > 1.5 s while seq increments ----
    d_pps_rt_s = np.diff(pps_rt_ns) / 1e9
    outage_mask_diff = d_pps_rt_s > OUTAGE_THRESHOLD_S
    n_outages = int(outage_mask_diff.sum())
    s_lost    = float(d_pps_rt_s[outage_mask_diff].sum() - n_outages) if n_outages else 0.0

    # Build keep-mask (length N): drop the pulse AFTER each outage
    keep = np.ones(len(seq), dtype=bool)
    keep[1:][outage_mask_diff] = False

    pps_rt_ns = pps_rt_ns[keep]
    mono_ns   = mono_ns[keep]
    seq       = seq[keep]

    # ---- GPS-truth elapsed and CLOCK_MONOTONIC elapsed ----
    # Use seq as ground truth (each step = 1 s exactly)
    gps_elapsed_s   = (seq - seq[0]).astype(np.float64)
    mono_elapsed_ns = mono_ns - mono_ns[0]
    drift_ms        = (mono_elapsed_ns - gps_elapsed_s * 1e9) / 1e6
    t_s             = gps_elapsed_s

    # ---- Global linear fit ----
    a, b = np.polyfit(t_s, drift_ms, 1)            # ms per s, ms
    drift_fit_ms = a * t_s + b
    drift_ppm    = a * 1000.0                      # ms/s -> µs/ms = ppm
    resid_global_us = (drift_ms - drift_fit_ms) * 1000.0

    # ---- Instantaneous drift rate (per-pulse, with safe diff) ----
    # ds_mono / ds_gps − 1, in ppm
    dt_mono_ns = np.diff(mono_ns)
    dt_gps_ns  = np.diff(seq).astype(np.float64) * 1e9
    inst_ppm   = (dt_mono_ns - dt_gps_ns) / dt_gps_ns * 1e6
    inst_ppm   = np.concatenate([[inst_ppm[0]], inst_ppm])  # pad to len(t_s)

    # Rolling mean (~60 s window)
    win = max(int(round(ROLLING_S)), 1)
    if len(inst_ppm) >= win:
        kernel = np.ones(win) / win
        rolling_ppm = np.convolve(inst_ppm, kernel, mode="same")
    else:
        rolling_ppm = inst_ppm.copy()

    # ---- 60-s piecewise-linear correction ----
    # For each calibration window, fit drift_ms = a_k * t + b_k locally.
    # Corrected residual = drift_ms − local_fit.
    resid_piece_us = np.zeros_like(drift_ms)
    n = len(t_s)
    i = 0
    while i < n:
        # find end-index of this window
        j = i
        while j < n and t_s[j] - t_s[i] < CALIB_INTERVAL_S:
            j += 1
        if j - i < 2:                              # < 2 points → can't fit
            resid_piece_us[i:j] = 0.0
            i = j
            continue
        a_k, b_k = np.polyfit(t_s[i:j], drift_ms[i:j], 1)
        local_fit = a_k * t_s[i:j] + b_k
        resid_piece_us[i:j] = (drift_ms[i:j] - local_fit) * 1000.0
        i = j

    return Result(
        t_h             = t_s / 3600.0,
        drift_ms        = drift_ms,
        drift_fit_ms    = drift_fit_ms,
        drift_rate_ppm  = inst_ppm,
        rolling_ppm     = rolling_ppm,
        resid_global_us = resid_global_us,
        resid_piece_us  = resid_piece_us,
        drift_ppm       = drift_ppm,
        n_outages       = n_outages,
        s_lost          = s_lost,
    )


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot(r: Result, out_png: str | Path) -> None:
    out_png = Path(out_png)

    fig = plt.figure(figsize=(12, 13))
    title = "CLOCK_MONOTONIC drift vs GPS (PPS)"
    if r.n_outages:
        title += f"  —  {r.n_outages} outage(s) masked ({r.s_lost:.0f} s lost)"
    fig.suptitle(title, fontsize=14, fontweight="bold")

    gs = gridspec.GridSpec(4, 1, hspace=0.55)

    # ---- Panel 1: cumulative drift ----
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(r.t_h, r.drift_ms, linewidth=1.2, label="measured")
    ax1.plot(r.t_h, r.drift_fit_ms, color="red", linewidth=1.2, linestyle="--",
             label=f"linear fit  {r.drift_ppm:+.3f} ppm  "
                   f"({r.drift_ppm * 86.400:+.1f} ms/24 h)")
    ax1.set_xlabel("GPS elapsed time (hours)")
    ax1.set_ylabel("MONO − GPS elapsed (ms)")
    ax1.set_title("Cumulative clock drift")
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    # ---- Panel 2: drift rate over time ----
    ax2 = fig.add_subplot(gs[1])
    ax2.plot(r.t_h, r.drift_rate_ppm, color="lightgrey", linewidth=0.6,
             label="per-pulse")
    ax2.plot(r.t_h, r.rolling_ppm, color="crimson", linewidth=1.4,
             label=f"{int(ROLLING_S)}-s rolling mean")
    ax2.axhline(r.drift_ppm, color="black", linewidth=0.8, linestyle="--",
                label=f"global fit ({r.drift_ppm:+.3f} ppm)")
    ax2.set_xlabel("GPS elapsed time (hours)")
    ax2.set_ylabel("Instantaneous drift rate (ppm)")
    ax2.set_title("Drift rate over time  (non-stationarity = temperature dependence)")
    # Clip y-axis to a sensible band around the rolling mean to suppress per-pulse outliers
    if len(r.rolling_ppm):
        lo = np.percentile(r.rolling_ppm, 1) - 1
        hi = np.percentile(r.rolling_ppm, 99) + 1
        ax2.set_ylim(lo, hi)
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)

    # ---- Panel 3: global-fit residuals ----
    ax3 = fig.add_subplot(gs[2])
    ax3.plot(r.t_h, r.resid_global_us, linewidth=1.0, color="orange")
    ax3.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax3.fill_between(r.t_h, r.resid_global_us, alpha=0.2, color="orange")
    ax3.set_xlabel("GPS elapsed time (hours)")
    ax3.set_ylabel("Residual (µs)")
    ax3.set_title(f"Residuals after GLOBAL linear-drift removal  "
                  f"(std = {r.resid_global_us.std():.2f} µs  ← dominated by thermal hump)")
    ax3.grid(True, alpha=0.3)

    # ---- Panel 4: 60-s piecewise residuals ----
    ax4 = fig.add_subplot(gs[3])
    ax4.plot(r.t_h, r.resid_piece_us, linewidth=1.0, color="seagreen")
    ax4.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax4.fill_between(r.t_h, r.resid_piece_us, alpha=0.2, color="seagreen")
    ax4.set_xlabel("GPS elapsed time (hours)")
    ax4.set_ylabel("Residual (µs)")
    ax4.set_title(f"Residuals after {int(CALIB_INTERVAL_S)}-s PIECEWISE-LINEAR correction  "
                  f"(std = {r.resid_piece_us.std():.2f} µs,  max = "
                  f"{np.abs(r.resid_piece_us).max():.1f} µs  ← effective alignment error)")
    ax4.grid(True, alpha=0.3)

    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    print(f"Plot saved → {out_png}")
    print(f"Drift rate                  : {r.drift_ppm:+.3f} ppm  "
          f"({r.drift_ppm * 86.4:+.1f} ms/24 h)")
    print(f"Global-fit residual std     : {r.resid_global_us.std():.2f} µs")
    print(f"60-s piecewise residual std : {r.resid_piece_us.std():.2f} µs  "
          f"(max = {np.abs(r.resid_piece_us).max():.1f} µs)")
    print(f"Improvement factor          : "
          f"{r.resid_global_us.std() / max(r.resid_piece_us.std(), 1e-9):.1f}×")
    plt.show()


# ---------------------------------------------------------------------------
# Standalone CSV runner
# ---------------------------------------------------------------------------

def _load_csv(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load a CSV produced by monitor_clock.py."""
    import csv
    pps_rt, mono, seq = [], [], []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            pps_rt.append(int(row["pps_realtime_ns"]))
            mono.append(int(row["monotonic_ns"]))
            seq.append(int(row["seq"]))
    return (np.array(pps_rt, dtype=np.int64),
            np.array(mono,   dtype=np.int64),
            np.array(seq,    dtype=np.int64))


def _load_txt(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load the legacy 3-column whitespace format from raw pps_log stdout."""
    pps_rt, mono, seq = [], [], []
    with path.open() as f:
        f.readline()  # header
        for line in f:
            parts = line.split()
            if len(parts) != 3:
                continue
            pps_rt.append(int(parts[0]))
            mono.append(int(parts[1]))
            seq.append(int(parts[2]))
    return (np.array(pps_rt, dtype=np.int64),
            np.array(mono,   dtype=np.int64),
            np.array(seq,    dtype=np.int64))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    in_path = Path(sys.argv[1])
    if not in_path.is_file():
        print(f"ERROR: {in_path} not found")
        sys.exit(1)

    if in_path.suffix.lower() == ".csv":
        pps_rt, mono, seq = _load_csv(in_path)
    else:
        pps_rt, mono, seq = _load_txt(in_path)

    print(f"Loaded {len(seq)} pulses from {in_path}")
    r = analyse(pps_rt, mono, seq)
    out_png = in_path.with_suffix(".png")
    plot(r, out_png)