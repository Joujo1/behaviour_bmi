#!/usr/bin/env python3
"""
Click timing validation — oscilloscope CSV analysis.

Loads a 3-channel oscilloscope CSV export (LED GPIO / Pi TTL / ItsyBitsy DAC),
detects rising edges, aligns them to scheduled click times recovered from
PostgreSQL, and computes the three timing distributions reported in the thesis:

  Pi-side scheduling error : TTL rising edge − scheduled click time
  MCU onset latency        : DAC rising edge − preceding TTL rising edge
  End-to-end error         : DAC rising edge − scheduled click time

The LED channel rising edge defines t = 0 (state entry).  All other times
are relative to this edge.

Oscilloscope channel assignment (default, override with --col-*):
  CH1 — LED GPIO output (Pi)          defines t = 0
  CH2 — Pi click-trigger TTL line     marks when Pi fires each pulse
  CH3 — ItsyBitsy analog DAC output   marks when audio actually plays

The ItsyBitsy firmware must be loaded with a square-pulse build for this
measurement so the DAC rising edges are threshold-detectable.

Usage:
    python analysis_click_timing.py --csv capture.csv --trial-id T123
    python analysis_click_timing.py --csv capture.csv --trial-id T123 \\
        --thr-led 1.5 --thr-ttl 1.5 --thr-dac 0.5
    python analysis_click_timing.py --csv capture.csv --trial-id T123 \\
        --save timing_fig.png --out-csv click_errors.csv
"""

import argparse
import csv as csv_mod
import os
import sys

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from ui.click_generator import generate_clicks

logger = None   # no logger needed — standalone analysis script

_MATCH_TOLERANCE_S = 0.010   # 10 ms window for pairing TTL edge to scheduled time
_MCU_WINDOW_S      = 0.005   # 5 ms window for pairing DAC edge to TTL edge


# ── CSV loading ───────────────────────────────────────────────────────────────

def load_oscilloscope_csv(path: str, col_led: str, col_ttl: str, col_dac: str
                          ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Parse a Tektronix (or similar) oscilloscope CSV export.

    Skips arbitrary metadata rows at the top of the file; the header row is
    the first row whose leading field matches a time-column label ('TIME',
    'X', 'T', 'time', etc.).

    Returns (t, led, ttl, dac) as float64 arrays in seconds / volts.
    """
    time_labels = {"time", "x", "t"}

    with open(path, newline="", encoding="utf-8-sig") as f:
        lines = f.readlines()

    header_idx = None
    header: list[str] = []
    for i, line in enumerate(lines):
        fields = [field.strip() for field in line.split(",")]
        if fields and fields[0].lower() in time_labels:
            header_idx = i
            header = [field.upper() for field in fields]
            break

    if header_idx is None:
        raise ValueError(
            f"No time-column header found in {path}. "
            f"Expected a row whose first field is one of: {time_labels}"
        )

    data_rows = []
    for line in lines[header_idx + 1:]:
        fields = [field.strip() for field in line.split(",")]
        if not fields or not fields[0]:
            continue
        try:
            data_rows.append([float(v) for v in fields[:len(header)]])
        except ValueError:
            continue

    if not data_rows:
        raise ValueError(f"No numeric data rows found after header in {path}")

    data = np.array(data_rows, dtype=np.float64)

    def _col(name: str) -> np.ndarray:
        key = name.upper()
        if key not in header:
            raise ValueError(f"Column '{name}' not found in CSV. Available: {header}")
        return data[:, header.index(key)]

    return _col(header[0]), _col(col_led), _col(col_ttl), _col(col_dac)


# ── Edge detection ────────────────────────────────────────────────────────────

def rising_edges(t: np.ndarray, v: np.ndarray, threshold: float,
                 refractory_s: float = 0.001) -> np.ndarray:
    """
    Return timestamps of rising-edge threshold crossings, sub-sample interpolated.

    refractory_s suppresses re-detection of the same edge due to ringing.
    """
    above = v >= threshold
    crossings = np.where(~above[:-1] & above[1:])[0] + 1

    if len(crossings) == 0:
        return np.array([], dtype=np.float64)

    times = []
    for idx in crossings:
        t0, t1 = t[idx - 1], t[idx]
        v0, v1 = v[idx - 1], v[idx]
        frac = (threshold - v0) / (v1 - v0) if v1 != v0 else 0.0
        times.append(t0 + frac * (t1 - t0))

    times = np.array(times)

    kept = [times[0]]
    for t_edge in times[1:]:
        if t_edge - kept[-1] >= refractory_s:
            kept.append(t_edge)
    return np.array(kept)


# ── PostgreSQL ────────────────────────────────────────────────────────────────

def load_scheduled_clicks(trial_id: str) -> tuple[list[float], list[float]]:
    """
    Recover scheduled click times for a trial from PostgreSQL by regenerating
    them from the stored click_seed and task_config, exactly as the live system did.

    Returns (left_clicks, right_clicks) — float seconds relative to trial start.
    """
    conn = psycopg2.connect(config.POSTGRES_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT tr.click_seed, tr.correct_side, ts.task_config
                FROM   trial_results    tr
                JOIN   training_substages ts ON ts.id = tr.substage_id
                WHERE  tr.trial_id = %s
            """, (trial_id,))
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise SystemExit(f"Trial '{trial_id}' not found in database.")

    seed, correct_side, task_config = row
    if seed is None:
        raise SystemExit(f"Trial '{trial_id}' has no click_seed — cannot recover scheduled times.")

    base_left, base_right, duration = 0.0, 0.0, 1.0
    for state in task_config.get("states", []):
        for phase in ("entry_actions", "exit_actions"):
            for action in state.get(phase, []):
                if action.get("type") == "play_clicks":
                    base_left  = action.get("left_rate",      0) or 0.0
                    base_right = action.get("right_rate",     0) or 0.0
                    duration   = action.get("click_duration", 1.0) or 1.0

    high_rate = max(base_left, base_right)
    low_rate  = min(base_left, base_right)
    l_rate = high_rate if correct_side == "left" else low_rate
    r_rate = low_rate  if correct_side == "left" else high_rate

    clicks = generate_clicks(l_rate, r_rate, duration, seed=seed)
    return clicks["left_clicks"], clicks["right_clicks"]


