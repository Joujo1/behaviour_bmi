"""
GPS-PPS clock drift analyser — post-hoc plotting companion to monitor_clock.py.

Reads the CSV written by monitor_clock.py (or a raw pps_log.txt file) and produces
a three-panel figure:
  1. Cumulative CLOCK_MONOTONIC drift vs GPS truth
  2. Instantaneous drift rate (ppm) with 60-s rolling mean
  3. Residuals after linear drift removal — shows noise floor of the PPS measurement

GPS outages (gaps where PPS pulses stopped) are detected and masked before fitting
so the drift rate is not distorted by recovery transients.

Usage:
    python3 debug/clock_plot.py output/clock_drift_20260504_120000.csv
    python3 debug/clock_plot.py output/clock_drift_20260504_120000.csv --out output/clock_drift.png

Also accepts raw pps_log.txt format (3-column: pps_realtime_ns  monotonic_ns  seq).
"""

import argparse
import os

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
OUTAGE_THRESHOLD_S = 1.5   # PPS gap longer than this = GPS outage
ROLLING_WINDOW     = 60    # seconds for instantaneous drift rate smoothing


def load(path: str):
    """Load either a monitor_clock CSV or a raw pps_log.txt into arrays."""
    pps_rt, mono, seq = [], [], []
    with open(path) as f:
        header = f.readline()
        is_csv = "elapsed_s" in header or "timing" in header
        for line in f:
            # Handle both comma-separated (monitor_clock CSV) and space-separated (pps_log.txt)
            parts = line.replace(",", " ").split()
            if len(parts) < 3:
                continue
            try:
                pps_rt.append(int(parts[0]))
                mono.append(int(parts[1]))
                seq.append(int(parts[2]))
            except ValueError:
                continue
    return (np.array(pps_rt, dtype=np.int64),
            np.array(mono,   dtype=np.int64),
            np.array(seq,    dtype=np.int64))


def analyse(pps_rt: np.ndarray, mono: np.ndarray, seq: np.ndarray) -> dict:
    d_pps_rt_s = np.diff(pps_rt) / 1e9
    d_mono_ns  = np.diff(mono.astype(np.float64))
    d_seq      = np.diff(seq)

    good = d_pps_rt_s < OUTAGE_THRESHOLD_S

    outage_idx       = np.where(~good)[0]
    n_outages        = outage_idx.size
    outage_durations = d_pps_rt_s[outage_idx] - 1.0
    total_outage_s   = outage_durations.sum() if n_outages else 0.0
    n_seq_drops      = int(np.sum(d_seq > 1))

    # Cumulative drift — only accumulate on clean intervals
    drift_increments_ns = np.where(good, d_mono_ns - 1e9, 0.0)
    time_increments_s   = np.where(good, 1.0, 0.0)
    drift_cum_ms = np.concatenate([[0.0], np.cumsum(drift_increments_ns)]) / 1e6
    t_clean_s    = np.concatenate([[0.0], np.cumsum(time_increments_s)])

    # Linear fit on clean data
    a, b       = np.polyfit(t_clean_s, drift_cum_ms, 1)
    drift_ppm  = a * 1e3
    fit_ms     = a * t_clean_s + b
    resid_us   = (drift_cum_ms - fit_ms) * 1e3

    # Per-pulse instantaneous drift rate
    per_pulse_ppm = np.where(good, (d_mono_ns - 1e9) / 1e3, np.nan)
    rolling_ppm   = _rolling_mean(per_pulse_ppm, ROLLING_WINDOW)
    t_pulse_h     = t_clean_s[1:] / 3600.0

    return {
        "t_clean_s":      t_clean_s,
        "t_clean_h":      t_clean_s / 3600.0,
        "drift_cum_ms":   drift_cum_ms,
        "fit_ms":         fit_ms,
        "resid_us":       resid_us,
        "drift_ppm":      drift_ppm,
        "drift_ns_per_s": a * 1e6,
        "drift_ms_per_24h": a * 86400,
        "resid_std_us":   resid_us.std(),
        "per_pulse_ppm":  per_pulse_ppm,
        "rolling_ppm":    rolling_ppm,
        "t_pulse_h":      t_pulse_h,
        "n_outages":      n_outages,
        "outage_durations": outage_durations,
        "total_outage_s": total_outage_s,
        "n_seq_drops":    n_seq_drops,
        "n_samples":      len(seq),
    }


