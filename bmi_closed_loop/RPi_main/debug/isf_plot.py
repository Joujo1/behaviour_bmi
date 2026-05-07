"""
Plot Tektronix ISF waveform exports from the DPO 2024B.

Usage:
    python3 isf_plot.py ch1.isf ch2.isf      # audio + GPIO, time-aligned
    python3 isf_plot.py ch1.isf               # single channel
"""

import argparse
import sys

import numpy as np
import matplotlib.pyplot as plt


def load(path: str) -> tuple:
    """Parse a Tektronix ISF file and return (t_ms, v) numpy arrays."""
    with open(path, "rb") as f:
        raw = f.read()

    # Header ends at :CURV
    curve_idx = raw.find(b":CURV")
    if curve_idx == -1:
        curve_idx = raw.find(b"CURV")
    header = raw[:curve_idx].decode("ascii", errors="ignore")
    after  = raw[curve_idx:]

    # Tokens are semicolon-separated; each token is "KEY VALUE" (space-separated)
    params = {}
    for token in header.split(";"):
        token = token.strip()
        # Strip leading colons and subgroup prefixes (e.g. ":WFMP:NR_P" → "NR_P")
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

    # Binary data follows "#N<N digits of byte count><data>"
    hash_idx = after.index(b"#")
    n_digits = int(chr(after[hash_idx + 1]))
    data_start = hash_idx + 2 + n_digits
    data = after[data_start:data_start + nr_pt * byt_nr]

    dtype = np.dtype((">" if byt_or == "MSB" else "<") +
                     ("i" if bn_fmt == "RI" else "u") + str(byt_nr))
    y_raw = np.frombuffer(data, dtype=dtype).astype(np.float64)

    v = (y_raw - yoff) * ymult + yzero
    t = (np.arange(nr_pt) - pt_off) * xincr + xzero

    return t * 1000, v  # time in ms


def main():
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="+", help="ISF files (ch1 audio, ch2 GPIO)")
    p.add_argument("--zoom", type=float, default=None,
                   help="Zoom window in ms centred on GPIO rising edge (e.g. --zoom 10)")
    args = p.parse_args()

    channels = [load(f) for f in args.files]
    labels   = ["Ch1 — audio (V)", "Ch2 — GPIO (V)"] + [f"Ch{i+3}" for i in range(len(channels) - 2)]

    fig, axes = plt.subplots(len(channels), 1, sharex=True, figsize=(12, 3 * len(channels)))
    if len(channels) == 1:
        axes = [axes]

    for ax, (t, v), label in zip(axes, channels, labels):
        ax.plot(t, v, lw=0.8)
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Time (ms)")

    # If two channels, annotate the delay between GPIO rising edge and audio onset
    if len(channels) == 2:
        t_gpio, v_gpio = channels[1]
        threshold = (v_gpio.max() + v_gpio.min()) / 2
        rising = np.where((v_gpio[:-1] < threshold) & (v_gpio[1:] >= threshold))[0]
        if rising.size:
            t_edge = t_gpio[rising[0]]
            for ax in axes:
                ax.axvline(t_edge, color="red", lw=0.8, linestyle="--", alpha=0.7)
            axes[1].annotate(f"GPIO edge\n{t_edge:.2f} ms", xy=(t_edge, threshold),
                             xytext=(t_edge + 0.5, threshold), fontsize=8, color="red")

        if args.zoom:
            for ax in axes:
                ax.set_xlim(t_edge - args.zoom / 2, t_edge + args.zoom / 2)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
