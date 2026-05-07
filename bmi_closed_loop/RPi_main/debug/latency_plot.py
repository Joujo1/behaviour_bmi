"""
Click timing analysis — two metrics, one figure.

Requires latency_measure.py output CSV + two Tektronix ISF files (ch1=audio, ch2=GPIO).

Metric 1 — ALSA prediction accuracy:
  t_audio (scope ch1 edge) − t_gpio (scope ch2 edge) per click.
  Measures how accurately outputBufferDacTime predicts actual DAC output.
  Should be near 0 ms with small std.

Metric 2 — ICI preservation:
  diff(t_audio) − diff(t_gpio) per consecutive click pair.
  Measures whether scheduled inter-click intervals are reproduced faithfully.
  Should be near 0 ms with small std.

Usage:
    python3 debug/latency_plot.py output/latency.csv --isf T0000CH1.ISF T0000CH2.ISF
    python3 debug/latency_plot.py output/latency.csv --isf T0000CH1.ISF T0000CH2.ISF --out fig.png
"""

import argparse
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


# ── ISF loader ────────────────────────────────────────────────────────────────

def _load_isf(path: str) -> tuple:
    """Parse a Tektronix ISF file. Returns (t_s, v) in seconds and volts."""
    with open(path, "rb") as f:
        raw = f.read()

    curve_idx = raw.find(b":CURV")
    if curve_idx == -1:
        curve_idx = raw.find(b"CURV")
    header = raw[:curve_idx].decode("ascii", errors="ignore")
    after  = raw[curve_idx:]

    params = {}
    for token in header.split(";"):
        token = token.strip()
        if ":" in token:
            token = token.rsplit(":", 1)[-1]
        parts = token.split()
        if len(parts) == 2:
            params[parts[0].strip()] = parts[1].strip()

    xincr  = float(params["XIN"])
    xzero  = float(params["XZE"])
    pt_off = float(params.get("PT_O", 0))
    ymult  = float(params["YMU"])
    yoff   = float(params["YOF"])
    yzero  = float(params["YZE"])
    byt_nr = int(params.get("BYT_N", 2))
    nr_pt  = int(params["NR_P"])
    bn_fmt = params.get("BN_F", "RI").strip()
    byt_or = params.get("BYT_O", "MSB").strip()

    hash_idx   = after.index(b"#")
    n_digits   = int(chr(after[hash_idx + 1]))
    data_start = hash_idx + 2 + n_digits
    data       = after[data_start:data_start + nr_pt * byt_nr]

    dtype = np.dtype((">" if byt_or == "MSB" else "<") +
                     ("i" if bn_fmt == "RI" else "u") + str(byt_nr))
    y_raw = np.frombuffer(data, dtype=dtype).astype(np.float64)
    v = (y_raw - yoff) * ymult + yzero
    t = (np.arange(nr_pt) - pt_off) * xincr + xzero
    return t, v


# ── Edge detection ────────────────────────────────────────────────────────────

