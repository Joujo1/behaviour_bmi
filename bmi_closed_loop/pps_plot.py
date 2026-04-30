import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# --- Load data ---
data = np.loadtxt("pps_log.txt", skiprows=1, usecols=(0, 1, 2))
pps_ns  = data[:, 0]
mono_ns = data[:, 1]
seq     = data[:, 2].astype(int)

# Detect dropped pulses and warn
gaps = np.diff(seq)
if np.any(gaps > 1):
    dropped = np.where(gaps > 1)[0]
    print(f"Warning: {len(dropped)} dropped pulse(s) at seq: {seq[dropped]}")

# --- Normalize to seconds from start for readability ---
t0_pps  = pps_ns[0]
t0_mono = mono_ns[0]
pps_sec  = (pps_ns  - t0_pps)  / 1e9
mono_sec = (mono_ns - t0_mono) / 1e9

# --- Linear regression: mono_ns = a * pps_ns + b ---
a, b = np.polyfit(pps_ns, mono_ns, 1)
drift_ns_per_s  = (a - 1) * 1e9
drift_us_per_s  = drift_ns_per_s / 1e3
mono_fit_ns     = a * pps_ns + b
residuals_us    = (mono_ns - mono_fit_ns) / 1e3  # µs

print(f"Drift rate : {drift_ns_per_s:.3f} ns/s  ({drift_us_per_s:.3f} µs/s)")
print(f"Offset (b) : {b/1e6:.3f} ms")
print(f"Residual std: {residuals_us.std():.3f} µs")

# --- Plot ---
fig = plt.figure(figsize=(12, 10))
fig.suptitle("PPS vs CLOCK_MONOTONIC Analysis", fontsize=14, fontweight="bold")
gs = gridspec.GridSpec(3, 1, hspace=0.45)

# Panel 1: both clocks over time
ax1 = fig.add_subplot(gs[0])
ax1.plot(pps_sec,  label="PPS (CLOCK_REALTIME, GPS truth)", linewidth=1.5)
ax1.plot(mono_sec, label="CLOCK_MONOTONIC", linewidth=1.5, linestyle="--")
ax1.set_xlabel("Pulse index (s from start)")
ax1.set_ylabel("Elapsed seconds")
ax1.set_title("Both clocks elapsed time per pulse")
ax1.legend()
ax1.grid(True, alpha=0.3)

# Panel 2: regression fit
ax2 = fig.add_subplot(gs[1])
ax2.scatter(pps_ns / 1e9, mono_ns / 1e9, s=4, label="Measured", zorder=3)
ax2.plot(pps_ns / 1e9, mono_fit_ns / 1e9, color="red", linewidth=1.5,
         label=f"Fit  (drift={drift_ns_per_s:.2f} ns/s)")
ax2.set_xlabel("PPS time (s, GPS truth)")
ax2.set_ylabel("CLOCK_MONOTONIC (s)")
ax2.set_title("Linear regression: CLOCK_MONOTONIC vs GPS truth")
ax2.legend()
ax2.grid(True, alpha=0.3)

# Panel 3: residuals
ax3 = fig.add_subplot(gs[2])
ax3.plot(pps_sec, residuals_us, linewidth=1, color="orange")
ax3.axhline(0, color="black", linewidth=0.8, linestyle="--")
ax3.fill_between(pps_sec, residuals_us, alpha=0.2, color="orange")
ax3.set_xlabel("Elapsed time (s from start)")
ax3.set_ylabel("Residual (µs)")
ax3.set_title(f"Regression residuals  (std = {residuals_us.std():.3f} µs)")
ax3.grid(True, alpha=0.3)

plt.savefig("pps_analysis.png", dpi=150, bbox_inches="tight")
plt.show()
print("Saved to pps_analysis.png")