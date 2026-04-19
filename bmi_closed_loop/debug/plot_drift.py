"""
plot_drift.py  —  Pi→PC clock drift using robust one-way estimation.

Method
------
  offset(i) = pc_ts(i) − pi_ts(i) / 1e6          # seconds; const + latency + drift
  Fit  offset(t) ≈ a·t + b  →  a is drift in s/s, a × 1e6 in ppm.

UDP latency is one-sided (hard lower bound, long upper tail), so plain OLS
gets pulled high by outliers.  Two robust estimators are used instead:

  Lower envelope  — 10 s time bins, minimum offset per bin, OLS through the
                    minima.  Bin minima are the lowest-latency packets and give
                    the cleanest view of the true clock relationship.

  Theil–Sen       — median of all pairwise slopes (scipy.stats.theilslopes).
                    Very tolerant of the upper tail.

If the two estimates agree the result is reliable.  A large disagreement
suggests an NTP step, thermal transient, or packet reordering.

Usage:
    python debug/plot_drift.py /path/to/session_dir/
    python debug/plot_drift.py drift_cage_1.csv drift_cage_2.csv ...
    python debug/plot_drift.py          # auto-picks newest session under NAS
"""

import sys
import os
import glob

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from scipy.stats import theilslopes


BIN_S = 10.0  # seconds per bin for lower-envelope


# ── Load & analyse one cage ───────────────────────────────────────────────────

def load_cage(path: str) -> dict | None:
    pc_list, pi_list, seq_list = [], [], []

    try:
        with open(path) as f:
            f.readline()  # header
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 3:
                    continue
                try:
                    pc_list.append(float(parts[0]))
                    pi_list.append(float(parts[1]))
                    seq_list.append(int(parts[2]))
                except ValueError:
                    continue
    except OSError as e:
        print(f"Cannot read {path}: {e}")
        return None

    if len(pc_list) < 10:
        print(f"Too few samples in {path}, skipping.")
        return None

    pc  = np.array(pc_list)
    pi  = np.array(pi_list, dtype=np.float64)

    # Time axis: seconds from first sample
    t = pc - pc[0]

    # Offset: both clocks in seconds
    offset = pc - pi / 1e6

    # ── Lower envelope ────────────────────────────────────────────────────────
    edges = np.arange(0, t[-1] + BIN_S, BIN_S)
    env_t, env_o = [], []
    for i in range(len(edges) - 1):
        mask = (t >= edges[i]) & (t < edges[i + 1])
        if mask.sum() > 0:
            j = np.argmin(offset[mask])
            env_t.append(t[mask][j])
            env_o.append(offset[mask][j])
    env_t = np.array(env_t)
    env_o = np.array(env_o)
    env_fit  = np.polyfit(env_t, env_o, 1)   # [slope s/s, intercept s]
    env_ppm  = env_fit[0] * 1e6

    # ── Theil–Sen on all data ─────────────────────────────────────────────────
    ts       = theilslopes(offset, t)
    ts_slope = ts.slope                       # s/s
    ts_inter = ts.intercept
    ts_ppm   = ts_slope * 1e6

    # ── Noise: std of residuals from lower-envelope fit ───────────────────────
    residuals = (offset - np.polyval(env_fit, t)) * 1000  # ms
    noise_ms  = residuals.std()

    # ── Cage id from filename ─────────────────────────────────────────────────
    cage_id = None
    for part in os.path.basename(path).replace(".csv", "").split("_"):
        try:
            cage_id = int(part)
        except ValueError:
            pass

    # For display: center offset at first sample, convert to ms
    offset_ms = (offset - offset[0]) * 1000

    # Fit lines in display coordinates (ms, t in seconds)
    def fit_display(slope_ss, intercept_s):
        # (slope·t + intercept − offset[0]) × 1000
        return (slope_ss * t + intercept_s - offset[0]) * 1000

    env_line = fit_display(env_fit[0], env_fit[1])
    ts_line  = fit_display(ts_slope,   ts_inter)

    # Lower-envelope points in display coords
    env_o_disp = (env_o - offset[0]) * 1000

    return {
        "cage_id":      cage_id,
        "path":         path,
        "t":            t,
        "offset_ms":    offset_ms,   # display: ms, centred at t=0
        "env_t":        env_t,
        "env_o_disp":   env_o_disp,
        "env_line":     env_line,
        "env_ppm":      env_ppm,
        "ts_line":      ts_line,
        "ts_ppm":       ts_ppm,
        "noise_ms":     noise_ms,
        "n":            len(pc),
        "duration_min": t[-1] / 60.0,
    }