def _rising_edges(t: np.ndarray, v: np.ndarray,
                  threshold: float | None = None,
                  min_gap_s: float = 0.003) -> np.ndarray:
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
                 search_min_s: float = 0.005,
                 search_max_s: float = 0.150) -> tuple:
    """Match each GPIO edge to the first audio edge within the search window."""
    mg, ma = [], []
    for tg in t_gpio:
        cands = t_audio[(t_audio >= tg + search_min_s) & (t_audio <= tg + search_max_s)]
        if len(cands):
            mg.append(tg)
            ma.append(cands[0])
    return np.array(mg), np.array(ma)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv", help="latency_measure.py output CSV")
    p.add_argument("--isf", nargs=2, metavar=("CH1.ISF", "CH2.ISF"), required=True,
                   help="Tektronix ISF exports: ch1=audio, ch2=GPIO marker")
    p.add_argument("--ch2-thresh", type=float, default=None,
                   help="GPIO channel threshold in V (default: auto)")
    p.add_argument("--ch1-thresh", type=float, default=None,
                   help="Audio channel threshold in V (default: auto = 5%% of peak)")
    p.add_argument("--search-min", type=float, default=5.0,
                   help="Edge match window start ms after GPIO edge (default: 5)")
    p.add_argument("--search-max", type=float, default=150.0,
                   help="Edge match window end ms after GPIO edge (default: 150)")
    p.add_argument("--zoom-ms", type=float, default=100.0,
                   help="Raw trace zoom window in ms around first GPIO edge (default: 100)")
    p.add_argument("--out", default=None, help="Output PNG path")
    args = p.parse_args()

    # Load software CSV
    df = pd.read_csv(args.csv)
    wj = (df["timing_error_ms"] - df["onset_delay_ms"])
    wj_std = wj.std()
    onset_med = df.groupby("trial")["onset_delay_ms"].first().median()

    # Load ISF
    print(f"Loading ISF: {args.isf[0]}  {args.isf[1]}")
    t1, ch1 = _load_isf(args.isf[0])
    t2, ch2 = _load_isf(args.isf[1])
    n = min(len(t1), len(t2))
    t_s, ch1, ch2 = t1[:n], ch1[:n], ch2[:n]
    print(f"  {n} samples  duration={t_s[-1]-t_s[0]:.3f} s  "
          f"rate={1/(t_s[1]-t_s[0]):.0f} Hz")

    # Detect edges
    ch2_thresh = args.ch2_thresh or (np.nanmax(ch2) + np.nanmin(ch2)) / 2
    ch1_thresh = args.ch1_thresh or np.nanmax(np.abs(ch1)) * 0.05
    t_gpio  = _rising_edges(t_s, ch2, threshold=ch2_thresh)
    t_audio = _rising_edges(t_s, ch1, threshold=ch1_thresh)
    print(f"  GPIO edges: {len(t_gpio)}   Audio edges: {len(t_audio)}")

    t_gpio_m, t_audio_m = _match_edges(t_gpio, t_audio,
                                        args.search_min / 1000, args.search_max / 1000)
    n_matched = len(t_gpio_m)
    print(f"  Matched: {n_matched} clicks")
    if n_matched < 2:
        print("ERROR: too few matched clicks — check --ch1-thresh / --search-min/max")
        sys.exit(1)

    # Metric 1 — ALSA prediction accuracy (per click)
    pred_error_ms = (t_audio_m - t_gpio_m) * 1000
    pred_med = np.median(pred_error_ms)
    pred_std = np.std(pred_error_ms)

    print(f"\nHardware delay:  median={pred_med:.3f} ms  std={pred_std:.4f} ms")
    print(f"  (std = ICI jitter — if flat over time, ICI is preserved)")

    # ── Figure ───────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(14, 10))
    gs  = gridspec.GridSpec(3, 2, figure=fig, hspace=0.55, wspace=0.38,
                            height_ratios=[1.6, 1.4, 0.6])

    C_PRED = "#4e79a7"
    C_ICI  = "#f28e2b"

    # Panel 1 — overlapping raw traces (twinx), same line style as isf_plot.py
    t0   = t_gpio[0] if len(t_gpio) else t_s[0]
    hw   = args.zoom_ms / 2 / 1000
    mask = (t_s >= t0 - hw) & (t_s <= t0 + hw)
    t_ms = (t_s[mask] - t0) * 1000

    ax = fig.add_subplot(gs[0, :])
    ax.plot(t_ms, ch1[mask], color=C_PRED, lw=0.8, label="Ch1 — audio (V)")
    ax.axvline(0,        color="red",   lw=0.8, linestyle="--", alpha=0.6)
    ax.axvline(pred_med, color="black", lw=0.8, linestyle="--", alpha=0.7,
               label=f"median audio onset +{pred_med:.1f} ms")
    ax.set_ylabel("Audio (V)", color=C_PRED)
    ax.tick_params(axis="y", labelcolor=C_PRED)
    ax.grid(alpha=0.3)

    ax2 = ax.twinx()
    ax2.plot(t_ms, ch2[mask], color="red", lw=0.8, alpha=0.8, label="Ch2 — GPIO (V)")
    ax2.set_ylabel("GPIO (V)", color="red")
    ax2.tick_params(axis="y", labelcolor="red")

    ax.set_xlabel("Time relative to GPIO edge (ms)")
    ax.set_title(f"Raw traces — first click  (zoom ±{args.zoom_ms/2:.0f} ms)")
    lines1, labs1 = ax.get_legend_handles_labels()
    lines2, labs2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labs1 + labs2, fontsize=8, loc="upper right")

    # Panel 2 — overlaid ICI from all detected edges (not matched subset)
    gpio_ici_ms  = np.diff(t_gpio)  * 1000
    audio_ici_ms = np.diff(t_audio) * 1000
    gpio_med  = np.median(gpio_ici_ms);  gpio_std  = np.std(gpio_ici_ms)
    audio_med = np.median(audio_ici_ms); audio_std = np.std(audio_ici_ms)
    ax = fig.add_subplot(gs[1, :])
    ax.scatter(range(len(gpio_ici_ms)),  gpio_ici_ms,  alpha=0.7, s=30, color="red",  marker="s", label=f"GPIO  (scheduled)  median={gpio_med:.3f} ms  std={gpio_std:.4f} ms")
    ax.scatter(range(len(audio_ici_ms)), audio_ici_ms, alpha=0.7, s=30, color=C_PRED, marker="^", label=f"Audio (actual)      median={audio_med:.3f} ms  std={audio_std:.4f} ms")
    ax.set_xlabel("Click pair index")
    ax.set_ylabel("ICI (ms)")
    ax.set_title("Scheduled vs actual ICI per consecutive click pair", fontsize=9)
    ax.legend(fontsize=8)
    ax.yaxis.set_major_locator(plt.MultipleLocator(5))
    ax.yaxis.set_minor_locator(plt.MultipleLocator(1))
    ax.grid(which="major", alpha=0.4)
    ax.grid(which="minor", alpha=0.15)

    # Panel 4 — summary
    ax = fig.add_subplot(gs[2, :])
    ax.axis("off")
    summary = (
        f"{'Quantity':<52}  {'GPIO (scheduled)':>18}  {'Audio (actual)':>16}\n"
        f"{'─'*90}\n"
        f"{'ICI  median':<52}  {gpio_med:>16.3f} ms  {audio_med:>14.3f} ms\n"
        f"{'ICI  std':<52}  {gpio_std:>16.4f} ms  {audio_std:>14.4f} ms\n"
        f"{'─'*90}\n"
        f"{'GPIO edges detected':<52}  {len(t_gpio):>18d}\n"
        f"{'Audio edges detected':<52}  {len(t_audio):>18d}\n"
        f"{'─'*90}\n"
        f"{'Software within-trial jitter  std':<52}  {wj_std:>16.4f} ms\n"
        f"{'ALSA pipeline onset delay  (median)':<52}  {onset_med:>16.2f} ms\n"
    )
    ax.text(0.01, 0.98, summary, transform=ax.transAxes,
            fontsize=9, verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="whitesmoke", alpha=0.8))

    fig.suptitle(
        f"Click timing  —  {n_matched} matched clicks  |  "
        f"GPIO ICI std={gpio_std:.4f} ms   Audio ICI std={audio_std:.4f} ms",
        fontsize=11, fontweight="bold",
    )

    out = args.out or args.csv.replace(".csv", "_hw.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.show()


if __name__ == "__main__":
    main()
