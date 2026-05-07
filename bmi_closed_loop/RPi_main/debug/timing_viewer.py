"""
Timing viewer — overlay GPIO and mean-shifted audio/PWM waveforms.

Shifts each audio channel left by its mean GPIO→audio delay so edges align
with the GPIO trigger at t=0. Outlier panel shows raw per-click delays.

Optional --isf-pwm adds a GPIO-PWM channel captured on a third scope channel.
The PWM fires at the scheduled software time (~56 ms before the GPIO trigger),
so its search window must be negative: use --search-min-pwm / --search-max-pwm.

Keys: ← / → to pan,  + / − to zoom.

Usage:
    python3 debug/timing_viewer.py --isf T0000CH2.ISF T0000CH1.ISF
    python3 debug/timing_viewer.py --isf T0000CH2.ISF T0000CH1.ISF \\
        --isf-pwm T0000CH3.ISF --search-min-pwm -80 --search-max-pwm -20
"""

import argparse
import sys

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy import signal as _signal


# ── ISF loader ────────────────────────────────────────────────────────────────

def _load_isf(path: str) -> tuple:
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
        frac    = (threshold - v[i]) / (v[i + 1] - v[i])
        t_cross = t[i] + frac * (t[i + 1] - t[i])
        if t_cross - last >= min_gap_s:
            times.append(float(t_cross))
            last = t_cross
    return np.array(times)


def _match_edges(t_ref: np.ndarray, t_other: np.ndarray,
                 search_min_s: float = 0.005,
                 search_max_s: float = 0.150) -> tuple:
    """Match each ref edge to the first unused other edge in [ref+min, ref+max].
    Works with negative offsets (other fires before ref)."""
    mg, ma = [], []
    last_idx = 0
    for tg in t_ref:
        for i in range(last_idx, len(t_other)):
            if t_other[i] < tg + search_min_s:
                continue
            if t_other[i] > tg + search_max_s:
                break
            mg.append(tg)
            ma.append(t_other[i])
            last_idx = i + 1
            break
    return np.array(mg), np.array(ma)


