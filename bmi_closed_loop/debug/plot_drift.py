"""
plot_drift.py — plots clock drift from drift_cage_N.csv files produced by frame_writer.py.

Each CSV row has:
    pc_ts  — PC wall-clock at UDP receive (Unix epoch seconds, float)
    pi_ts  — Pi timestamp from frame header (microseconds, Pi clock)
    pi_seq — Pi frame counter

Drift metric:
    raw_delta(t)  = pc_ts * 1e6 - pi_ts          # microseconds, arbitrary offset
    drift(t)      = raw_delta(t) - raw_delta(t0)  # μs relative to first sample
    drift_ms(t)   = drift(t) / 1000               # milliseconds

If drift_ms increases → Pi clock runs slow (loses time vs PC).
If drift_ms decreases → Pi clock runs fast (gains time vs PC).
Network jitter (~±0.5 ms) adds noise but the trend is clear over hours.

Usage:
    python debug/plot_drift.py /path/to/session_dir/
    python debug/plot_drift.py drift_cage_1.csv drift_cage_2.csv ...
"""

import sys
import os
import glob

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


# ── Load ──────────────────────────────────────────────────────────────────────

def load_cage(path: str) -> dict | None:
    """Returns {t_min, drift_ms, pi_seq, cage_id} or None on error."""
    pc_ts_list, pi_ts_list, pi_seq_list = [], [], []

    try:
        with open(path) as f:
            header = f.readline()  # skip header
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 3:
                    continue
                try:
                    pc_ts_list.append(float(parts[0]))
                    pi_ts_list.append(int(parts[1]))
                    pi_seq_list.append(int(parts[2]))
                except ValueError:
                    continue
    except OSError as e:
        print(f"Cannot read {path}: {e}")
        return None

    if len(pc_ts_list) < 2:
        print(f"Too few samples in {path}, skipping.")
        return None

    pc  = np.array(pc_ts_list)
    pi  = np.array(pi_ts_list, dtype=np.float64)
    seq = np.array(pi_seq_list)

    raw_delta = pc * 1e6 - pi           # μs, arbitrary baseline
    drift_us  = raw_delta - raw_delta[0]
    drift_ms  = drift_us / 1000.0

    # Time axis: minutes from first sample
    t_min = (pc - pc[0]) / 60.0

    # Infer cage id from filename
    basename = os.path.basename(path)
    cage_id = None
    for part in basename.replace(".csv", "").split("_"):
        try:
            cage_id = int(part)
        except ValueError:
            pass

    return {
        "cage_id":  cage_id,
        "path":     path,
        "t_min":    t_min,
        "drift_ms": drift_ms,
        "pi_seq":   seq,
        "n":        len(pc),
        "duration_min": t_min[-1],
    }


def cage_color(cage_id, n=12):
    import matplotlib.cm as cm
    if cage_id is None:
        return "gray"
    return cm.tab20(((cage_id - 1) % n) / max(n - 1, 1))


# ── Summary ───────────────────────────────────────────────────────────────────

def summary(cages: list[dict]):
    print(f"\n{'Cage':>5}  {'Samples':>8}  {'Duration':>10}  "
          f"{'Drift end (ms)':>15}  {'Rate (ms/hr)':>13}  {'Noise ±ms':>10}")
    print("-" * 70)
    for d in sorted(cages, key=lambda x: x["cage_id"] or 0):
        dur_h = d["duration_min"] / 60.0
        drift_end = d["drift_ms"][-1]
        rate = drift_end / dur_h if dur_h > 0 else 0
        # noise = std of residuals after linear fit
        t = d["t_min"]
        fit = np.polyfit(t, d["drift_ms"], 1)
        residuals = d["drift_ms"] - np.polyval(fit, t)
        noise = residuals.std()
        print(f"{d['cage_id']:>5}  {d['n']:>8}  "
              f"{d['duration_min']:>9.1f}m  "
              f"{drift_end:>+15.2f}  "
              f"{rate:>+13.3f}  "
              f"{noise:>10.3f}")
    print()


# ── Plot ──────────────────────────────────────────────────────────────────────

def plot(cages: list[dict], out_path: str):
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.suptitle("Pi → PC clock drift", fontsize=11, y=0.98)

    # ── Drift traces ──────────────────────────────────────────────────────────
    ax = axes[0]
    for d in cages:
        color = cage_color(d["cage_id"])
        ax.plot(d["t_min"], d["drift_ms"],
                linewidth=0.6, alpha=0.6, color=color, label=f"Cage {d['cage_id']}")

        # Linear trend line
        t = d["t_min"]
        fit = np.polyfit(t, d["drift_ms"], 1)
        ax.plot(t, np.polyval(fit, t),
                linewidth=1.5, color=color, linestyle="--", alpha=0.9)

    ax.axhline(0, color="#aaa", linewidth=0.7, linestyle=":")
    ax.set_ylabel("Drift (ms)\nrelative to first sample")
    ax.set_title("Clock drift — raw (thin) and linear trend (dashed)", fontsize=9)
    ax.legend(ncol=6, fontsize=6.5, loc="best")
    ax.grid(True, linewidth=0.4, alpha=0.4)

    # ── Drift rate bar chart ──────────────────────────────────────────────────
    ax = axes[1]
    rates, labels, colors = [], [], []
    for d in sorted(cages, key=lambda x: x["cage_id"] or 0):
        t = d["t_min"]
        dur_h = d["duration_min"] / 60.0
        fit = np.polyfit(t, d["drift_ms"], 1)
        # slope is ms/min → convert to ms/hr
        rate_ms_hr = fit[0] * 60.0
        rates.append(rate_ms_hr)
        labels.append(f"Cage {d['cage_id']}")
        colors.append(cage_color(d["cage_id"]))

    bars = ax.bar(labels, rates, color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Drift rate (ms / hour)")
    ax.set_title("Linear drift rate per cage  [+ = Pi loses time, − = Pi gains time]", fontsize=9)
    ax.tick_params(axis="x", labelsize=7, rotation=45)
    ax.grid(True, axis="y", linewidth=0.4, alpha=0.4)

    # Value labels on bars
    for bar, val in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (0.02 if val >= 0 else -0.05),
                f"{val:+.2f}", ha="center", va="bottom" if val >= 0 else "top",
                fontsize=6.5)

    axes[-1].xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: f"{int(x // 60)}h{int(x % 60):02d}m" if x >= 60 else f"{x:.0f}m"
    ))

    plt.tight_layout()
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
        # Auto-pick newest session dir under NAS_BASE_PATH
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
                os.path.join(os.path.dirname(__file__), "..", "NAS", "**", "drift_cage_*.csv"),
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

    # Output plot next to first CSV
    out = os.path.join(os.path.dirname(csv_paths[0]), "drift_plot.png")
    plot(cages, out)


if __name__ == "__main__":
    main()
