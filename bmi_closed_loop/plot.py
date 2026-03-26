"""
Usage:
    python plot.py                          # uses default CSV path
    python plot.py logs/debug_queues.csv    # custom path
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "logs/debug_queues.csv"
CAGES     = [1, 2, 3, 4, 5]
QUEUE_MAX = 60

COLOURS = {
    "fps":   "#2196F3",   # blue
    "queue": "#FF9800",   # orange
    "drops": "#F44336",   # red
}

df = pd.read_csv(CSV_PATH)
df = df[df["cage_id"].isin(CAGES)].copy()
df["time"] = pd.to_datetime(df["timestamp"], unit="s")
df = df.sort_values(["cage_id", "time"])

n = len(CAGES)
fig, axes = plt.subplots(3, n, figsize=(n * 4, 9), sharex=False)
fig.suptitle("BMI Acquisition Monitor", fontsize=14, fontweight="bold", y=1.01)

ROW_LABELS = ["FPS", "UDP Queue Depth", "Drops (cumulative)"]

for col, cage_id in enumerate(CAGES):
    sub = df[df["cage_id"] == cage_id].copy()

    if sub.empty:
        for row in range(3):
            axes[row][col].set_visible(False)
        continue

    sub["fps"]        = (sub["frames_written"].diff() / sub["timestamp"].diff()).clip(lower=0)
    sub["total_drops"] = sub["drop_count"] + sub["network_drop_count"]

    rows_data = [sub["fps"], sub["udp_queue"], sub["total_drops"]]
    colours   = [COLOURS["fps"], COLOURS["queue"], COLOURS["drops"]]

    for row, (data, colour) in enumerate(zip(rows_data, colours)):
        ax = axes[row][col]
        ax.plot(sub["time"], data, linewidth=1.2, color=colour)
        ax.fill_between(sub["time"], data, alpha=0.15, color=colour)

        # Titles and labels
        if row == 0:
            ax.set_title(f"Cage {cage_id}", fontsize=12, fontweight="bold", pad=6)
        if col == 0:
            ax.set_ylabel(ROW_LABELS[row], fontsize=9)

        # Queue capacity line
        if row == 1:
            ax.axhline(QUEUE_MAX, color="red", linestyle="--", linewidth=1.0, alpha=0.6, label=f"max ({QUEUE_MAX})")
            ax.set_ylim(bottom=0, top=QUEUE_MAX * 1.1)
            ax.legend(fontsize=7, loc="upper right")

        # FPS reference line at expected 60
        if row == 0:
            ax.axhline(60, color="green", linestyle="--", linewidth=1.0, alpha=0.5, label="target 60")
            ax.set_ylim(bottom=0)
            ax.legend(fontsize=7, loc="upper right")

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=25, ha="right", fontsize=7)
        ax.grid(True, alpha=0.2, linestyle="--")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

plt.tight_layout()
plt.show()