# ── Colour helper ─────────────────────────────────────────────────────────────

def cage_color(cage_id, n=12):
    import matplotlib.cm as cm
    if cage_id is None:
        return "gray"
    return cm.tab20(((cage_id - 1) % n) / max(n - 1, 1))


# ── Summary table ─────────────────────────────────────────────────────────────

def summary(cages: list[dict]):
    print(f"\n{'Cage':>5}  {'N':>6}  {'Duration':>9}  "
          f"{'LEnv (ppm)':>12}  {'Theil-Sen (ppm)':>16}  "
          f"{'Δ (ppm)':>9}  {'Noise (ms)':>11}")
    print("─" * 80)
    for d in sorted(cages, key=lambda x: x["cage_id"] or 0):
        delta = d["env_ppm"] - d["ts_ppm"]
        flag  = "⚠" if abs(delta) > max(0.5, 0.15 * abs(d["env_ppm"])) else ""
        print(f"{d['cage_id']:>5}  {d['n']:>6}  "
              f"{d['duration_min']:>8.1f}m  "
              f"{d['env_ppm']:>+12.3f}  "
              f"{d['ts_ppm']:>+16.3f}  "
              f"{delta:>+9.3f}  "
              f"{d['noise_ms']:>10.3f}  {flag}")
    print()


# ── Plot ──────────────────────────────────────────────────────────────────────

ROW_H = 3.8   # inches per cage row
FIG_W = 15.0

def _fmt_time(x, _):
    x = max(x, 0)
    return f"{int(x // 60)}h{int(x % 60):02d}m" if x >= 60 else f"{x:.0f}m"


