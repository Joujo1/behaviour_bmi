"""
Audio click timing visualiser — PREEMPT_RT software measurement + optional oscilloscope.

Key quantities (all in ms):
  timing_error_ms  = (t_dac − t_play − t_click) * 1000
  onset_delay_ms   = (first block DAC time − t_play) * 1000   [per trial]
  within_trial_jitter_ms = timing_error_ms − onset_delay_ms   [sample-clock precision]

  t_dac is derived from outputBufferDacTime converted to CLOCK_MONOTONIC inside
  the sounddevice callback; no GPIO hardware required for the software measurement.

Oscilloscope post-processing (--osci-csv):
  Loads a two-channel oscilloscope CSV (time, ch1_audio, ch2_gpio) exported after
  running latency_measure.py --osci-pin.
  Ch2 rising edges = predicted click times (GPIO marker from Pi).
  Ch1 rising edges = actual click times (audio waveform from line-out).
  delay_ms = t_ch1_edge - t_ch2_edge per click = hardware-verified ALSA latency.

  Supported CSV formats: Rigol, Siglent, Tektronix — any format where non-header
  rows are (time_s, ch1_V, ch2_V). Header rows with non-numeric first column are
  skipped automatically.

Usage:
    python3 debug/latency_plot.py output/latency_20260504_120000.csv
    python3 debug/latency_plot.py output/latency.csv --out output/latency.png
    python3 debug/latency_plot.py output/latency.csv --osci-csv output/scope.csv
"""

import argparse

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


# ── Oscilloscope CSV helpers ──────────────────────────────────────────────────

def _load_osci_csv(path: str) -> tuple:
    """
    Load a two-channel oscilloscope CSV.
    Skips any header rows where the first column is not a float.
    Returns (t, ch1, ch2) as float64 numpy arrays.
    """
    t, ch1, ch2 = [], [], []
    with open(path) as f:
        for line in f:
            parts = line.replace(";", ",").split(",")
            if len(parts) < 3:
                continue
            try:
                t.append(float(parts[0]))
                ch1.append(float(parts[1]))
                ch2.append(float(parts[2]))
            except ValueError:
                continue
    return np.array(t), np.array(ch1), np.array(ch2)


def _rising_edges(t: np.ndarray, v: np.ndarray,
                  threshold: float | None = None,
                  min_gap_s: float = 0.003) -> np.ndarray:
    """
    Return times of rising edges where v crosses threshold.
    min_gap_s debounces consecutive edges (set to min_ici = 3 ms).
    """
    if threshold is None:
        threshold = (np.nanmax(v) + np.nanmin(v)) / 2
    above = v > threshold
    idxs  = np.where(~above[:-1] & above[1:])[0]
    times, last = [], -np.inf
    for i in idxs:
        if t[i] - last >= min_gap_s:
            times.append(float(t[i]))
            last = t[i]
    return np.array(times)