def _process_audio(t_s: np.ndarray, ch: np.ndarray,
                   sample_rate: float, thresh: float | None = None) -> tuple:
    """LP filter at 3 kHz → rising-edge detection on filtered signal.
    Returns (ch_lp, t_edges, thresh_used)."""
    b, a   = _signal.butter(4, 3000 / (sample_rate / 2), btype="low")
    ch_lp  = _signal.filtfilt(b, a, ch)
    if thresh is None:
        thresh = np.nanmax(np.abs(ch_lp)) * 0.35
    t_edges = _rising_edges(t_s, ch_lp, threshold=thresh)
    return ch_lp, t_edges, thresh


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--isf", nargs=2, metavar=("CH1.ISF", "CH2.ISF"), required=True,
                   help="ch1=audio, ch2=GPIO trigger")
    p.add_argument("--isf-pwm", metavar="CH3.ISF", default=None,
                   help="Optional ISF for the GPIO-PWM channel")
    p.add_argument("--ch2-thresh",  type=float, default=None)
    p.add_argument("--ch1-thresh",  type=float, default=None)
    p.add_argument("--ch3-thresh",  type=float, default=None)
    p.add_argument("--search-min",     type=float, default=5.0,
                   help="Audio match window start ms after GPIO edge (default: 5)")
    p.add_argument("--search-max",     type=float, default=150.0,
                   help="Audio match window end ms (default: 150)")
    p.add_argument("--search-min-pwm", type=float, default=-100.0,
                   help="PWM match window start ms relative to GPIO edge (default: -100)")
    p.add_argument("--search-max-pwm", type=float, default=-20.0,
                   help="PWM match window end ms relative to GPIO edge (default: -20)")
    p.add_argument("--win-ms", type=float, default=200.0,
                   help="Visible window width in ms (default: 200)")
    args = p.parse_args()

    # ── Load ISF ─────────────────────────────────────────────────────────────
    print(f"Loading: {args.isf[0]}  {args.isf[1]}")
    t1, ch1 = _load_isf(args.isf[0])
    t2, ch2 = _load_isf(args.isf[1])
    n = min(len(t1), len(t2))
    t_s, ch1, ch2 = t1[:n], ch1[:n], ch2[:n]
    sample_rate = 1.0 / (t_s[1] - t_s[0])
    print(f"  {n} samples  duration={t_s[-1]-t_s[0]:.3f} s  rate={sample_rate:.0f} Hz")

    # ── Audio channel (LP → envelope → edges) ────────────────────────────────
    ch1_lp, t_audio, ch1_thresh = _process_audio(
        t_s, ch1, sample_rate, args.ch1_thresh)
    print(f"  Audio threshold: {ch1_thresh*1000:.2f} mV")

    # ── GPIO trigger edges ────────────────────────────────────────────────────
    ch2_thresh = args.ch2_thresh or (np.nanmax(ch2) + np.nanmin(ch2)) / 2
    t_gpio = _rising_edges(t_s, ch2, threshold=ch2_thresh)
    print(f"  GPIO edges: {len(t_gpio)}   Audio edges: {len(t_audio)}")

    # ── Match audio → GPIO ────────────────────────────────────────────────────
    t_gpio_m, t_audio_m = _match_edges(t_gpio, t_audio,
                                        args.search_min / 1000,
                                        args.search_max / 1000)
    n_matched = len(t_gpio_m)
    print(f"  Matched audio: {n_matched}")
    if n_matched < 2:
        print("ERROR: too few matched audio clicks — check thresholds / search window")
        sys.exit(1)

    delays_ms    = (t_audio_m - t_gpio_m) * 1000
    mean_delay   = np.mean(delays_ms)
    median_delay = np.median(delays_ms)
    std_delay    = np.std(delays_ms)
    print(f"  Audio  mean={mean_delay:.3f} ms  median={median_delay:.3f} ms  std={std_delay:.4f} ms")

    # ── Optional GPIO-PWM channel ─────────────────────────────────────────────
    has_pwm = False
    if args.isf_pwm is not None:
        print(f"Loading PWM ISF: {args.isf_pwm}")
        t_p, ch_pwm_raw = _load_isf(args.isf_pwm)
        np_ = min(len(t_p), n)
        ch_pwm_raw = ch_pwm_raw[:np_]

        ch_pwm_lp, t_pwm_edges, ch3_thresh = _process_audio(
            t_s[:np_], ch_pwm_raw, sample_rate, args.ch3_thresh)
        print(f"  PWM threshold: {ch3_thresh*1000:.2f} mV")
        print(f"  PWM edges: {len(t_pwm_edges)}")

        t_gpio_pm, t_pwm_m = _match_edges(t_gpio, t_pwm_edges,
                                           args.search_min_pwm / 1000,
                                           args.search_max_pwm / 1000)
        n_pwm = len(t_gpio_pm)
        print(f"  Matched PWM: {n_pwm}")

        if n_pwm >= 2:
            has_pwm = True
            pwm_delays_ms    = (t_pwm_m - t_gpio_pm) * 1000
            mean_pwm_delay   = np.mean(pwm_delays_ms)
            median_pwm_delay = np.median(pwm_delays_ms)
            std_pwm_delay    = np.std(pwm_delays_ms)
            print(f"  PWM    mean={mean_pwm_delay:.3f} ms  median={median_pwm_delay:.3f} ms  std={std_pwm_delay:.4f} ms")
        else:
            print("  WARNING: too few PWM matches — disabling PWM overlay")

    # ── Time axes (shift by mean to align with GPIO trigger) ──────────────────
    t_ms       = t_s * 1000
    t_audio_ms = (t_s - mean_delay / 1000) * 1000
    if has_pwm:
        t_pwm_ms = (t_s - mean_pwm_delay / 1000) * 1000

    # ── Figure ────────────────────────────────────────────────────────────────
    n_panels = 3 if has_pwm else 2
    fig = plt.figure(figsize=(14, 8 if not has_pwm else 9))
    height_ratios = [2.5, 1.2] if not has_pwm else [2.5, 1.0, 1.0]
    gs = gridspec.GridSpec(n_panels, 1, figure=fig,
                           height_ratios=height_ratios, hspace=0.50)

    C_AUDIO = "#4e79a7"   # blue
    C_GPIO  = "red"
    C_PWM   = "#f28e2b"   # orange

    # ── Panel 1: waveform overlay (twinx) ────────────────────────────────────
    ax_w  = fig.add_subplot(gs[0])
    ax_w2 = ax_w.twinx()

    ax_w.plot(t_audio_ms, ch1_lp, color=C_AUDIO, lw=0.8, alpha=0.85,
              label=f"Audio LP (shifted −{mean_delay:.1f} ms)")

    if has_pwm:
        ax_w.plot(t_pwm_ms, ch_pwm_lp, color=C_PWM, lw=0.8, alpha=0.85,
                  label=f"PWM LP (shifted −{mean_pwm_delay:.1f} ms)")

    ax_w2.plot(t_ms, ch2, color=C_GPIO, lw=0.8, alpha=0.85, label="GPIO trigger")

    ax_w.set_ylabel("Audio (V)",  color=C_AUDIO)
    ax_w.tick_params(axis="y", labelcolor=C_AUDIO)
    ax_w2.set_ylabel("GPIO (V)", color=C_GPIO)
    ax_w2.tick_params(axis="y", labelcolor=C_GPIO)
    ax_w.set_xlabel("Time (ms)")
    ax_w.grid(alpha=0.3)

    lines1, labs1 = ax_w.get_legend_handles_labels()
    lines2, labs2 = ax_w2.get_legend_handles_labels()
    ax_w.legend(lines1 + lines2, labs1 + labs2, fontsize=8, loc="upper right")

    # ── Panel 2: audio delay scatter ─────────────────────────────────────────
    ax_a = fig.add_subplot(gs[1])
    ax_a.scatter(range(n_matched), delays_ms, s=15, alpha=0.65,
                 color=C_AUDIO, zorder=2)
    ax_a.axhline(mean_delay,   color=C_AUDIO, lw=1.5, linestyle="-",
                 label=f"mean {mean_delay:.3f} ms")
    ax_a.axhline(median_delay, color="gray",  lw=1.0, linestyle="--",
                 label=f"median {median_delay:.3f} ms")
    ax_a.axhspan(mean_delay - std_delay, mean_delay + std_delay,
                 color=C_AUDIO, alpha=0.12, label=f"±1σ ({std_delay:.4f} ms)")
    ax_a.yaxis.set_major_locator(plt.MultipleLocator(1))
    ax_a.yaxis.set_minor_locator(plt.MultipleLocator(0.25))
    ax_a.grid(which="major", alpha=0.4)
    ax_a.grid(which="minor", alpha=0.15)
    ax_a.set_xlabel("Click index")
    ax_a.set_ylabel("Audio delay (ms)", color=C_AUDIO)
    ax_a.tick_params(axis="y", labelcolor=C_AUDIO)
    ax_a.set_xlim(-1, n_matched + 1)
    ax_a.legend(fontsize=8, loc="upper right")
    ax_a.set_title(
        f"Audio delay  mean={mean_delay:.3f} ms   median={median_delay:.3f} ms   std={std_delay:.4f} ms",
        fontsize=9)

    # ── Panel 3: PWM delay scatter (optional) ────────────────────────────────
    if has_pwm:
        ax_p = fig.add_subplot(gs[2])
        ax_p.scatter(range(n_pwm), pwm_delays_ms, s=15, alpha=0.65,
                     color=C_PWM, zorder=2)
        ax_p.axhline(mean_pwm_delay,   color=C_PWM,    lw=1.5, linestyle="-",
                     label=f"mean {mean_pwm_delay:.3f} ms")
        ax_p.axhline(median_pwm_delay, color="#c8a060", lw=1.0, linestyle="--",
                     label=f"median {median_pwm_delay:.3f} ms")
        ax_p.axhspan(mean_pwm_delay - std_pwm_delay,
                     mean_pwm_delay + std_pwm_delay,
                     color=C_PWM, alpha=0.12, label=f"±1σ ({std_pwm_delay:.4f} ms)")
        ax_p.yaxis.set_major_locator(plt.MultipleLocator(1))
        ax_p.yaxis.set_minor_locator(plt.MultipleLocator(0.25))
        ax_p.grid(which="major", alpha=0.4)
        ax_p.grid(which="minor", alpha=0.15)
        ax_p.set_xlabel("Click index")
        ax_p.set_ylabel("PWM delay (ms)", color=C_PWM)
        ax_p.tick_params(axis="y", labelcolor=C_PWM)
        ax_p.set_xlim(-1, n_pwm + 1)
        ax_p.legend(fontsize=8, loc="upper right")
        ax_p.set_title(
            f"PWM delay  mean={mean_pwm_delay:.3f} ms   median={median_pwm_delay:.3f} ms   std={std_pwm_delay:.4f} ms",
            fontsize=9)

    # ── Navigation ────────────────────────────────────────────────────────────
    t0_ms  = t_gpio[0] * 1000 if len(t_gpio) else 0.0
    win_ms = [args.win_ms]
    pos_ms = [t0_ms]

    def set_view():
        ax_w.set_xlim(pos_ms[0], pos_ms[0] + win_ms[0])
        fig.canvas.draw_idle()

    def on_key(event):
        step = win_ms[0] * 0.5
        if event.key == "right":
            pos_ms[0] += step
        elif event.key == "left":
            pos_ms[0] = max(t_ms[0], pos_ms[0] - step)
        elif event.key in ("+", "="):
            win_ms[0] = max(10.0, win_ms[0] * 0.5)
            pos_ms[0] += win_ms[0] * 0.5
        elif event.key == "-":
            win_ms[0] = min(t_ms[-1] - t_ms[0], win_ms[0] * 2.0)
            pos_ms[0] = max(t_ms[0], pos_ms[0] - win_ms[0] * 0.25)
        else:
            return
        set_view()

    fig.canvas.mpl_connect("key_press_event", on_key)

    title = (f"{n_matched} matched clicks  |  "
             f"audio mean={mean_delay:.3f} ms  std={std_delay:.4f} ms")
    if has_pwm:
        title += f"   |   PWM mean={mean_pwm_delay:.3f} ms  std={std_pwm_delay:.4f} ms"
    title += "   |   ← / → pan   + / − zoom"
    fig.suptitle(title, fontsize=10, fontweight="bold")

    set_view()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