# ── Matching ──────────────────────────────────────────────────────────────────

def match_edges(ttl_edges: np.ndarray, scheduled: np.ndarray,
                dac_edges: np.ndarray, match_tol_s: float,
                mcu_window_s: float) -> tuple[np.ndarray, np.ndarray, np.ndarray,
                                              np.ndarray, np.ndarray]:
    """
    Build consistent per-click triples (scheduled_t, ttl_t, dac_t).

    Step 1: pair each scheduled time to the nearest TTL edge within match_tol_s.
    Step 2: for each paired TTL edge, find the first DAC edge within mcu_window_s.

    Returns (sched_matched, ttl_matched, dac_matched, pi_errors, mcu_latency)
    where pi_errors = ttl - sched and mcu_latency = dac - ttl.
    All four arrays have the same length (only fully matched triples are kept).
    """
    ttl_sorted = np.sort(ttl_edges)
    dac_sorted = np.sort(dac_edges)

    sched_out, ttl_out, dac_out = [], [], []
    used_ttl = set()

    for sched_t in sorted(scheduled):
        diffs = np.abs(ttl_sorted - sched_t)
        best = int(np.argmin(diffs))
        if diffs[best] > match_tol_s or best in used_ttl:
            continue
        ttl_t = ttl_sorted[best]
        used_ttl.add(best)

        # Find first unused DAC edge after this TTL edge
        idx = int(np.searchsorted(dac_sorted, ttl_t))
        if idx >= len(dac_sorted) or dac_sorted[idx] - ttl_t > mcu_window_s:
            continue

        sched_out.append(sched_t)
        ttl_out.append(ttl_t)
        dac_out.append(dac_sorted[idx])

    sched_arr = np.array(sched_out)
    ttl_arr   = np.array(ttl_out)
    dac_arr   = np.array(dac_out)

    pi_errors   = ttl_arr - sched_arr
    mcu_latency = dac_arr - ttl_arr
    return sched_arr, ttl_arr, dac_arr, pi_errors, mcu_latency


# ── Stats helpers ─────────────────────────────────────────────────────────────

def _stats_us(arr_s: np.ndarray) -> dict:
    arr = arr_s * 1e6
    return {
        "n":      len(arr),
        "median": float(np.median(arr)),
        "p25":    float(np.percentile(arr, 25)),
        "p75":    float(np.percentile(arr, 75)),
        "p99":    float(np.percentile(arr, 99)),
        "max":    float(np.max(arr)),
    }


# ── Plot ──────────────────────────────────────────────────────────────────────

