# run_once_generate_waveform.py
# Run this on any machine with numpy to regenerate the CLICK_WAV array
# if waveform parameters change, then paste the output into click_player.ino.

import numpy as np

SRATE = 192_000
WIDTH = 0.003        # 3 ms click duration
RAMP  = 0.002        # 2 ms cosine² taper on each end
TONES = [2000, 4000, 8000, 16000]
ATT   = 10 ** (-40 / 20)   # 40 dB attenuation per tone

n   = int(WIDTH * SRATE)    # 576 samples
t   = np.arange(n) / SRATE

snd = np.zeros(n)
for f in TONES:
    snd += ATT * np.sin(2 * np.pi * f * t)

r_n  = int(RAMP * SRATE)    # 384 samples
ramp = np.cos(np.arange(r_n) / r_n * np.pi / 2) ** 2
snd[:r_n]  *= ramp[::-1]    # fade in  (cos² goes 0→1)
snd[-r_n:] *= ramp           # fade out (cos² goes 1→0)
snd /= np.max(np.abs(snd))  # peak normalise to ±1.0

# Convert to 12-bit unsigned centred at 2048 (= DAC silence level)
wav = np.clip(np.round(snd * 2047 + 2048), 0, 4095).astype(np.uint16)

print(f"#define CLICK_LEN {n}")
print(f"const uint16_t CLICK_WAV[CLICK_LEN] = {{")
for i in range(0, n, 16):
    print("  " + ", ".join(str(v) for v in wav[i:i+16]) + ",")
print("};")
