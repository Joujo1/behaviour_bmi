"""
Standalone click test — plays the Brody-style broadband click continuously
via the Pi 4 3.5mm audio jack (sounddevice / ALSA).

Usage:
    python click_test.py              # 10 clicks/s
    python click_test.py --rate 5     # 5 clicks/s
    python click_test.py --ici 0.2    # 200 ms inter-click interval
Requirements:
    pip install sounddevice numpy

Hardware:
    PAM8302 IN+ → Pi 4 3.5mm tip (left channel)
    PAM8302 IN- → Pi 4 3.5mm sleeve (ground)
"""

import argparse

import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd

# ── Click parameters (match clickplot.py / Brody lab spec) ──────────────────
SRATE   = 48_000                        # Hz — Pi 4 audio jack max
WIDTH   = 0.003                         # 3 ms click duration
RAMP    = 0.002                         # 2 ms cosine-squared fade in/out
TONES   = [2000, 4000, 8000, 16000]     # Hz — 32kHz dropped (aliases at 48kHz)
ATT_DB  = 40                            # dB attenuation

sd.default.device = 1

def build_click(srate=SRATE, width=WIDTH, ramp=RAMP,
                tones=TONES, att_db=ATT_DB) -> np.ndarray:
    t   = np.arange(0, width + 1 / srate, 1 / srate)
    amp = 10 ** (-att_db / 20)

    snd = np.zeros(len(t))
    for f in tones:
        snd += amp * np.sin(2 * np.pi * f * t)

    ramp_t  = np.arange(0, ramp + 1 / srate, 1 / srate)
    edge    = np.cos(ramp_t * np.pi / (2 * ramp)) ** 2
    n_edge  = len(edge)
    snd[:n_edge]  *= edge[::-1]
    snd[-n_edge:] *= edge

    peak = np.max(np.abs(snd))
    if peak > 0:
        snd /= peak

    return snd.astype(np.float32)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--rate",  type=float, default=10.0,
                       help="clicks per second (default 10)")
    group.add_argument("--ici",   type=float,
                       help="inter-click interval in seconds (overrides --rate)")
    args = parser.parse_args()

    ici = args.ici if args.ici is not None else 1.0 / args.rate

    click = build_click()
    click_duration = len(click) / SRATE

    print(f"Click: {len(TONES)} tones {[t//1000 for t in TONES]} kHz, "
          f"{WIDTH*1000:.0f} ms wide, {ATT_DB} dB att")
    print(f"Rate:  {1/ici:.1f} clicks/s  (ICI {ici*2000:.0f} ms)")
    print("Playing — Ctrl+C to stop\n")

    # ── Plot waveform + power spectrum ────────────────────────────────────────
    t_ms = np.arange(len(click)) / SRATE * 1000
    N = 1 << 15
    spectrum    = np.abs(np.fft.rfft(click, N)) ** 2
    freqs       = np.fft.rfftfreq(N, 1 / SRATE)
    spectrum_db = 10 * np.log10(spectrum / spectrum.max() + 1e-12)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle(f"Click  (tones={[f//1000 for f in TONES]} kHz, "
                 f"width={WIDTH*1000:.0f} ms, ramp={RAMP*1000:.0f} ms, att={ATT_DB} dB)")
    ax1.plot(t_ms, click, color="#1f77b4", linewidth=1)
    ax1.set_xlabel("Time (ms)"); ax1.set_ylabel("Amplitude")
    ax1.axhline(0, color="k", linewidth=0.5, alpha=0.3)
    ax1.grid(alpha=0.3); ax1.set_title("Waveform")

    ax2.plot(freqs / 1000, spectrum_db, color="#d62728", linewidth=1.2)
    for f in TONES:
        ax2.axvline(f / 1000, color="k", linestyle="--", linewidth=0.6, alpha=0.4)
        ax2.text(f / 1000, 3, f"{f//1000:.0f}", ha="center", fontsize=8)
    ax2.set_xlabel("Frequency (kHz)"); ax2.set_ylabel("Power (dB, normalised)")
    ax2.set_xscale("log"); ax2.set_xlim(0.5, SRATE / 2000)
    ax2.set_ylim(-80, 10); ax2.grid(alpha=0.3, which="both")
    ax2.set_title("Power spectrum")

    plt.tight_layout()
    plt.show(block=False)

    # Build one ICI-length period: click followed by silence
    ici_samples = int(round(ici * SRATE))
    period = np.zeros(ici_samples, dtype=np.float32)
    period[:len(click)] = click

    try:
        with sd.OutputStream(samplerate=SRATE, channels=1, device=1, dtype='float32') as stream:
            while True:
                stream.write(period)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