def plot(t: np.ndarray, ttl_raw: np.ndarray, dac_raw: np.ndarray,
         sched: np.ndarray, ttl_matched: np.ndarray, dac_matched: np.ndarray,
         pi_errors: np.ndarray, mcu_latency: np.ndarray,
         save_path: str | None = None) -> None:

    e2e = pi_errors + mcu_latency

    fig = plt.figure(figsize=(14, 8))
    gs  = gridspec.GridSpec(2, 3, figure=fig, height_ratios=[1.2, 1], hspace=0.45, wspace=0.35)

    # ── Top panel: oscilloscope trace (first 300 ms after t=0 or full duration) ──
    ax_trace = fig.add_subplot(gs[0, :])
    t_end = min(t[-1], 0.30)
    mask  = (t >= 0) & (t <= t_end)
    ax_trace.plot(t[mask] * 1e3, ttl_raw[mask], color="steelblue", linewidth=0.8,
                  label="TTL (Pi trigger)")
    ax_trace.plot(t[mask] * 1e3, dac_raw[mask] * 0.8 - 0.5, color="darkorange",
                  linewidth=0.8, label="DAC (ItsyBitsy, scaled)")
    for s in sched[sched <= t_end]:
        ax_trace.axvline(s * 1e3, color="gray", linewidth=0.7, linestyle="--", alpha=0.7)
    for tm in ttl_matched[ttl_matched <= t_end]:
        ax_trace.axvline(tm * 1e3, color="steelblue", linewidth=0.5, alpha=0.4)
    for dm in dac_matched[dac_matched <= t_end]:
        ax_trace.axvline(dm * 1e3, color="darkorange", linewidth=0.5, alpha=0.4)
    ax_trace.set_xlabel("Time relative to LED rising edge (ms)")
    ax_trace.set_ylabel("Voltage (V)")
    ax_trace.set_title("Oscilloscope trace — dashed lines: scheduled, solid: detected edges")
    ax_trace.legend(fontsize=8, loc="upper right")

    # ── Bottom panels: three error histograms ────────────────────────────────
    hist_data = [
        (pi_errors,   "Pi-side scheduling error\n(TTL − scheduled)",   "steelblue"),
        (mcu_latency, "MCU onset latency\n(DAC − TTL)",                 "darkorange"),
        (e2e,         "End-to-end error\n(DAC − scheduled)",            "seagreen"),
    ]

    for col, (arr_s, title, color) in enumerate(hist_data):
        ax = fig.add_subplot(gs[1, col])
        s  = _stats_us(arr_s)
        arr_us = arr_s * 1e6

        ax.hist(arr_us, bins=40, color=color, edgecolor="white", linewidth=0.4, alpha=0.85)
        ax.axvline(s["median"], color="black",  linewidth=1.5,
                   label=f"Median {s['median']:.1f} µs")
        ax.axvline(s["p25"],    color="black",  linewidth=1.0, linestyle="--")
        ax.axvline(s["p75"],    color="black",  linewidth=1.0, linestyle="--",
                   label=f"IQR {s['p75'] - s['p25']:.1f} µs")
        ax.set_xlabel("Error (µs)")
        ax.set_ylabel("Count")
        ax.set_title(title, fontsize=10)
        ax.legend(fontsize=8)

        # Annotate p99 and max as text
        ax.text(0.97, 0.97, f"p99 = {s['p99']:.1f} µs\nmax = {s['max']:.1f} µs\nn = {s['n']}",
                transform=ax.transAxes, ha="right", va="top", fontsize=7,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.7))

    fig.suptitle("Click timing validation — ItsyBitsy TTL path", fontweight="bold")

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved → {save_path}")
    else:
        plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="Click timing validation — oscilloscope CSV analysis"
    )
    p.add_argument("--csv",      required=True,
                   help="Oscilloscope CSV export path")
    p.add_argument("--trial-id", required=True,
                   help="trial_id to fetch scheduled clicks from PostgreSQL")
    p.add_argument("--col-led",  default="CH1",
                   help="CSV column for LED GPIO channel (default: CH1)")
    p.add_argument("--col-ttl",  default="CH2",
                   help="CSV column for Pi TTL line (default: CH2)")
    p.add_argument("--col-dac",  default="CH3",
                   help="CSV column for ItsyBitsy DAC output (default: CH3)")
    p.add_argument("--thr-led",  type=float, default=1.5,
                   help="LED threshold voltage (default: 1.5 V)")
    p.add_argument("--thr-ttl",  type=float, default=1.5,
                   help="TTL threshold voltage (default: 1.5 V)")
    p.add_argument("--thr-dac",  type=float, default=None,
                   help="DAC threshold voltage (default: midpoint of DAC signal range)")
    p.add_argument("--refractory-ttl", type=float, default=0.0005,
                   help="TTL refractory period in seconds (default: 0.5 ms)")
    p.add_argument("--refractory-dac", type=float, default=0.004,
                   help="DAC refractory period in seconds (default: 4 ms)")
    p.add_argument("--save",     default=None,
                   help="Save plot to this path instead of displaying")
    p.add_argument("--out-csv",  default=None,
                   help="Save per-click error table to this CSV path")
    args = p.parse_args()

    # Load waveforms
    print(f"Loading {args.csv} ...")
    t, led, ttl_raw, dac_raw = load_oscilloscope_csv(
        args.csv, args.col_led, args.col_ttl, args.col_dac
    )
    dt_us = float(np.median(np.diff(t))) * 1e6
    print(f"  {len(t):,} samples  dt={dt_us:.2f} µs  duration={t[-1]-t[0]:.3f} s")

    thr_dac = args.thr_dac if args.thr_dac is not None else float((dac_raw.min() + dac_raw.max()) / 2)
    print(f"  Thresholds — LED: {args.thr_led} V  TTL: {args.thr_ttl} V  DAC: {thr_dac:.3f} V")

    # Detect t=0 from first LED rising edge
    led_edges = rising_edges(t, led, args.thr_led, refractory_s=0.001)
    if len(led_edges) == 0:
        sys.exit("ERROR: no LED rising edge found — check --thr-led and --col-led.")
    t0 = float(led_edges[0])
    print(f"  LED rising edge (t=0) at {t0:.6f} s absolute")

    # Shift time axis so t=0 = LED edge, then detect TTL and DAC edges
    t_rel     = t - t0
    ttl_edges = rising_edges(t_rel, ttl_raw, args.thr_ttl, refractory_s=args.refractory_ttl)
    dac_edges = rising_edges(t_rel, dac_raw, thr_dac,      refractory_s=args.refractory_dac)

    # Drop any edges that arrived before state entry (shouldn't happen but be safe)
    ttl_edges = ttl_edges[ttl_edges > -0.001]
    dac_edges = dac_edges[dac_edges > -0.001]
    print(f"  TTL edges detected: {len(ttl_edges)}   DAC edges detected: {len(dac_edges)}")

    # Recover scheduled click times from PostgreSQL
    print(f"Fetching trial '{args.trial_id}' from PostgreSQL ...")
    left_clicks, right_clicks = load_scheduled_clicks(args.trial_id)
    scheduled = np.array(sorted(left_clicks + right_clicks))
    print(f"  Scheduled clicks: {len(scheduled)}  ({len(left_clicks)} L + {len(right_clicks)} R)")

    # Build matched triples and compute errors
    sched_matched, ttl_matched, dac_matched, pi_errors, mcu_latency = match_edges(
        ttl_edges, scheduled, dac_edges, _MATCH_TOLERANCE_S, _MCU_WINDOW_S
    )
    e2e_errors = pi_errors + mcu_latency
    n_matched  = len(pi_errors)
    print(f"  Fully matched triples: {n_matched} / {len(scheduled)}")

    if n_matched == 0:
        sys.exit("ERROR: no clicks matched — check thresholds and column assignments.")

    # Print summary
    print("\n── Results ──────────────────────────────────────────────────────────────")
    for label, arr_s in [
        ("Pi-side scheduling error  (TTL − scheduled)", pi_errors),
        ("MCU onset latency         (DAC − TTL)       ", mcu_latency),
        ("End-to-end error          (DAC − scheduled) ", e2e_errors),
    ]:
        s = _stats_us(arr_s)
        print(f"  {label}")
        print(f"    n={s['n']}  median={s['median']:+.1f} µs  "
              f"IQR={s['p75']-s['p25']:.1f} µs  "
              f"p99={s['p99']:+.1f} µs  max={s['max']:+.1f} µs")

    # Optional per-click CSV output
    if args.out_csv:
        with open(args.out_csv, "w", newline="") as f:
            writer = csv_mod.DictWriter(f, fieldnames=[
                "click_idx", "scheduled_s", "ttl_s", "dac_s",
                "pi_error_us", "mcu_latency_us", "e2e_error_us",
            ])
            writer.writeheader()
            for i in range(n_matched):
                writer.writerow({
                    "click_idx":      i,
                    "scheduled_s":    round(float(sched_matched[i]), 6),
                    "ttl_s":          round(float(ttl_matched[i]),   6),
                    "dac_s":          round(float(dac_matched[i]),   6),
                    "pi_error_us":    round(float(pi_errors[i])   * 1e6, 2),
                    "mcu_latency_us": round(float(mcu_latency[i]) * 1e6, 2),
                    "e2e_error_us":   round(float(e2e_errors[i])  * 1e6, 2),
                })
        print(f"\nSaved per-click table → {args.out_csv}")

    # Plot
    plot(t_rel, ttl_raw, dac_raw, sched_matched, ttl_matched, dac_matched,
         pi_errors, mcu_latency, save_path=args.save)


if __name__ == "__main__":
    main()
