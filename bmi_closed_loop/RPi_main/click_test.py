"""
    python click_test.py                          # 10 clicks/s mono
    python click_test.py --rate 5                 # 5 clicks/s mono
    python click_test.py --ici 0.2                # 200 ms ICI mono
    python click_test.py --left 40 --right 10     # stereo Poisson
"""

import argparse

import numpy as np
import sounddevice as sd

# ── Click parameters (match clickplot.py / Brody lab spec) ──────────────────
SRATE   = 48_000                        # Hz — Pi 4 audio jack max
WIDTH   = 0.003                         # 3 ms click duration
RAMP    = 0.002                         # 2 ms cosine-squared fade in/out
TONES   = [2000, 4000, 8000, 16000]     # Hz — 32kHz dropped (aliases at 48kHz)
ATT_DB  = 40                            # dB attenuation

BUFFER_S = 2.0                          # seconds of audio pre-generated per chunk


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


def generate_poisson_buffer(click: np.ndarray, left_rate: float,
                             right_rate: float, duration: float) -> np.ndarray:
    """Generate a stereo buffer with independent Poisson click trains per channel."""
    n_samples = int(duration * SRATE)
    buf = np.zeros((n_samples, 2), dtype=np.float32)
    click_len = len(click)

    for ch, rate in enumerate([left_rate, right_rate]):
        t = 0.0
        while t < duration:
            t += np.random.exponential(1.0 / rate)
            i = int(t * SRATE)
            if i + click_len <= n_samples:
                buf[i:i + click_len, ch] += click

    np.clip(buf, -1.0, 1.0, out=buf)
    return buf


def main():
    parser = argparse.ArgumentParser()
    mono_group = parser.add_mutually_exclusive_group()
    mono_group.add_argument("--rate", type=float, default=None,
                            help="mono clicks per second (default 10)")
    mono_group.add_argument("--ici",  type=float,
                            help="mono inter-click interval in seconds")
    parser.add_argument("--left",    type=float, default=None,
                        help="left clicks per trial (Poisson mean)")
    parser.add_argument("--right",   type=float, default=None,
                        help="right clicks per trial (Poisson mean)")
    parser.add_argument("--seconds", type=float, default=1.0,
                        help="trial duration in seconds (default 1.0)")
    parser.add_argument("--gap",     type=float, default=0.0,
                        help="silence between trials in seconds (default 0)")
    args = parser.parse_args()

    click = build_click()
    stereo_mode = args.left is not None or args.right is not None

    if stereo_mode:
        duration   = args.seconds
        left_rate  = (args.left  or 0.0) / duration
        right_rate = (args.right or 0.0) / duration
        print(f"Stereo Poisson — left: {args.left or 0:.1f} clicks  "
              f"right: {args.right or 0:.1f} clicks  over {duration:.1f}s")
        print("Playing — Ctrl+C to stop\n")

        gap_samples = int(args.gap * SRATE)
        silence = np.zeros((gap_samples, 2), dtype=np.float32)

        try:
            with sd.OutputStream(samplerate=SRATE, channels=2,
                                  device=1, dtype='float32') as stream:
                while True:
                    buf = generate_poisson_buffer(click, left_rate, right_rate, duration)
                    stream.write(buf)
                    if gap_samples:
                        stream.write(silence)
        except KeyboardInterrupt:
            print("\nStopped.")

    else:
        ici = args.ici if args.ici is not None else 1.0 / (args.rate or 10.0)
        print(f"Mono — rate: {1/ici:.1f} clicks/s  ICI: {ici*1000:.0f} ms")
        print("Playing — Ctrl+C to stop\n")

        ici_samples = int(round(ici * SRATE))
        period = np.zeros(ici_samples, dtype=np.float32)
        period[:len(click)] = click

        try:
            with sd.OutputStream(samplerate=SRATE, channels=1,
                                  device=1, dtype='float32') as stream:
                while True:
                    stream.write(period)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