def _rolling_mean(x: np.ndarray, w: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=np.float64)
    for i in range(len(x) - w + 1):
        chunk = x[i:i + w]
        valid = ~np.isnan(chunk)
        if valid.sum() >= w // 2:
            out[i + w // 2] = chunk[valid].mean()
    return out


def plot(r: dict, out_path: str | None = None) -> None:
    title = "CLOCK_MONOTONIC drift vs GPS-PPS"
    if r["n_outages"]:
        title += (f"  —  {r['n_outages']} GPS outage"
                  f"{'s' if r['n_outages'] != 1 else ''} "
                  f"masked ({r['total_outage_s']:.0f} s lost)")

    fig = plt.figure(figsize=(12, 11))
    fig.suptitle(title, fontsize=13, fontweight="bold")
    gs = gridspec.GridSpec(3, 1, hspace=0.48)

    # Panel 1 — cumulative drift
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(r["t_clean_h"], r["drift_cum_ms"], linewidth=1.4, color="#1f77b4",
             label="measured")
    ax1.plot(r["t_clean_h"], r["fit_ms"], color="red", linewidth=1.2,
             linestyle="--",
             label=f"linear fit  {r['drift_ppm']:+.3f} ppm  "
                   f"({r['drift_ms_per_24h']:+.1f} ms/24 h)")
    ax1.set_xlabel("GPS elapsed time (hours)")
    ax1.set_ylabel("MONO − GPS elapsed (ms)")
    ax1.set_title("Cumulative clock drift")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    # Panel 2 — instantaneous drift rate
    ax2 = fig.add_subplot(gs[1])
    ax2.plot(r["t_pulse_h"], r["per_pulse_ppm"],
             linewidth=0.4, color="#cccccc", label="per-pulse")
    ax2.plot(r["t_pulse_h"], r["rolling_ppm"],
             linewidth=1.6, color="#d62728",
             label=f"{ROLLING_WINDOW}-s rolling mean")
    ax2.axhline(r["drift_ppm"], color="black", linestyle="--", linewidth=0.9,
                label=f"global fit ({r['drift_ppm']:+.3f} ppm)")
    ax2.set_xlabel("GPS elapsed time (hours)")
    ax2.set_ylabel("Instantaneous drift rate (ppm)")
    ax2.set_title("Drift rate over time  (non-stationarity = temperature dependence)")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)
    ymid  = r["drift_ppm"]
    yspan = max(2.0, 4 * np.nanstd(r["rolling_ppm"]))
    ax2.set_ylim(ymid - yspan, ymid + yspan)

    # Panel 3 — residuals
    ax3 = fig.add_subplot(gs[2])
    ax3.plot(r["t_clean_h"], r["resid_us"], linewidth=0.9, color="orange")
    ax3.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax3.fill_between(r["t_clean_h"], r["resid_us"], alpha=0.2, color="orange")
    ax3.set_xlabel("GPS elapsed time (hours)")
    ax3.set_ylabel("Residual (µs)")
    ax3.set_title(f"Residuals after linear-drift removal  "
                  f"(std = {r['resid_std_us']:.2f} µs  ← PPS noise floor)")
    ax3.grid(True, alpha=0.3)

    if out_path:
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Saved → {out_path}")

    plt.show()


def main():
    p = argparse.ArgumentParser(description="GPS-PPS clock drift analyser")
    p.add_argument("csv", help="CSV from monitor_clock.py or raw pps_log.txt")
    p.add_argument("--out", default=None,
                   help="Output PNG path (default: same name as CSV with .png)")
    args = p.parse_args()

    pps_rt, mono, seq = load(args.csv)
    print(f"Loaded {len(seq)} pulses from {args.csv}")

    r = analyse(pps_rt, mono, seq)

    print(f"Samples          : {r['n_samples']}")
    print(f"GPS outages      : {r['n_outages']}  "
          f"(total {r['total_outage_s']:.1f} s lost)")
    print(f"Seq drops        : {r['n_seq_drops']}")
    print(f"Drift rate       : {r['drift_ppm']:+.3f} ppm  "
          f"({r['drift_ns_per_s']:+.3f} ns/s)")
    print(f"Over 24 h        : {r['drift_ms_per_24h']:+.1f} ms")
    print(f"Residual std     : {r['resid_std_us']:.2f} µs")

    out = args.out or args.csv.replace(".csv", ".png").replace(".txt", ".png")
    plot(r, out)


if __name__ == "__main__":
    main()
