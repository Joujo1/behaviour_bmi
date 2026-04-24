import numpy as np
import matplotlib.pyplot as plt

srate  = 48_000                                    # audio sample rate (Hz)
width  = 0.003                                      # bup_width = 3 ms
ramp   = 0.002                                      # bup_ramp  = 2 ms
tones  = np.array([2000, 4000, 8000, 16000]) # Hz
att_db = 40                                         # attenuation in dB

t = np.arange(0, width + 1/srate, 1/srate)
amp = 10 ** (-att_db / 20)

snd = np.zeros_like(t)
for f in np.unique(tones):
    snd += amp * np.sin(2 * np.pi * f * t)

# Cosine-squared edge
ramp_t = np.arange(0, ramp + 1/srate, 1/srate)
edge   = np.cos(ramp_t * np.pi / (2 * ramp)) ** 2
n_edge = len(edge)
snd[:n_edge]  *= edge[::-1]   # fade in
snd[-n_edge:] *= edge         # fade out

N            = 1 << 15
spectrum     = np.abs(np.fft.rfft(snd, N)) ** 2
freqs        = np.fft.rfftfreq(N, 1/srate)
spectrum_db  = 10 * np.log10(spectrum / spectrum.max() + 1e-12)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))
fig.suptitle(f"Click  (tones={list(tones//1000)} kHz, width={width*1000:.0f} ms, "
             f"ramp={ramp*1000:.0f} ms, att={att_db} dB)", fontsize=11)

ax1.plot(t * 1000, snd, color="#1f77b4", linewidth=1)
ax1.set_xlabel("Time (ms)")
ax1.set_ylabel("Amplitude")
ax1.axhline(0, color="k", linewidth=0.5, alpha=0.3)
ax1.grid(alpha=0.3)
ax1.set_title("Waveform")

ax2.plot(freqs / 1000, spectrum_db, color="#d62728", linewidth=1.2)
for f in tones:
    ax2.axvline(f / 1000, color="k", linestyle="--", linewidth=0.6, alpha=0.4)
    ax2.text(f / 1000, 3, f"{f//1000:.0f}", ha="center", fontsize=8)
ax2.set_xlabel("Frequency (kHz)")
ax2.set_ylabel("Power (dB, normalised)")
ax2.set_xscale("log")
ax2.set_xlim(0.5, srate / 2000)
ax2.set_ylim(-80, 10)
ax2.grid(alpha=0.3, which="both")
ax2.set_title("Power spectrum")

plt.tight_layout()
plt.show()