def _match_edges(t_gpio: np.ndarray, t_audio: np.ndarray,
                 search_min_ms: float = 5.0,
                 search_max_ms: float = 150.0) -> tuple:
    """
    For each GPIO edge (predicted click time) find the first audio edge in
    the window [t_gpio + search_min_ms, t_gpio + search_max_ms].
    Returns (matched_gpio, matched_audio, delay_ms).
    """
    lo, hi = search_min_ms / 1000, search_max_ms / 1000
    mg, ma, delays = [], [], []
    for tg in t_gpio:
        cands = t_audio[(t_audio >= tg + lo) & (t_audio <= tg + hi)]
        if len(cands):
            mg.append(tg)
            ma.append(cands[0])
            delays.append((cands[0] - tg) * 1000)
    return np.array(mg), np.array(ma), np.array(delays)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--out",      default=None,
                        help="Output PNG path (default: same name as CSV)")
    parser.add_argument("--osci-csv", default=None,
                        help="Oscilloscope CSV (time, ch1_audio_V, ch2_gpio_V) "
                             "for hardware verification")
    parser.add_argument("--osci-ch2-thresh", type=float, default=None,
                        help="Ch2 (GPIO) threshold in V (default: auto = midpoint)")
    parser.add_argument("--osci-ch1-thresh", type=float, default=None,
                        help="Ch1 (audio) threshold in V (default: auto = 5%% of peak)")
    parser.add_argument("--osci-search-min", type=float, default=-5.0,
                        help="Search window start relative to GPIO edge, ms (default: -5)")
    parser.add_argument("--osci-search-max", type=float, default=20.0,
                        help="Search window end relative to GPIO edge, ms (default: 20)")
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    n_clicks = len(df)
    n_trials  = df["trial"].nunique()
    print(f"Loaded {n_clicks} clicks across {n_trials} trials from {args.csv}")

    err = df["timing_error_ms"]
    med = err.median()
    std = err.std()
    p5, p95 = np.percentile(err, [5, 95])

    trial_onset = df.groupby("trial")["onset_delay_ms"].first()
    onset_std   = trial_onset.std()

    df["within_trial_jitter_ms"] = df["timing_error_ms"] - df["onset_delay_ms"]
    wj     = df["within_trial_jitter_ms"]
    wj_std = wj.std()

    # ── Software measurement figure (always produced) ────────────────────────
    fig = plt.figure(figsize=(15, 11))
    fig.suptitle(
        f"Click timing determinism (software DAC timestamp)  —  "
        f"{n_clicks} clicks, {n_trials} trials\n"
        f"timing_error:  median {med:.3f} ms   std {std:.3f} ms   "
        f"5–95 pct [{p5:.3f}, {p95:.3f}] ms",
        fontsize=12, fontweight="bold",
    )
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.55, wspace=0.38)

    C_ERR   = "#e15759"
    C_ONSET = "#4e79a7"
    C_JITT  = "#f28e2b"
    bins = min(80, max(20, n_clicks // 30))

    ax = fig.add_subplot(gs[0, 0])
    ax.hist(err, bins=bins, color=C_ERR, alpha=0.85, edgecolor="white", linewidth=0.3)
    ax.axvline(med, color="black", linewidth=1.2, linestyle="--", label=f"median {med:.3f} ms")
    ax.set_xlabel("timing_error_ms")
    ax.set_ylabel("Count")
    ax.set_title(f"All clicks: timing error\nstd = {std:.3f} ms", fontsize=9)
    ax.legend(fontsize=8)

    ax = fig.add_subplot(gs[0, 1])
    ax.hist(trial_onset.values, bins=min(40, n_trials), color=C_ONSET, alpha=0.85,
            edgecolor="white", linewidth=0.3)
    ax.axvline(trial_onset.median(), color="black", linewidth=1.2, linestyle="--",
               label=f"median {trial_onset.median():.2f} ms")
    ax.set_xlabel("onset_delay_ms (per trial)")
    ax.set_ylabel("Count")
    ax.set_title(f"Pipeline delay per trial\nstd = {onset_std:.4f} ms  (onset jitter)", fontsize=9)
    ax.legend(fontsize=8)

    ax = fig.add_subplot(gs[0, 2])
    ax.hist(wj, bins=bins, color=C_JITT, alpha=0.85, edgecolor="white", linewidth=0.3)
    ax.axvline(0, color="black", linewidth=1.0, linestyle="--")
    ax.set_xlabel("within_trial_jitter_ms")
    ax.set_ylabel("Count")
    ax.set_title(f"Within-trial jitter\nstd = {wj_std:.4f} ms  ← sample-clock precision", fontsize=9)

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
    ax.set_title("Jitter vs. position in train", fontsize=9)
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
    ax.set_title("Timing error vs. scheduled time", fontsize=9)
    ax.legend(fontsize=8)

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
        f"{'Overall timing_error std':<50}  {std:>11.4f} ms\n"
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

    # ── Oscilloscope verification figure (only when --osci-csv is given) ─────
    if args.osci_csv:
        print(f"\nLoading oscilloscope CSV: {args.osci_csv}")
        t_s, ch1, ch2 = _load_osci_csv(args.osci_csv)
        print(f"  {len(t_s)} samples  "
              f"duration={t_s[-1]-t_s[0]:.3f} s  "
              f"sample_rate={1/(t_s[1]-t_s[0]):.0f} Hz")

        ch2_thresh = args.osci_ch2_thresh or (np.nanmax(ch2) + np.nanmin(ch2)) / 2
        ch1_thresh = args.osci_ch1_thresh or np.nanmax(np.abs(ch1)) * 0.05

        t_gpio  = _rising_edges(t_s, ch2, threshold=ch2_thresh, min_gap_s=0.003)
        t_audio = _rising_edges(t_s, ch1, threshold=ch1_thresh, min_gap_s=0.003)
        print(f"  GPIO edges: {len(t_gpio)}   Audio edges: {len(t_audio)}")

        _, _, delays = _match_edges(t_gpio, t_audio,
                                    args.osci_search_min, args.osci_search_max)
        n_matched = len(delays)
        print(f"  Matched: {n_matched} clicks")

        if n_matched == 0:
            print("  WARNING: no matched pairs. Check --osci-search-min/max "
                  "and --osci-ch1/ch2-thresh.")
        else:
            d_med = np.median(delays)
            d_std = np.std(delays)
            onset_sw  = trial_onset.median()
            onset_hw  = onset_sw + d_med  # hardware-verified: sw + PortAudio bias
            print(f"  Oscilloscope delay:  median={d_med:.3f} ms  std={d_std:.4f} ms")
            print(f"  Software onset delay  : {onset_sw:.2f} ms")
            print(f"  PortAudio bias (d_med): {d_med:+.3f} ms")
            print(f"  HW-verified onset     : {onset_hw:.2f} ms  "
                  f"(= software {'+ ' if d_med >= 0 else '− '}{abs(d_med):.3f} ms)")

            fig2 = plt.figure(figsize=(14, 10))
            fig2.suptitle(
                f"Oscilloscope verification  —  {n_matched} matched clicks\n"
                f"PortAudio bias (Ch1−Ch2 median): {d_med:+.3f} ms   "
                f"hw-verified onset: {onset_hw:.2f} ms   "
                f"scope jitter std: {d_std:.4f} ms",
                fontsize=12, fontweight="bold",
            )
            gs2 = gridspec.GridSpec(3, 2, figure=fig2, hspace=0.55, wspace=0.38,
                                    height_ratios=[2, 1.5, 0.8])

            # Panel 1 — raw oscilloscope traces anchored to first GPIO edge
            ax = fig2.add_subplot(gs2[0, :])
            t_anchor = t_gpio[0] if len(t_gpio) > 0 else t_s[0]
            mask = (t_s >= t_anchor - 0.010) & (t_s <= t_anchor + 0.050)
            ax.plot(t_s[mask] * 1000, ch1[mask], color="#1f77b4",
                    linewidth=0.8, label="Ch1 audio")
            ax2_twin = ax.twinx()
            ax2_twin.plot(t_s[mask] * 1000, ch2[mask], color="#d62728",
                          linewidth=0.8, alpha=0.7, label="Ch2 GPIO")
            ax2_twin.set_ylabel("GPIO (V)", color="#d62728")
            ax2_twin.tick_params(axis='y', labelcolor="#d62728")
            ax.set_xlabel("Time (ms)")
            ax.set_ylabel("Audio (V)")
            ax.set_title("Raw traces — first GPIO edge ±10/50 ms  (audio blue, GPIO marker red)")
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2_twin.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper right")
            ax.grid(alpha=0.3)

            # Panel 2 — oscilloscope hw error vs software within-trial jitter
            # Both quantities are centred near 0 and measure timing precision:
            #   delays           = t_ch1_audio − t_ch2_gpio ≈ 0  (PortAudio prediction error)
            #   within_trial_jitter_ms = timing_error − onset_delay ≈ 0  (sample-clock jitter)
            # If they agree, the software DAC timestamp is an accurate jitter proxy.
            ax = fig2.add_subplot(gs2[1, 0])
            combined = np.concatenate([delays, wj.values])
            p1, p99  = np.percentile(combined, [1, 99])
            margin   = max(0.5, (p99 - p1) * 0.2)
            bins_h   = np.linspace(p1 - margin, p99 + margin, 60)
            ax.hist(delays, bins=bins_h, color="#2ca02c", alpha=0.7,
                    label=f"scope hw error: std={d_std:.4f} ms", density=True)
            ax.hist(wj.values, bins=bins_h, color=C_JITT, alpha=0.5,
                    label=f"software jitter: std={wj_std:.4f} ms", density=True)
            ax.axvline(d_med, color="#2ca02c", linewidth=1.2, linestyle="--",
                       label=f"scope median {d_med:.3f} ms")
            ax.axvline(0, color="black", linewidth=0.8, linestyle=":")
            ax.set_xlabel("Prediction error (ms)")
            ax.set_ylabel("Density")
            ax.set_title("Scope hw verification vs software jitter\n"
                         "(aligned ↔ PortAudio timestamp is accurate)", fontsize=9)
            ax.legend(fontsize=8)

            # Panel 3 — oscilloscope delay vs click index (systematic drift?)
            ax = fig2.add_subplot(gs2[1, 1])

            ax.scatter(range(n_matched), delays, alpha=0.4, s=8, color="#2ca02c")
            roll = pd.Series(delays).rolling(max(1, n_matched // 20),
                                             center=True, min_periods=1).median()
            ax.plot(range(n_matched), roll.values,
                    color="black", linewidth=1.2, label="rolling median")
            ax.axhline(d_med, color="grey", linewidth=0.8, linestyle="--")
            ax.set_xlabel("Click index (all trials)")
            ax.set_ylabel("Oscilloscope delay (ms)")
            ax.set_title("Delay over time\n(slope = systematic drift)", fontsize=9)
            ax.legend(fontsize=8)

            # Panel 4 — onset delay summary text
            ax = fig2.add_subplot(gs2[2, :])
            ax.axis("off")
            summary2 = (
                f"{'Quantity':<55}  {'Software':>14}  {'Hardware (scope)':>16}\n"
                f"{'─' * 90}\n"
                f"{'ALSA onset delay  (t_play → first sample at DAC)':<55}  "
                f"{onset_sw:>13.2f} ms  {onset_hw:>15.2f} ms\n"
                f"{'PortAudio outputBufferDacTime bias  (d_med)':<55}  "
                f"{'—':>14}  {d_med:>+14.3f} ms\n"
                f"{'Timing jitter std  (sample-clock precision)':<55}  "
                f"{wj_std:>13.4f} ms  {d_std:>15.4f} ms\n"
                f"{'─' * 90}\n"
                f"  hw_onset = sw_onset + PortAudio_bias:  "
                f"{onset_sw:.2f} + ({d_med:+.3f}) = {onset_hw:.2f} ms\n"
                f"  If |PortAudio_bias| < 1 ms: software onset measurement is trustworthy."
            )
            ax.text(0.01, 0.95, summary2, transform=ax.transAxes,
                    fontsize=8.5, verticalalignment="top", fontfamily="monospace",
                    bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.9))

            osci_out = (args.out or args.csv.replace(".csv", "")).replace(".png", "") \
                       + "_osci.png"
            fig2.savefig(osci_out, dpi=150, bbox_inches="tight")
            print(f"Oscilloscope figure saved → {osci_out}")

    plt.show()


if __name__ == "__main__":
    main()
