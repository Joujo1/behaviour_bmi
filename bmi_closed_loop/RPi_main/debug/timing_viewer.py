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
                   thresh: float | None = None) -> tuple:
    """Rising-edge detection on abs(ch) — works regardless of output polarity.
    min_gap_s=0.005 rejects noise edges closer than 5 ms (just under 6 ms min ICI).
    Returns (ch, t_edges, thresh_used)."""
    ch_abs = np.abs(ch)
    if thresh is None:
        thresh = np.nanmax(ch_abs) * 0.5
    t_edges = _rising_edges(t_s, ch_abs, threshold=thresh, min_gap_s=0.005)
    return ch, t_edges, thresh


# ── Per-run processing helper ─────────────────────────────────────────────────

def _process_run(gpio_isf: str, audio_isf: str,
                 ch1_thresh, ch2_thresh,
                 search_min_s: float, search_max_s: float) -> dict | None:
    """Load one ISF pair and return delay stats, or None if too few matches."""
    t1, ch1 = _load_isf(audio_isf)
    t2, ch2 = _load_isf(gpio_isf)
    n = min(len(t1), len(t2))
    t_s = t1[:n]; ch1 = ch1[:n]; ch2 = ch2[:n]
    ch1_peak = np.nanmax(np.abs(ch1))
    ch2_peak = np.nanmax(ch2)
    eff_ch2 = ch2_thresh if ch2_thresh is not None else (np.nanmax(ch2) + np.nanmin(ch2)) / 2
    _, t_audio, thresh1_used = _process_audio(t_s, ch1, ch1_thresh)
    t_gpio  = _rising_edges(t_s, ch2, threshold=eff_ch2)
    print(f"  ch1 peak={ch1_peak*1000:.1f} mV  thresh={thresh1_used*1000:.1f} mV  "
          f"audio_edges={len(t_audio)}  |  "
          f"ch2 peak={ch2_peak*1000:.1f} mV  thresh={eff_ch2*1000:.1f} mV  "
          f"gpio_edges={len(t_gpio)}")
    t_gpio_m, t_audio_m = _match_edges(t_gpio, t_audio, search_min_s, search_max_s)
    print(f"  matched={len(t_gpio_m)}")
    if len(t_gpio_m) < 2:
        return None
    delays = (t_audio_m - t_gpio_m) * 1000
    return {
        'delays_ms': delays,
        'n':         len(delays),
        'mean':      float(np.mean(delays)),
        'median':    float(np.median(delays)),
        'std':       float(np.std(delays)),
        'label':     audio_isf,
    }


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
    p.add_argument("--extra", nargs=2, metavar=("CH2.ISF", "CH1.ISF"),
                   action="append", default=[],
                   help="Additional ISF pair for multi-run panel; repeat as needed")
    args = p.parse_args()

    # ── Load ISF ─────────────────────────────────────────────────────────────
    print(f"Loading: {args.isf[0]}  {args.isf[1]}")
    t1, ch1 = _load_isf(args.isf[0])
    t2, ch2 = _load_isf(args.isf[1])
    n = min(len(t1), len(t2))
    t_s, ch1, ch2 = t1[:n], ch1[:n], ch2[:n]
    sample_rate = 1.0 / (t_s[1] - t_s[0])
    print(f"  {n} samples  duration={t_s[-1]-t_s[0]:.3f} s  rate={sample_rate:.0f} Hz")

    ch1_proc, t_audio, ch1_thresh = _process_audio(t_s, ch1, args.ch1_thresh)
    print(f"  Audio threshold: {ch1_thresh*1000:.2f} mV")

    # ── GPIO trigger edges ────────────────────────────────────────────────────
    ch2_thresh = args.ch2_thresh if args.ch2_thresh is not None else (np.nanmax(ch2) + np.nanmin(ch2)) / 2
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

        ch_pwm_proc, t_pwm_edges, ch3_thresh = _process_audio(
            t_s[:np_], ch_pwm_raw, args.ch3_thresh)
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

    # ── Extra runs for multi-run panel ───────────────────────────────────────
    extra_runs = []
    for gpio_isf, audio_isf in args.extra:
        print(f"Loading extra: {gpio_isf}  {audio_isf}")
        run = _process_run(gpio_isf, audio_isf,
                           args.ch1_thresh, args.ch2_thresh,
                           args.search_min / 1000, args.search_max / 1000)
        if run is None:
            print(f"  WARNING: too few matches — skipping")
        else:
            extra_runs.append(run)
            print(f"  n={run['n']}  mean={run['mean']:.3f} ms  std={run['std']:.4f} ms")

    # ── Time axes — origin at first GPIO edge, audio shifted by mean delay ───
    t_origin   = t_gpio[0]
    t_ms       = (t_s - t_origin) * 1000
    t_audio_ms = (t_s - t_origin - mean_delay / 1000) * 1000
    if has_pwm:
        t_pwm_ms = (t_s - t_origin - mean_pwm_delay / 1000) * 1000

    # ── Figure ────────────────────────────────────────────────────────────────
    has_multi = len(extra_runs) > 0
    panel_heights = [2.5, 1.2]
    if has_pwm:   panel_heights.append(1.0)
    if has_multi: panel_heights.append(1.4)
    n_panels = len(panel_heights)
    fig = plt.figure(figsize=(14, 4 + sum(panel_heights)))
    gs = gridspec.GridSpec(n_panels, 1, figure=fig,
                           height_ratios=panel_heights, hspace=0.50)

    C_AUDIO = "#4e79a7"   # blue
    C_GPIO  = "red"
    C_PWM   = "#f28e2b"   # orange

    # ── Panel 1: waveform overlay (twinx) ────────────────────────────────────
    ax_w  = fig.add_subplot(gs[0])
    ax_w2 = ax_w.twinx()

    ax_w.plot(t_audio_ms, ch1_proc, color=C_AUDIO, lw=0.8, alpha=0.85,
              label=f"Audio (shifted −{mean_delay:.1f} ms)")

    if has_pwm:
        ax_w.plot(t_pwm_ms, ch_pwm_proc, color=C_PWM, lw=0.8, alpha=0.85,
                  label=f"PWM (shifted −{mean_pwm_delay:.1f} ms)")

    ax_w2.plot(t_ms, ch2, color=C_GPIO, lw=0.8, alpha=0.85, label="GPIO trigger")

    # Click index labels — light vertical line + index number at top of panel
    t_gpio_plot = (t_gpio_m - t_origin) * 1000
    for i, tg in enumerate(t_gpio_plot):
        ax_w.axvline(tg, color="gray", lw=0.5, alpha=0.25, zorder=0)
        ax_w.text(tg, 1.01, str(i), transform=ax_w.get_xaxis_transform(),
                  ha="center", va="bottom", fontsize=6, color="gray")

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

    # ── Panel: multi-run delay (optional) ────────────────────────────────────
    if has_multi:
        multi_idx = 2 + (1 if has_pwm else 0)
        ax_m = fig.add_subplot(gs[multi_idx])
        cmap = plt.cm.tab10

        # Primary run as run 0
        all_runs = [{'delays_ms': delays_ms, 'n': n_matched,
                     'mean': mean_delay, 'median': median_delay,
                     'std': std_delay, 'label': args.isf[1]}] + extra_runs

        x_offset = 0
        for r_idx, run in enumerate(all_runs):
            color = cmap(r_idx / max(len(all_runs) - 1, 1))
            xs = range(x_offset, x_offset + run['n'])
            ax_m.scatter(xs, run['delays_ms'], s=10, alpha=0.5, color=color, zorder=2)
            ax_m.axhline(run['mean'], color=color, lw=1.2, linestyle="--", alpha=0.8)
            if x_offset > 0:
                ax_m.axvline(x_offset - 0.5, color="lightgray", lw=0.8, zorder=0)
            ax_m.text(x_offset + run['n'] / 2, 0.97,
                      f"#{r_idx}\nn={run['n']}\nμ={run['mean']:.2f}\nσ={run['std']:.3f}",
                      ha="center", va="top", fontsize=6, color=color,
                      transform=ax_m.get_xaxis_transform())
            x_offset += run['n']

        all_delays_pool = np.concatenate([r['delays_ms'] for r in all_runs])
        pool_mean   = float(np.mean(all_delays_pool))
        pool_median = float(np.median(all_delays_pool))
        pool_std    = float(np.std(all_delays_pool))

        ax_m.axhline(pool_mean,   color="black", lw=1.5, linestyle="-",
                     label=f"all mean {pool_mean:.3f} ms")
        ax_m.axhline(pool_median, color="gray",  lw=1.0, linestyle="--",
                     label=f"all median {pool_median:.3f} ms")
        ax_m.axhspan(pool_mean - pool_std, pool_mean + pool_std,
                     color="black", alpha=0.07, label=f"±1σ ({pool_std:.4f} ms)")
        ax_m.yaxis.set_major_locator(plt.MultipleLocator(1))
        ax_m.yaxis.set_minor_locator(plt.MultipleLocator(0.25))
        ax_m.grid(which="major", alpha=0.4)
        ax_m.grid(which="minor", alpha=0.15)
        ax_m.set_xlabel("Click index (cumulative across runs)")
        ax_m.set_ylabel("Audio delay (ms)")
        ax_m.set_xlim(-1, x_offset + 1)
        ax_m.legend(fontsize=8, loc="upper right")
        ax_m.set_title(
            f"All {len(all_runs)} runs  |  "
            f"N={len(all_delays_pool)} clicks  |  "
            f"mean={pool_mean:.3f} ms   median={pool_median:.3f} ms   std={pool_std:.4f} ms",
            fontsize=9)

    # ── Navigation ────────────────────────────────────────────────────────────
    win_ms = [args.win_ms]
    pos_ms = [0.0]   # first GPIO edge is now at t=0

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
