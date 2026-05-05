"""
Audio click timing visualiser — PREEMPT_RT software measurement.

Key quantities (all in ms):
  timing_error_ms  = (t_dac − t_play − t_click) * 1000
  onset_delay_ms   = (first block DAC time − t_play) * 1000   [per trial, same for all clicks]
  within_trial_jitter_ms = timing_error_ms − onset_delay_ms   [sample-clock precision]

  t_dac is derived from outputBufferDacTime converted to CLOCK_MONOTONIC inside
  the sounddevice callback; no GPIO hardware is required.

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

    # onset_delay_ms is identical for all clicks in a trial — take first per trial
    trial_onset = df.groupby("trial")["onset_delay_ms"].first()
    onset_std   = trial_onset.std()

    df["within_trial_jitter_ms"] = df["timing_error_ms"] - df["onset_delay_ms"]

    fig = plt.figure(figsize=(15, 11))
    fig.suptitle(
        f"Click timing determinism (PREEMPT_RT, software DAC timestamp)  —  "
        f"{n_clicks} clicks, {n_trials} trials\n"
        f"Overall timing_error:  median {med:.3f} ms   std {std:.3f} ms   "
        f"5–95 pct [{p5:.3f}, {p95:.3f}] ms",
        fontsize=12, fontweight="bold",
    )
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.55, wspace=0.38)

    C_ERR   = "#e15759"
    C_ONSET = "#4e79a7"
    C_JITT  = "#f28e2b"
    bins = min(80, max(20, n_clicks // 30))

    # Panel 1 — all-click timing error histogram
    ax = fig.add_subplot(gs[0, 0])
    ax.hist(err, bins=bins, color=C_ERR, alpha=0.85, edgecolor="white", linewidth=0.3)
    ax.axvline(med, color="black", linewidth=1.2, linestyle="--", label=f"median {med:.3f} ms")
    ax.set_xlabel("timing_error_ms")
    ax.set_ylabel("Count")
    ax.set_title(f"All clicks: timing error\nstd = {std:.3f} ms", fontsize=9)
    ax.legend(fontsize=8)

    # Panel 2 — per-trial onset delay (pipeline delay trial-to-trial variation)
    ax = fig.add_subplot(gs[0, 1])
    ax.hist(trial_onset.values, bins=min(40, n_trials), color=C_ONSET, alpha=0.85,
            edgecolor="white", linewidth=0.3)
    ax.axvline(trial_onset.median(), color="black", linewidth=1.2, linestyle="--",
               label=f"median {trial_onset.median():.2f} ms")
    ax.set_xlabel("onset_delay_ms (per trial)")
    ax.set_ylabel("Count")
    ax.set_title(f"Pipeline delay per trial\nstd = {onset_std:.4f} ms  (onset jitter)", fontsize=9)
    ax.legend(fontsize=8)

    # Panel 3 — within-trial jitter (sample-clock precision)
    ax = fig.add_subplot(gs[0, 2])
    wj     = df["within_trial_jitter_ms"]
    wj_std = wj.std()
    ax.hist(wj, bins=bins, color=C_JITT, alpha=0.85, edgecolor="white", linewidth=0.3)
    ax.axvline(0, color="black", linewidth=1.0, linestyle="--")
    ax.set_xlabel("within_trial_jitter_ms")
    ax.set_ylabel("Count")
    ax.set_title(f"Within-trial jitter\nstd = {wj_std:.4f} ms  ← sample-clock precision", fontsize=9)

    # Panel 4 — timing error over time (drift check)
    ax = fig.add_subplot(gs[1, 0])
    ax.plot(err.values, color=C_ERR, alpha=0.3, linewidth=0.4)
    roll_w = max(10, n_clicks // 50)
    ax.plot(err.rolling(roll_w, center=True, min_periods=1).median().values,
            color=C_ERR, linewidth=1.4, label=f"rolling median (w={roll_w})")
    ax.set_xlabel("Click index (all trials concatenated)")
    ax.set_ylabel("timing_error_ms")
    ax.set_title("Timing error over time (drift check)", fontsize=9)
    ax.legend(fontsize=8)

    # Panel 5 — within-trial jitter vs click position
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

    # Panel 6 — timing error vs scheduled click time (buffer drift)
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

    # Summary table
    ax = fig.add_subplot(gs[2, :])
    ax.axis("off")
    summary = (
        f"{'Quantity':<50}  {'Value':>12}\n"
        f"{'─'*65}\n"
        f"{'Total clicks measured':<50}  {n_clicks:>12d}\n"
        f"{'Trials':<50}  {n_trials:>12d}\n"
        f"{'Clicks per trial (mean)':<50}  {n_clicks/n_trials:>12.1f}\n"
        f"{'─'*65}\n"
        f"{'ALSA pipeline delay (median onset_delay_ms)':<50}  {trial_onset.median():>11.2f} ms\n"
        f"{'Onset jitter — trial-to-trial std':<50}  {onset_std:>11.4f} ms\n"
        f"{'Within-trial jitter — std (sample clock)':<50}  {wj_std:>11.4f} ms\n"
        f"{'Overall timing_error std (all sources)':<50}  {std:>11.4f} ms\n"
        f"{'5–95th pct range':<50}  [{p5:.3f}, {p95:.3f}] ms\n"
        f"{'─'*65}\n"
        f"{'Measurement method':<50}  {'outputBufferDacTime → CLOCK_MONOTONIC':>12}\n"
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
