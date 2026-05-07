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
from scipy import signal as _signal


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
    """Detect rising edges where v crosses `threshold` upward.

    Use this on monotonic or single-polarity signals (GPIO square waves,
    envelopes, etc.). Do NOT call on bipolar oscillating signals — the
    crossing time then depends on click amplitude and starting polarity.
    """
    if threshold is None:
        threshold = (np.nanmax(v) + np.nanmin(v)) / 2
    above = v > threshold
    idxs  = np.where(~above[:-1] & above[1:])[0]
    times, last = [], -np.inf
    for i in idxs:
        # linear interpolation for sub-sample precision
        frac  = (threshold - v[i]) / (v[i + 1] - v[i])
        t_cross = t[i] + frac * (t[i + 1] - t[i])
        if t_cross - last >= min_gap_s:
            times.append(float(t_cross))
            last = t_cross
    return np.array(times)


def _audio_envelope(v: np.ndarray) -> np.ndarray:
    """Return the analytic-signal envelope of an audio trace.

    The envelope is single-polarity, so threshold crossings are independent
    of the click's starting phase and roughly proportional to click amplitude
    only via a smooth rise — much better behaved than the raw bipolar signal.
    """
    return np.abs(_signal.hilbert(v))


def _match_edges(t_gpio: np.ndarray, t_audio: np.ndarray,
                 search_min_s: float = 0.005,
                 search_max_s: float = 0.150) -> tuple:
    """Match each GPIO edge to the first unused audio edge within the search window."""
    mg, ma = [], []
    last_idx = 0
    for tg in t_gpio:
        for i in range(last_idx, len(t_audio)):
            if t_audio[i] < tg + search_min_s:
                continue
            if t_audio[i] > tg + search_max_s:
                break
            mg.append(tg)
            ma.append(t_audio[i])
            last_idx = i + 1  # consume this audio edge
            break
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
                   help="Audio envelope threshold in V "
                        "(default: auto = 8%% of envelope peak — low CFD-style trigger)")
    p.add_argument("--ch1-thresh-frac", type=float, default=0.08,
                   help="Fraction of envelope peak to use as audio threshold "
                        "(default: 0.08). Lower = less amplitude bias.")
    p.add_argument("--search-min", type=float, default=5.0,
                   help="Edge match window start ms after GPIO edge (default: 5)")
    p.add_argument("--search-max", type=float, default=150.0,
                   help="Edge match window end ms after GPIO edge (default: 150)")
    p.add_argument("--zoom-ms", type=float, default=100.0,
                   help="Raw trace zoom window in ms around first GPIO edge (default: 100)")
    p.add_argument("--trim-edges", type=int, default=1,
                   help="Drop this many matched clicks from start AND end "
                        "to avoid filtfilt edge artifacts (default: 1)")
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

    # Filter audio: low-pass at 3 kHz to suppress PWM noise, then take envelope
    sample_rate = 1.0 / (t_s[1] - t_s[0])
    b, a    = _signal.butter(4, 3000 / (sample_rate / 2), btype="low")
    ch1_lp  = _signal.filtfilt(b, a, ch1)
    ch1_env = _audio_envelope(ch1_lp)

    # Edge detection
    ch2_thresh = args.ch2_thresh or (np.nanmax(ch2) + np.nanmin(ch2)) / 2
    ch1_thresh = args.ch1_thresh or np.nanmax(ch1_env) * args.ch1_thresh_frac
    print(f"  Audio envelope threshold: {ch1_thresh*1000:.2f} mV  "
          f"(={args.ch1_thresh_frac*100:.0f}% of peak {np.nanmax(ch1_env)*1000:.1f} mV)")

    t_gpio  = _rising_edges(t_s, ch2,     threshold=ch2_thresh)
    t_audio = _rising_edges(t_s, ch1_env, threshold=ch1_thresh)
    print(f"  GPIO edges: {len(t_gpio)}   Audio edges: {len(t_audio)}")

    t_gpio_m, t_audio_m = _match_edges(t_gpio, t_audio,
                                        args.search_min / 1000, args.search_max / 1000)

    # Trim edges of the matched series — filtfilt is unreliable near trace boundaries
    if args.trim_edges > 0 and len(t_gpio_m) > 2 * args.trim_edges + 1:
        k = args.trim_edges
        t_gpio_m  = t_gpio_m[k:-k]
        t_audio_m = t_audio_m[k:-k]
        print(f"  Trimmed {k} click(s) from each end "
              f"(filtfilt edge artifacts) → {len(t_gpio_m)} kept")

    n_matched = len(t_gpio_m)
    print(f"  Matched: {n_matched} clicks")
    if n_matched < 2:
        print("ERROR: too few matched clicks — check --ch1-thresh / --search-min/max")
        sys.exit(1)

    # Metric 1 — per-click hardware delay (audio onset relative to GPIO edge)
    pred_error_ms = (t_audio_m - t_gpio_m) * 1000
    pred_med = np.median(pred_error_ms)
    pred_std = np.std(pred_error_ms)

    print(f"\nHardware delay:  median={pred_med:.3f} ms  std={pred_std:.4f} ms")
    print("  (per-click; std reflects amplitude/threshold sensitivity)")

    # ── Figure ───────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(14, 10))
    gs  = gridspec.GridSpec(3, 2, figure=fig, hspace=0.55, wspace=0.38,
                            height_ratios=[1.6, 1.4, 0.6])

    C_PRED = "#4e79a7"
    C_ENV  = "#59a14f"

    # Panel 1 — overlapping raw traces (twinx)
    t0   = t_gpio[0] if len(t_gpio) else t_s[0]
    mask = (t_s >= t0) & (t_s <= t0 + args.zoom_ms / 1000)
    t_ms = (t_s[mask] - t0) * 1000

    ax = fig.add_subplot(gs[0, :])
    ax.plot(t_ms, ch1[mask],     color=C_PRED, lw=0.5, alpha=0.35, label="Ch1 — audio raw")
    ax.plot(t_ms, ch1_lp[mask],  color=C_PRED, lw=1.0, label="Ch1 — audio filtered")
    ax.plot(t_ms, ch1_env[mask], color=C_ENV,  lw=1.0, alpha=0.85, label="Ch1 — envelope")
    ax.axhline( ch1_thresh, color=C_ENV, lw=0.6, linestyle=":", alpha=0.6,
               label=f"audio threshold ±{ch1_thresh*1000:.1f} mV")
    ax.axhline(-ch1_thresh, color=C_ENV, lw=0.6, linestyle=":", alpha=0.6)
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
    ax.set_title(f"Raw traces — first {args.zoom_ms:.0f} ms from first GPIO edge")
    lines1, labs1 = ax.get_legend_handles_labels()
    lines2, labs2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labs1 + labs2, fontsize=8, loc="upper right")

    # Panel 2 — ICI difference: audio ICI minus GPIO ICI (matched pairs)
    gpio_ici_ms  = np.diff(t_gpio_m)  * 1000
    audio_ici_ms = np.diff(t_audio_m) * 1000
    ici_diff_ms  = audio_ici_ms - gpio_ici_ms
    diff_med = np.median(ici_diff_ms)
    diff_std = np.std(ici_diff_ms)

    ax = fig.add_subplot(gs[1, :])
    ax.scatter(range(len(ici_diff_ms)), ici_diff_ms, alpha=0.7, s=20,
               color=C_PRED, marker="o")
    ax.axhline(0,        color="black", lw=1.0, linestyle="--", alpha=0.5)
    ax.axhline(diff_med, color="red",   lw=1.2, linestyle="--",
               label=f"median {diff_med:.3f} ms")
    ax.set_xlabel("Click pair index")
    ax.set_ylabel("Audio ICI − GPIO ICI  (ms)")
    ax.set_title(f"ICI difference (audio − scheduled)  |  median={diff_med:.3f} ms   std={diff_std:.4f} ms",
                 fontsize=9)
    ax.legend(fontsize=8)
    ax.yaxis.set_major_locator(plt.MultipleLocator(5))
    ax.yaxis.set_minor_locator(plt.MultipleLocator(1))
    ax.grid(which="major", alpha=0.4)
    ax.grid(which="minor", alpha=0.15)

    # Panel 3 — summary
    ax = fig.add_subplot(gs[2, :])
    ax.axis("off")
    summary = (
        f"{'Quantity':<52}  {'Value':>12}\n"
        f"{'─'*67}\n"
        f"{'Matched clicks':<52}  {n_matched:>12d}\n"
        f"{'GPIO edges detected':<52}  {len(t_gpio):>12d}\n"
        f"{'Audio edges detected':<52}  {len(t_audio):>12d}\n"
        f"{'─'*67}\n"
        f"{'Per-click hardware delay  median':<52}  {pred_med:>11.3f} ms\n"
        f"{'Per-click hardware delay  std':<52}  {pred_std:>11.4f} ms\n"
        f"{'ICI difference  median  (audio − GPIO)':<52}  {diff_med:>11.3f} ms\n"
        f"{'ICI difference  std':<52}  {diff_std:>11.4f} ms\n"
        f"{'─'*67}\n"
        f"{'Software within-trial jitter  std':<52}  {wj_std:>11.4f} ms\n"
        f"{'ALSA pipeline onset delay  (median)':<52}  {onset_med:>11.2f} ms\n"
    )
    ax.text(0.01, 0.98, summary, transform=ax.transAxes,
            fontsize=9, verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="whitesmoke", alpha=0.8))

    fig.suptitle(
        f"Click timing  —  {n_matched} matched clicks  |  "
        f"ICI difference  median={diff_med:.3f} ms   std={diff_std:.4f} ms",
        fontsize=11, fontweight="bold",
    )

    out = args.out or args.csv.replace(".csv", "_hw.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.show()


if __name__ == "__main__":
    main()