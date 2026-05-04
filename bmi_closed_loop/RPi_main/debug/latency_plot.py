"""
Audio loopback latency visualiser — per-click timing error analysis.

The key quantity is timing_error_ms = (t_speaker - t_buffer - t_click) * 1000
  - t_buffer  : CLOCK_MONOTONIC just before the first stream.write()
  - t_click   : scheduled play time of this click (seconds into the buffer)
  - t_speaker : CLOCK_MONOTONIC of the GPIO rising edge

If ALSA is perfectly deterministic, timing_error_ms is identical for every
click in every trial. Any spread in the distribution IS the click jitter.

Usage:
    python3 debug/latency_plot.py output/latency_20260504_120000.csv
    python3 debug/latency_plot.py output/latency_20260504_120000.csv --out output/latency.png
"""

import argparse

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    n_clicks = len(df)
    n_trials  = df["trial"].nunique()
    print(f"Loaded {n_clicks} clicks across {n_trials} trials from {args.csv}")

    err = df["timing_error_ms"]
    med = err.median()
    std = err.std()
    p5, p95 = np.percentile(err, [5, 95])

    trial_offset = df.groupby("trial")["timing_error_ms"].mean().rename("alsa_offset_ms")
    df = df.join(trial_offset, on="trial")
    df["within_trial_jitter_ms"] = df["timing_error_ms"] - df["alsa_offset_ms"]

    fig = plt.figure(figsize=(15, 11))
    fig.suptitle(
        f"Click timing determinism  —  {n_clicks} clicks, {n_trials} trials\n"
        f"Overall timing_error:  median {med:.2f} ms   std {std:.2f} ms   "
        f"5–95 pct [{p5:.2f}, {p95:.2f}] ms",
        fontsize=12, fontweight="bold",
    )
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.55, wspace=0.38)

    C_ERR   = "#e15759"
    C_ONSET = "#4e79a7"
    C_JITT  = "#f28e2b"
    bins = min(80, max(20, n_clicks // 30))

    ax = fig.add_subplot(gs[0, 0])
    ax.hist(err, bins=bins, color=C_ERR, alpha=0.85, edgecolor="white", linewidth=0.3)
    ax.axvline(med, color="black", linewidth=1.2, linestyle="--", label=f"median {med:.2f} ms")
    ax.set_xlabel("timing_error_ms")
    ax.set_ylabel("Count")
    ax.set_title(f"All clicks: timing error\nstd = {std:.2f} ms", fontsize=9)
    ax.legend(fontsize=8)

    ax = fig.add_subplot(gs[0, 1])
    t_off = trial_offset.values
    onset_std = np.std(t_off)
    ax.hist(t_off, bins=min(40, n_trials), color=C_ONSET, alpha=0.85,
            edgecolor="white", linewidth=0.3)
    ax.axvline(np.median(t_off), color="black", linewidth=1.2, linestyle="--",
               label=f"median {np.median(t_off):.2f} ms")
    ax.set_xlabel("Mean timing_error per trial (ms)")
    ax.set_ylabel("Count")
    ax.set_title(f"Per-trial ALSA onset offset\nstd = {onset_std:.3f} ms (startup jitter)", fontsize=9)
    ax.legend(fontsize=8)

    ax = fig.add_subplot(gs[0, 2])
    wj = df["within_trial_jitter_ms"]
    wj_std = wj.std()
    ax.hist(wj, bins=bins, color=C_JITT, alpha=0.85, edgecolor="white", linewidth=0.3)
    ax.axvline(0, color="black", linewidth=1.0, linestyle="--")
    ax.set_xlabel("within_trial_jitter_ms")
    ax.set_ylabel("Count")
    ax.set_title(f"Within-trial jitter\nstd = {wj_std:.3f} ms  ← sample-clock precision", fontsize=9)

    ax = fig.add_subplot(gs[1, 0])
    ax.plot(err.values, color=C_ERR, alpha=0.3, linewidth=0.4)
    roll_w = max(10, n_clicks // 50)
    ax.plot(err.rolling(roll_w, center=True, min_periods=1).median().values,
            color=C_ERR, linewidth=1.4, label=f"rolling median (w={roll_w})")
    ax.set_xlabel("Click index (all trials concatenated)")
    ax.set_ylabel("timing_error_ms")
    ax.set_title("Timing error over time (drift check)", fontsize=9)
    ax.legend(fontsize=8)

    ax = fig.add_subplot(gs[1, 1])
    ax.scatter(df["click_idx"], df["within_trial_jitter_ms"],
               alpha=0.15, s=2, color=C_JITT, rasterized=True)
    grp = df.groupby("click_idx")["within_trial_jitter_ms"]
    ax.plot(grp.median().index, grp.median().values,
            color="black", linewidth=1.2, label="median per click position")
    ax.axhline(0, color="grey", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Click index within trial")
    ax.set_ylabel("within_trial_jitter_ms")
    ax.set_title("Jitter vs. position in train\n(early vs. late clicks)", fontsize=9)
    ax.legend(fontsize=8)

    ax = fig.add_subplot(gs[1, 2])
    ax.scatter(df["t_click"] * 1000, df["timing_error_ms"],
               alpha=0.15, s=2, color=C_ERR, rasterized=True)
    df["t_click_ms"] = df["t_click"] * 1000
    bins_t = np.arange(0, df["t_click_ms"].max() + 50, 50)
    df["t_bin"] = pd.cut(df["t_click_ms"], bins=bins_t, labels=False)
    grp2 = df.groupby("t_bin")["timing_error_ms"]
    bin_centres = bins_t[:-1] + 25
    valid = grp2.median().dropna()
    ax.plot(bin_centres[valid.index.astype(int)], valid.values,
            color="black", linewidth=1.2, label="median (50 ms bins)")
    ax.set_xlabel("Scheduled click time (ms into buffer)")
    ax.set_ylabel("timing_error_ms")
    ax.set_title("Timing error vs. scheduled time\n(drift within buffer?)", fontsize=9)
    ax.legend(fontsize=8)

    ax = fig.add_subplot(gs[2, :])
    ax.axis("off")
    summary = (
        f"{'Quantity':<45}  {'Value':>12}\n"
        f"{'─'*60}\n"
        f"{'Total clicks measured':<45}  {n_clicks:>12d}\n"
        f"{'Trials':<45}  {n_trials:>12d}\n"
        f"{'Clicks per trial (mean)':<45}  {n_clicks/n_trials:>12.1f}\n"
        f"{'─'*60}\n"
        f"{'ALSA pipeline delay (median timing_error)':<45}  {med:>11.2f} ms\n"
        f"{'Startup jitter — trial-to-trial std':<45}  {onset_std:>11.3f} ms\n"
        f"{'Within-trial jitter — std (sample clock)':<45}  {wj_std:>11.3f} ms\n"
        f"{'Overall timing_error std (all sources)':<45}  {std:>11.3f} ms\n"
        f"{'5–95th pct range':<45}  [{p5:.2f}, {p95:.2f}] ms\n"
    )
    ax.text(0.02, 0.95, summary, transform=ax.transAxes,
            fontsize=9, verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="whitesmoke", alpha=0.8))

    out = args.out or args.csv.replace(".csv", ".png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.show()


if __name__ == "__main__":
    main()
