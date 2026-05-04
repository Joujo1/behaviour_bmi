"""
Click waveform visualiser — plots the exact waveform used in production.

Calls audio.build_click() with the given parameters (defaults match config.py)
so any waveform changes are reflected automatically.

Usage:
    python3 debug/clickplot.py
    python3 debug/clickplot.py --width 0.004 --ramp 0.001 --att 30
    python3 debug/clickplot.py --tones 2000 4000 8000 --out output/click.png
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np
import matplotlib.pyplot as plt

from audio import SRATE, RAMP, TONES, ATT_DB
from config import CLICK_WIDTH_S


def main():
    p = argparse.ArgumentParser(description="Click waveform visualiser")
    p.add_argument("--width",  type=float, default=CLICK_WIDTH_S,
                   help=f"Click width in seconds (default {CLICK_WIDTH_S*1000:.0f} ms)")
    p.add_argument("--ramp",   type=float, default=RAMP,
                   help=f"Cosine² ramp duration in seconds (default {RAMP*1000:.0f} ms)")
    p.add_argument("--att",    type=float, default=ATT_DB,
                   help=f"Attenuation in dB before peak-normalisation (default {ATT_DB} dB)")
    p.add_argument("--tones",  type=float, nargs="+", default=TONES,
                   help=f"Tone frequencies in Hz (default {TONES})")
    p.add_argument("--srate",  type=int,   default=SRATE,
                   help=f"Sample rate in Hz (default {SRATE})")
    p.add_argument("--out",    default=None, help="Save PNG to this path")
    args = p.parse_args()

    from audio import build_click
    click = build_click(srate=args.srate, width=args.width,
                        ramp=args.ramp, tones=args.tones, att_db=args.att)

    t_ms = np.arange(len(click)) / args.srate * 1000

    N        = 1 << 15
    spectrum = np.abs(np.fft.rfft(click.astype(np.float64), N)) ** 2
    freqs    = np.fft.rfftfreq(N, 1 / args.srate)
    spec_db  = 10 * np.log10(spectrum / spectrum.max() + 1e-12)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))
    fig.suptitle(
        f"Click waveform  "
        f"(tones={[int(f) for f in args.tones]} Hz, "
        f"width={args.width*1000:.1f} ms, "
        f"ramp={args.ramp*1000:.1f} ms, "
        f"att={args.att:.0f} dB)",
        fontsize=11,
    )

    ax1.plot(t_ms, click, color="#1f77b4", linewidth=1)
    ax1.axhline(0, color="k", linewidth=0.5, alpha=0.3)
    ax1.axvline(args.ramp * 1000, color="grey", linewidth=0.7, linestyle=":",
                label=f"ramp end ({args.ramp*1000:.1f} ms)")
    ax1.axvline((args.width - args.ramp) * 1000, color="grey", linewidth=0.7,
                linestyle=":")
    ax1.set_xlabel("Time (ms)")
    ax1.set_ylabel("Amplitude (peak-normalised)")
    ax1.set_title("Waveform")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)

    ax2.plot(freqs / 1000, spec_db, color="#d62728", linewidth=1.2)
    for f in args.tones:
        ax2.axvline(f / 1000, color="k", linestyle="--", linewidth=0.6, alpha=0.4)
        ax2.text(f / 1000, 3, f"{int(f)//1000}k", ha="center", fontsize=8)
    ax2.set_xlabel("Frequency (kHz)")
    ax2.set_ylabel("Power (dB, normalised)")
    ax2.set_xscale("log")
    ax2.set_xlim(0.5, args.srate / 2000)
    ax2.set_ylim(-80, 10)
    ax2.grid(alpha=0.3, which="both")
    ax2.set_title("Power spectrum")

    plt.tight_layout()

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        fig.savefig(args.out, dpi=150, bbox_inches="tight")
        print(f"Saved → {args.out}")

    plt.show()


if __name__ == "__main__":
    main()
