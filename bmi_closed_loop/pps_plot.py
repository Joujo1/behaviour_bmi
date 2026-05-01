import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# --- Load data ---
pps_ns, mono_ns, seq = [], [], []
with open("pps_log.txt", "r") as f:
    f.readline()  # skip header
    for line in f:
        parts = line.split()
        if len(parts) != 3:
            continue
        pps_ns.append(int(parts[0]))
        mono_ns.append(int(parts[1]))
        seq.append(int(parts[2]))

pps_ns  = np.array(pps_ns,  dtype=np.float64)
mono_ns = np.array(mono_ns, dtype=np.float64)
seq     = np.array(seq,     dtype=int)

# Detect dropped pulses and warn
gaps = np.diff(seq)
if np.any(gaps > 1):
    dropped = np.where(gaps > 1)[0]
    print(f"Warning: {len(dropped)} dropped pulse(s) at seq: {seq[dropped]}")

# --- Compute GPS-truth elapsed and CLOCK_MONOTONIC elapsed ---
# GPS truth: each sequence step is exactly 1 second (1e9 ns)
gps_elapsed_ns  = (seq - seq[0]).astype(np.float64) * 1e9
mono_elapsed_ns = (mono_ns - mono_ns[0])

# Drift = how much CLOCK_MONOTONIC has deviated from GPS truth over time
# Positive = MONO is running fast (ahead of GPS), negative = running slow
drift_ms = (mono_elapsed_ns - gps_elapsed_ns) / 1e6
t_sec    = gps_elapsed_ns / 1e9  # wall-clock seconds (GPS truth)

# --- Linear regression on drift vs time ---
a_drift, b_drift = np.polyfit(t_sec, drift_ms, 1)  # drift_ms = a*t + b
drift_us_per_s   = a_drift * 1e3                    # convert ms/s -> µs/s
drift_ns_per_s   = drift_us_per_s * 1e3
drift_fit_ms     = a_drift * t_sec + b_drift
residuals_us     = (drift_ms - drift_fit_ms) * 1e3  # µs

print(f"Drift rate : {drift_ns_per_s:.3f} ns/s  ({drift_us_per_s:.3f} µs/s)")
print(f"Over 24 h  : {drift_us_per_s * 86400 / 1e3:.1f} ms")
print(f"Residual std: {residuals_us.std():.3f} µs")

# --- Plot ---
fig = plt.figure(figsize=(12, 10))
fig.suptitle("CLOCK_MONOTONIC drift vs GPS (PPS)", fontsize=14, fontweight="bold")
gs = gridspec.GridSpec(3, 1, hspace=0.45)

# Panel 1: cumulative drift (the money plot — mirrors Syntalos Fig. 3D)
ax1 = fig.add_subplot(gs[0])
ax1.plot(t_sec / 3600, drift_ms, linewidth=1.5, label="Measured drift")
ax1.plot(t_sec / 3600, drift_fit_ms, color="red", linewidth=1.5, linestyle="--",
         label=f"Linear fit  ({drift_us_per_s:.3f} µs/s,  {drift_us_per_s*86400/1e3:.1f} ms/24 h)")
ax1.set_xlabel("Elapsed time (hours)")
ax1.set_ylabel("MONO − GPS elapsed (ms)")
ax1.set_title("Cumulative clock drift: CLOCK_MONOTONIC relative to GPS truth")
ax1.legend()
ax1.grid(True, alpha=0.3)

# Panel 2: regression scatter (mono_elapsed vs gps_elapsed)
mono_elapsed_ms = mono_elapsed_ns / 1e6
gps_elapsed_ms  = gps_elapsed_ns  / 1e6
a2, b2 = np.polyfit(gps_elapsed_ms, mono_elapsed_ms, 1)
ax2 = fig.add_subplot(gs[1])
ax2.scatter(gps_elapsed_ms, mono_elapsed_ms, s=4, label="Measured", zorder=3)
ax2.plot(gps_elapsed_ms, a2 * gps_elapsed_ms + b2, color="red", linewidth=1.5,
         label=f"Fit  (slope={a2:.9f})")
ax2.set_xlabel("GPS elapsed (ms)")
ax2.set_ylabel("CLOCK_MONOTONIC elapsed (ms)")
ax2.set_title("Linear regression: MONO elapsed vs GPS elapsed")
ax2.legend()
ax2.grid(True, alpha=0.3)

# Panel 3: residuals after removing linear drift
ax3 = fig.add_subplot(gs[2])
ax3.plot(t_sec / 3600, residuals_us, linewidth=1, color="orange")
ax3.axhline(0, color="black", linewidth=0.8, linestyle="--")
ax3.fill_between(t_sec / 3600, residuals_us, alpha=0.2, color="orange")
ax3.set_xlabel("Elapsed time (hours)")
ax3.set_ylabel("Residual after drift removal (µs)")
ax3.set_title(f"Residuals  (std = {residuals_us.std():.3f} µs)  — jitter / non-linear effects")
ax3.grid(True, alpha=0.3)

plt.savefig("pps_analysis.png", dpi=150, bbox_inches="tight")
plt.show()
print("Saved to pps_analysis.png")