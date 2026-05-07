"""
Timing viewer — overlay GPIO and median-shifted audio waveforms.

Shifts the entire audio channel left by the median GPIO→audio delay.
If timing is consistent the two waveforms should overlap on every click.

Keys: ← / → to pan by half a window, + / - to zoom.

Usage:
    python3 debug/timing_viewer.py --isf T0000CH2.ISF T0000CH1.ISF
"""

import argparse
import sys

import numpy as np
import matplotlib.pyplot as plt
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


def _match_edges(t_gpio: np.ndarray, t_audio: np.ndarray,
                 search_min_s: float = 0.005,
                 search_max_s: float = 0.150) -> tuple:
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
            last_idx = i + 1
            break
    return np.array(mg), np.array(ma)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--isf", nargs=2, metavar=("CH1.ISF", "CH2.ISF"), required=True,
                   help="ch1=audio, ch2=GPIO")
    p.add_argument("--ch2-thresh", type=float, default=None)
    p.add_argument("--ch1-thresh", type=float, default=None)
    p.add_argument("--search-min", type=float, default=5.0)
    p.add_argument("--search-max", type=float, default=150.0)
    p.add_argument("--win-ms",  type=float, default=200.0,
                   help="Visible window width in ms (default: 200)")
    args = p.parse_args()

    # Load ISF
    print(f"Loading: {args.isf[0]}  {args.isf[1]}")
    t1, ch1 = _load_isf(args.isf[0])
    t2, ch2 = _load_isf(args.isf[1])
    n = min(len(t1), len(t2))
    t_s, ch1, ch2 = t1[:n], ch1[:n], ch2[:n]
    sample_rate = 1.0 / (t_s[1] - t_s[0])
    print(f"  {n} samples  duration={t_s[-1]-t_s[0]:.3f} s  rate={sample_rate:.0f} Hz")

    # LP filter audio at 3 kHz to suppress PWM noise before edge detection
    b, a   = _signal.butter(4, 3000 / (sample_rate / 2), btype="low")
    ch1_lp = _signal.filtfilt(b, a, ch1)

    # Edge detection + matching
    ch2_thresh = args.ch2_thresh or (np.nanmax(ch2) + np.nanmin(ch2)) / 2
    ch1_thresh = args.ch1_thresh or np.nanmax(np.abs(ch1_lp)) * 0.35

    t_gpio  = _rising_edges(t_s, ch2,    threshold=ch2_thresh)
    t_audio = _rising_edges(t_s, ch1_lp, threshold=ch1_thresh)
    print(f"  GPIO edges: {len(t_gpio)}   Audio edges: {len(t_audio)}")

    t_gpio_m, t_audio_m = _match_edges(t_gpio, t_audio,
                                        args.search_min / 1000,
                                        args.search_max / 1000)
    n_matched = len(t_gpio_m)
    print(f"  Matched: {n_matched} clicks")
    if n_matched < 2:
        print("ERROR: too few matched clicks — check --ch1-thresh / --search-min/max")
        sys.exit(1)

    delays_ms    = (t_audio_m - t_gpio_m) * 1000
    median_delay = np.median(delays_ms)
    std_delay    = np.std(delays_ms)
    print(f"  Median delay: {median_delay:.3f} ms   std: {std_delay:.4f} ms")

    # Shift entire audio time axis by -median so edges land on GPIO edges
    median_s  = median_delay / 1000
    t_audio_shifted = t_s - median_s   # audio samples plotted earlier by median

    t_ms       = t_s * 1000            # GPIO time axis in ms
    t_audio_ms = t_audio_shifted * 1000

    # ── Figure ───────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(14, 5))
    ax2 = ax.twinx()

    ax.plot(t_audio_ms, ch1_lp, color="#4e79a7", lw=0.8, alpha=0.85,
            label=f"Audio LP-filtered (shifted −{median_delay:.1f} ms)")
    ax2.plot(t_ms, ch2, color="red", lw=0.8, alpha=0.85, label="GPIO")

    ax.set_ylabel("Audio (V)",  color="#4e79a7")
    ax.tick_params(axis="y", labelcolor="#4e79a7")
    ax2.set_ylabel("GPIO (V)", color="red")
    ax2.tick_params(axis="y", labelcolor="red")
    ax.set_xlabel("Time (ms)")

    lines1, labs1 = ax.get_legend_handles_labels()
    lines2, labs2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labs1 + labs2, fontsize=9, loc="upper right")
    ax.grid(alpha=0.3)

    fig.suptitle(
        f"{n_matched} matched clicks  |  "
        f"median delay = {median_delay:.3f} ms  std = {std_delay:.4f} ms  |  "
        f"← / → to pan   + / − to zoom",
        fontsize=10, fontweight="bold"
    )

    # Start at first GPIO edge
    t0_ms   = t_gpio[0] * 1000 if len(t_gpio) else 0.0
    win_ms  = [args.win_ms]
    pos_ms  = [t0_ms]

    def set_view():
        ax.set_xlim(pos_ms[0], pos_ms[0] + win_ms[0])
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
            win_ms[0] = min((t_ms[-1] - t_ms[0]), win_ms[0] * 2.0)
            pos_ms[0] = max(t_ms[0], pos_ms[0] - win_ms[0] * 0.25)
        else:
            return
        set_view()

    fig.canvas.mpl_connect("key_press_event", on_key)
    set_view()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