def plot(cages: list[dict], out_path: str):
    cages_sorted = sorted(cages, key=lambda x: x["cage_id"] or 0)
    n = len(cages_sorted)

    # ── Figure: one row per cage + one summary row at the bottom ─────────────
    height_ratios = [1.0] * n + [0.9]
    fig, axes = plt.subplots(
        n + 1, 1,
        figsize=(FIG_W, ROW_H * n + 3.0),
        gridspec_kw={"height_ratios": height_ratios},
    )
    fig.suptitle("Pi → PC clock drift  (one-way UDP timestamping)\n"
                 "Solid = lower-envelope fit  |  Dashed = Theil–Sen  |"
                 "  · = per-bin minima  |  faint = raw",
                 fontsize=10, y=1.0)

    time_fmt = ticker.FuncFormatter(_fmt_time)

    # ── One subplot per cage ──────────────────────────────────────────────────
    for i, d in enumerate(cages_sorted):
        ax    = axes[i]
        color = cage_color(d["cage_id"])
        t_min = d["t"] / 60.0

        ax.plot(t_min, d["offset_ms"],
                linewidth=0.5, alpha=0.3, color=color)

        ax.scatter(d["env_t"] / 60.0, d["env_o_disp"],
                   s=6, color=color, alpha=0.75, zorder=3)

        ax.plot(t_min, d["env_line"],
                linewidth=1.8, color=color, linestyle="-")

        ax.plot(t_min, d["ts_line"],
                linewidth=1.1, color=color, linestyle="--", alpha=0.85)

        ax.axhline(0, color="#bbb", linewidth=0.6, linestyle=":")
        ax.grid(True, linewidth=0.35, alpha=0.4)
        ax.xaxis.set_major_formatter(time_fmt)
        ax.set_ylabel("offset (ms)", fontsize=8)

        # Drift annotation top-right
        delta = d["env_ppm"] - d["ts_ppm"]
        flag  = "  ⚠ disagree" if abs(delta) > max(0.5, 0.15 * abs(d["env_ppm"])) else ""
        ax.set_title(
            f"Cage {d['cage_id']}   "
            f"env {d['env_ppm']:+.3f} ppm   "
            f"Theil-Sen {d['ts_ppm']:+.3f} ppm   "
            f"Δ {delta:+.3f} ppm   "
            f"noise ±{d['noise_ms']:.2f} ms"
            f"{flag}",
            fontsize=8.5, loc="left",
        )

        if i < n - 1:
            ax.tick_params(labelbottom=False)
        else:
            ax.set_xlabel("Time from session start", fontsize=8)

    # ── Summary bar chart (bottom row) ───────────────────────────────────────
    ax    = axes[-1]
    x     = np.arange(n)
    w     = 0.35
    colors = [cage_color(d["cage_id"]) for d in cages_sorted]

    b_env = ax.bar(x - w / 2, [d["env_ppm"] for d in cages_sorted],
                   w, color=colors, alpha=0.85,
                   edgecolor="black", linewidth=0.5, label="Lower envelope")
    b_ts  = ax.bar(x + w / 2, [d["ts_ppm"]  for d in cages_sorted],
                   w, color=colors, alpha=0.4,
                   edgecolor="black", linewidth=0.5, hatch="//", label="Theil–Sen")

    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"Cage {d['cage_id']}" for d in cages_sorted], fontsize=8)
    ax.set_ylabel("ppm", fontsize=8)
    ax.set_title("Drift rate summary  [+ = Pi loses time,  − = Pi gains time]",
                 fontsize=8.5, loc="left")
    ax.legend(fontsize=7.5, loc="upper right")
    ax.grid(True, axis="y", linewidth=0.35, alpha=0.4)

    for bar in list(b_env) + list(b_ts):
        v = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2,
                v + (0.005 if v >= 0 else -0.03),
                f"{v:+.2f}",
                ha="center", va="bottom" if v >= 0 else "top", fontsize=6)

    plt.tight_layout(rect=[0, 0, 1, 0.99])
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {out_path}")
    plt.show()


# ── Entry point ───────────────────────────────────────────────────────────────

def resolve_paths(args: list[str]) -> list[str]:
    paths = []
    for arg in args:
        if os.path.isdir(arg):
            found = sorted(glob.glob(os.path.join(arg, "drift_cage_*.csv")))
            if not found:
                print(f"No drift_cage_*.csv found in {arg}")
            paths.extend(found)
        elif "*" in arg:
            paths.extend(sorted(glob.glob(arg)))
        else:
            paths.append(arg)
    return paths


def main():
    if len(sys.argv) > 1:
        csv_paths = resolve_paths(sys.argv[1:])
    else:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "config",
                os.path.join(os.path.dirname(__file__), "..", "config.py")
            )
            cfg = importlib.util.load_from_spec(spec)
            spec.loader.exec_module(cfg)
            base = cfg.NAS_BASE_PATH
        except Exception:
            base = None

        if base and os.path.isdir(base):
            session_dirs = sorted(
                [os.path.join(base, d) for d in os.listdir(base)
                 if os.path.isdir(os.path.join(base, d))],
                key=os.path.getmtime
            )
            if session_dirs:
                csv_paths = resolve_paths([session_dirs[-1]])
                print(f"Auto-picked session: {session_dirs[-1]}")
            else:
                csv_paths = []
        else:
            csv_paths = sorted(glob.glob(
                os.path.join(os.path.dirname(__file__), "..", "NAS",
                             "**", "drift_cage_*.csv"),
                recursive=True
            ))

    if not csv_paths:
        print("Usage: python debug/plot_drift.py <session_dir | drift_cage_*.csv ...>")
        sys.exit(1)

    cages = [load_cage(p) for p in csv_paths]
    cages = [c for c in cages if c is not None]

    if not cages:
        print("No valid drift data loaded.")
        sys.exit(1)

    summary(cages)

    out = os.path.join(os.path.dirname(csv_paths[0]), "drift_plot.png")
    plot(cages, out)


if __name__ == "__main__":
    main()
