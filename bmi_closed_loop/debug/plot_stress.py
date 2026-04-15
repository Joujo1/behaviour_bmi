"""
plot_stress.py — plots a stress_log CSV produced by stress_logger.py.

Usage:
    python debug/plot_stress.py stress_log_20240101_120000.csv
    python debug/plot_stress.py             # auto-picks newest stress_log_*.csv in debug/
"""

import sys
import os
import glob
import csv
from collections import defaultdict

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


# ── Load CSV ──────────────────────────────────────────────────────────────────

def load(path: str):
    """Returns dict: cage_id → {t, fps, queue_drops, net_drops}"""
    cages = defaultdict(lambda: {"t": [], "fps": [], "queue_drops": [], "net_drops": []})

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                cage = int(row["cage"])
                pc_t = float(row["pc_time"])
                fps  = float(row["fps"]) if row["fps"] else None
                qd   = int(row["queue_drops"])   if row["queue_drops"]  else None
                nd   = int(row["net_drops"])      if row["net_drops"]    else None
                cages[cage]["t"].append(pc_t)
                cages[cage]["fps"].append(fps)
                cages[cage]["queue_drops"].append(qd)
                cages[cage]["net_drops"].append(nd)
            except (ValueError, KeyError):
                continue

    # Normalise time to minutes from start
    all_t0 = min(v["t"][0] for v in cages.values() if v["t"])
    for v in cages.values():
        v["t"] = [(t - all_t0) / 60.0 for t in v["t"]]

    return dict(cages)


# ── Helpers ───────────────────────────────────────────────────────────────────

def cage_color(cage_id: int, n: int = 12):
    import matplotlib.cm as cm
    return cm.tab20(((cage_id - 1) % n) / max(n - 1, 1))


# ── Plots ─────────────────────────────────────────────────────────────────────

def plot(data: dict, csv_path: str):
    cages = sorted(data.keys())
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(f"Stress test — {os.path.basename(csv_path)}", fontsize=11, y=0.98)

    # ── FPS per cage ──────────────────────────────────────────────────────────
    ax = axes[0]
    for cage in cages:
        d = data[cage]
        fps_vals = [v for v in d["fps"] if v is not None]
        if not fps_vals:
            continue
        ax.plot(d["t"], d["fps"], linewidth=0.8, alpha=0.85,
                color=cage_color(cage), label=f"Cage {cage}")
    ax.set_ylabel("FPS")
    ax.set_title("Frame rate per cage", fontsize=9)
    ax.axhline(60, color="#ccc", linewidth=0.7, linestyle="--")
    ax.set_ylim(bottom=0)
    ax.legend(ncol=6, fontsize=6.5, loc="lower right")
    ax.grid(True, linewidth=0.4, alpha=0.5)

    # ── Cumulative queue drops per cage ───────────────────────────────────────
    ax = axes[1]
    for cage in cages:
        d = data[cage]
        ax.plot(d["t"], d["queue_drops"], linewidth=0.9, alpha=0.85,
                color=cage_color(cage), label=f"Cage {cage}")
    ax.set_ylabel("Cumulative queue drops")
    ax.set_title("Queue drops (PC-side, UDP receive buffer full)", fontsize=9)
    ax.set_ylim(bottom=0)
    ax.legend(ncol=6, fontsize=6.5, loc="upper left")
    ax.grid(True, linewidth=0.4, alpha=0.5)

    # ── Cumulative network drops per cage ─────────────────────────────────────
    ax = axes[2]
    for cage in cages:
        d = data[cage]
        ax.plot(d["t"], d["net_drops"], linewidth=0.9, alpha=0.85,
                color=cage_color(cage), label=f"Cage {cage}")
    ax.set_ylabel("Cumulative net drops")
    ax.set_title("Network drops (gaps in Pi frame counter)", fontsize=9)
    ax.set_xlabel("Time (minutes)")
    ax.set_ylim(bottom=0)
    ax.legend(ncol=6, fontsize=6.5, loc="upper left")
    ax.grid(True, linewidth=0.4, alpha=0.5)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: f"{int(x // 60)}h{int(x % 60):02d}m" if x >= 60 else f"{x:.0f}m"
    ))

    plt.tight_layout()

    out = csv_path.replace(".csv", "_plot.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved: {out}")
    plt.show()


# ── Summary ───────────────────────────────────────────────────────────────────

def summary(data: dict):
    print(f"\n{'Cage':>5}  {'Avg FPS':>8}  {'Min FPS':>8}  {'Q drops':>8}  {'Net drops':>10}")
    print("-" * 50)
    for cage in sorted(data.keys()):
        d = data[cage]
        fps_vals = [v for v in d["fps"] if v is not None]
        avg_fps = sum(fps_vals) / len(fps_vals) if fps_vals else 0
        min_fps = min(fps_vals) if fps_vals else 0
        last_qd = next((v for v in reversed(d["queue_drops"]) if v is not None), 0)
        last_nd = next((v for v in reversed(d["net_drops"]) if v is not None), 0)
        print(f"{cage:>5}  {avg_fps:>8.2f}  {min_fps:>8.2f}  {last_qd:>8}  {last_nd:>10}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        pattern = os.path.join(os.path.dirname(__file__), "stress_log_*.csv")
        files = sorted(glob.glob(pattern))
        if not files:
            print("No stress_log_*.csv found. Pass the path as argument.")
            sys.exit(1)
        path = files[-1]
        print(f"Auto-picked: {path}")

    data = load(path)
    summary(data)
    plot(data, path)


if __name__ == "__main__":
    main()
