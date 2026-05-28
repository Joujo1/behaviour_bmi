#!/usr/bin/env python3
"""
Click timing validation — oscilloscope CSV analysis + database analysis.

Measurement modes (--mode):

  ttl-dac  (Step 1 — 2 oscilloscope probes)
      Channels: Pi TTL trigger line + ItsyBitsy DAC output.
      Measures the MCU onset latency: time from TTL rising edge to DAC
      rising edge.  No PostgreSQL or LED channel needed.  Use the
      SQUARE_PULSE_VALIDATION firmware build so DAC edges are cleanly
      threshold-detectable.

  pi-sched  (Step 2 — no oscilloscope needed)
      Reads click_fire_log events from PostgreSQL (logged by actions.py).
      Measures the Pi-side scheduling error: actual TTL fire time vs.
      scheduled time, measured in software via CLOCK_MONOTONIC.
      Use --session-id or --n-recent to select which trials to include.

  led-ttl  (Step 2 — 2 probes, oscilloscope-based alternative)
      Channels: Pi LED GPIO output + Pi TTL trigger line.
      The LED rising edge defines t = 0 (state entry).  Measures the
      Pi-side scheduling error: TTL rising edge vs. scheduled click
      times recovered from PostgreSQL.  --trial-id is required.

  full  (3 probes — combines both steps in one capture)
      Channels: LED GPIO / Pi TTL / ItsyBitsy DAC.
      Computes all three distributions: Pi-side scheduling error,
      MCU onset latency, end-to-end error.  --trial-id is required.

Usage:
    # Step 1 — MCU onset latency (oscilloscope)
    python analysis_click_timing.py --mode ttl-dac --csv capture1.csv

    # Step 2 — Pi scheduling error (database, no oscilloscope)
    python analysis_click_timing.py --mode pi-sched --n-recent 500

    # Step 2 — Pi scheduling error (oscilloscope-based)
    python analysis_click_timing.py --mode led-ttl --csv capture2.csv --trial-id T123

    # Full 3-channel
    python analysis_click_timing.py --mode full --csv capture.csv --trial-id T123
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

_MATCH_TOLERANCE_S = 0.010   # 10 ms window for pairing TTL edge to scheduled time
_MCU_WINDOW_S      = 0.005   # 5 ms window for pairing DAC edge to TTL edge


# ── CSV loading ───────────────────────────────────────────────────────────────

def load_oscilloscope_csv(path: str, *col_names: str
                          ) -> tuple[np.ndarray, ...]:
    """
    Parse a Tektronix (or similar) oscilloscope CSV export.

    Skips arbitrary metadata rows; the header row is the first row whose
    leading field matches a time-column label ('TIME', 'X', 'T', ...).

    Returns (t, ch1, ch2, ...) as float64 arrays for each requested column.
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

    t = _col(header[0])
    return (t,) + tuple(_col(c) for c in col_names)


# ── Edge detection ────────────────────────────────────────────────────────────

def rising_edges(t: np.ndarray, v: np.ndarray, threshold: float,
                 refractory_s: float = 0.001) -> np.ndarray:
    """Return sub-sample interpolated timestamps of rising-edge crossings."""
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
    Recover scheduled click times from PostgreSQL by regenerating them from
    the stored click_seed and task_config.

    Returns (left_clicks, right_clicks) in seconds relative to trial start.
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

def match_ttl_to_dac(ttl_edges: np.ndarray, dac_edges: np.ndarray,
                     mcu_window_s: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Pair TTL[i] with DAC[i] by index.  Keeps only pairs where the DAC edge
    falls within mcu_window_s of the TTL edge (positive or negative).
    Simple and reliable for small N where edge counts should match 1-to-1.
    """
    n = min(len(ttl_edges), len(dac_edges))
    ttl_s = np.sort(ttl_edges)[:n]
    dac_s = np.sort(dac_edges)[:n]
    diff  = dac_s - ttl_s
    mask  = np.abs(diff) <= mcu_window_s
    return ttl_s[mask], dac_s[mask], diff[mask]


def match_ttl_to_scheduled(ttl_edges: np.ndarray, scheduled: np.ndarray,
                            match_tol_s: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Strict 1-to-1 sequential match.

    Both arrays are sorted.  A single TTL pointer advances; for each scheduled
    time we find the nearest not-yet-consumed TTL edge and accept it if within
    match_tol_s.  Each TTL edge is consumed exactly once.
    """
    ttl_sorted  = np.sort(ttl_edges)
    sched_sorted = np.sort(scheduled)
    sched_out, ttl_out = [], []
    j = 0

    for sched_t in sched_sorted:
        # advance past TTL edges that are clearly too early
        while j < len(ttl_sorted) - 1 and ttl_sorted[j] < sched_t - match_tol_s:
            j += 1
        if j >= len(ttl_sorted):
            break
        if abs(ttl_sorted[j] - sched_t) <= match_tol_s:
            sched_out.append(sched_t)
            ttl_out.append(ttl_sorted[j])
            j += 1

    sched_arr = np.array(sched_out)
    ttl_arr   = np.array(ttl_out)
    return sched_arr, ttl_arr, ttl_arr - sched_arr


# ── Stats ─────────────────────────────────────────────────────────────────────

def _stats_us(arr_s: np.ndarray) -> dict:
    arr = arr_s * 1e6
    counts, edges = np.histogram(arr, bins=40)
    mode = float(edges[int(np.argmax(counts))] + (edges[1] - edges[0]) / 2)
    return {
        "n":      len(arr),
        "mean":   float(np.mean(arr)),
        "median": float(np.median(arr)),
        "mode":   mode,
        "p95":    float(np.percentile(arr, 95)),
        "p99":    float(np.percentile(arr, 99)),
        "max":    float(np.max(arr)),
    }


def _print_stats(label: str, arr_s: np.ndarray) -> None:
    s = _stats_us(arr_s)
    print(f"  {label}")
    print(f"    n={s['n']}  median={s['median']:+.1f} µs  "
          f"p95={s['p95']:+.1f} µs  "
          f"p99={s['p99']:+.1f} µs  max={s['max']:+.1f} µs")


# ── Plots ─────────────────────────────────────────────────────────────────────

def _hist_panel(ax, arr_s: np.ndarray, title: str, color: str) -> None:
    s = _stats_us(arr_s)
    arr_us = arr_s * 1e6
    ax.hist(arr_us, bins=40, color=color, edgecolor="white", linewidth=0.4, alpha=0.85)
    ax.axvline(s["median"], color="black",  linewidth=1.5, linestyle="-",
               label=f"Median {s['median']:.1f} µs")
    ax.axvline(s["p95"],    color="tab:red",    linewidth=1.2, linestyle="--",
               label=f"p95 {s['p95']:.1f} µs")
    ax.axvline(s["p99"],    color="tab:purple", linewidth=1.2, linestyle=":",
               label=f"p99 {s['p99']:.1f} µs")
    ax.set_xlabel("Error (µs)")
    ax.set_ylabel("Count")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8)
    ax.text(0.97, 0.97,
            f"max = {s['max']:.1f} µs\nn = {s['n']}",
            transform=ax.transAxes, ha="right", va="top", fontsize=7,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.7))


def load_pi_sched_errors(session_id: int | None = None,
                          n_recent: int = 200,
                          verify: bool = False) -> np.ndarray:
    """
    Extract Pi-side scheduling errors from click_fire_log events in PostgreSQL.

    Errors are recomputed independently from raw timestamps:
        fired_mono − (t0_mono + scheduled_s)
    rather than trusting the pre-computed sched_error_us field.

    If verify=True, prints a side-by-side comparison of stored vs recomputed
    values so you can confirm the Pi's arithmetic is correct.

    Returns errors in seconds (to match the convention of other error arrays).
    """
    conn = psycopg2.connect(config.POSTGRES_DSN)
    try:
        with conn.cursor() as cur:
            if session_id is not None:
                cur.execute("""
                    SELECT events FROM trial_results
                    WHERE  session_id = %s
                    ORDER  BY completed_at DESC
                """, (session_id,))
            else:
                cur.execute("""
                    SELECT events FROM trial_results
                    ORDER  BY completed_at DESC
                    LIMIT  %s
                """, (n_recent,))
            rows = cur.fetchall()
    finally:
        conn.close()

    recomputed_us = []
    stored_us     = []

    for (events,) in rows:
        if not events:
            continue
        for ev in events:
            if ev.get("output") == "click_fire_log":
                for rec in (ev.get("active") or []):
                    t0      = rec.get("t0_mono")
                    fired   = rec.get("fired_mono")
                    sched_s = rec.get("scheduled_s")
                    stored  = rec.get("sched_error_us")
                    if t0 is not None and fired is not None and sched_s is not None:
                        recomputed_us.append((fired - (t0 + sched_s)) * 1e6)
                        if stored is not None:
                            stored_us.append(float(stored))

    if not recomputed_us:
        raise SystemExit(
            "No click_fire_log events found in PostgreSQL.\n"
            "Ensure the Pi service is running the updated actions.py "
            "(restart with: sudo systemctl restart bmi-pi)."
        )

    if verify and stored_us:
        r = np.array(recomputed_us)
        s = np.array(stored_us[:len(r)])
        offsets = r - s
        print(f"\n── Stored vs recomputed comparison ({len(r)} records) ────────────────")
        print(f"  {'click':>5}  {'stored µs':>12}  {'recomputed µs':>14}  {'diff µs':>10}")
        print(f"  {'-'*5}  {'-'*12}  {'-'*14}  {'-'*10}")
        for i in range(min(15, len(r))):
            print(f"  {i:>5}  {s[i]:>12.3f}  {r[i]:>14.3f}  {offsets[i]:>+10.4f}")
        if len(r) > 15:
            print(f"  ... ({len(r) - 15} more rows)")
        print(f"\n  Mean offset  : {offsets.mean():+.4f} µs")
        print(f"  Std of offset: {offsets.std():.4f} µs  (should be ~0 if rounding is correct)")
        print(f"  Max |offset| : {np.abs(offsets).max():.4f} µs")
        print()

    return np.array(recomputed_us, dtype=np.float64) * 1e-6   # → seconds


def plot_pi_sched(errors_s: np.ndarray, save_path: str | None = None) -> None:
    s = _stats_us(errors_s)
    fig, ax = plt.subplots(figsize=(8, 5))
    errors_us = errors_s * 1e6
    ax.hist(errors_us, bins=40, color="steelblue",
            edgecolor="white", linewidth=0.4, alpha=0.85)
    ax.axvline(s["mean"],   color="tab:orange", linewidth=1.2, linestyle="-",
               label=f"Mean {s['mean']:.1f} µs")
    ax.axvline(s["median"], color="black",      linewidth=1.5, linestyle="-",
               label=f"Median {s['median']:.1f} µs")
    ax.axvline(s["p95"],    color="tab:red",    linewidth=1.2, linestyle="--",
               label=f"p95 {s['p95']:.1f} µs")
    ax.axvline(s["p99"],    color="tab:purple", linewidth=1.2, linestyle=":",
               label=f"p99 {s['p99']:.1f} µs")
    ax.set_xlabel("Scheduling error (µs)")
    ax.set_ylabel("Count")
    ax.set_title("Pi-side click scheduling error", fontsize=10)
    ax.legend(fontsize=9)
    ax.text(0.97, 0.97,
            f"max = {s['max']:.1f} µs\nn = {s['n']}",
            transform=ax.transAxes, ha="right", va="top", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.7))
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved → {save_path}")
    else:
        plt.show()


def plot_ttl_dac(t: np.ndarray, ttl_raw: np.ndarray, dac_raw: np.ndarray,
                 ttl_matched: np.ndarray, dac_matched: np.ndarray,
                 mcu_latency: np.ndarray, save_path: str | None = None) -> None:
    fig = plt.figure(figsize=(12, 7))
    gs  = gridspec.GridSpec(2, 1, figure=fig, height_ratios=[1.2, 1], hspace=0.45)

    ax_trace = fig.add_subplot(gs[0])
    t_end = min(t[-1], 0.30)
    mask  = (t >= 0) & (t <= t_end)
    ax_trace.plot(t[mask] * 1e3, ttl_raw[mask], color="steelblue",
                  linewidth=0.8, label="TTL (Pi trigger)")
    ax_trace.plot(t[mask] * 1e3, dac_raw[mask], color="darkorange",
                  linewidth=0.8, label="DAC (ItsyBitsy)")
    for tm in ttl_matched[ttl_matched <= t_end]:
        ax_trace.axvline(tm * 1e3, color="steelblue", linewidth=0.6, alpha=0.5)
    for dm in dac_matched[dac_matched <= t_end]:
        ax_trace.axvline(dm * 1e3, color="darkorange", linewidth=0.6, alpha=0.5)
    ax_trace.set_xlabel("Time (ms)")
    ax_trace.set_ylabel("Voltage (V)")
    ax_trace.set_title("Step 1 — TTL trigger vs DAC output (vertical lines: detected edges)")
    ax_trace.legend(fontsize=8, loc="upper right")

    ax_hist = fig.add_subplot(gs[1])
    _hist_panel(ax_hist, mcu_latency, "MCU onset latency (DAC rising edge − TTL rising edge)",
                "darkorange")

    fig.suptitle("Click timing — Step 1: MCU onset latency", fontweight="bold")
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved → {save_path}")
    else:
        plt.show()


def plot_led_ttl(t: np.ndarray, led_raw: np.ndarray, ttl_raw: np.ndarray,
                 sched_matched: np.ndarray, ttl_matched: np.ndarray,
                 pi_errors: np.ndarray, save_path: str | None = None) -> None:
    fig = plt.figure(figsize=(12, 7))
    gs  = gridspec.GridSpec(2, 1, figure=fig, height_ratios=[1.2, 1], hspace=0.45)

    ax_trace = fig.add_subplot(gs[0])
    t_end = min(t[-1], 0.30)
    mask  = (t >= 0) & (t <= t_end)
    ax_trace.plot(t[mask] * 1e3, led_raw[mask], color="seagreen",
                  linewidth=0.8, label="LED GPIO (Pi)")
    ax_trace.plot(t[mask] * 1e3, ttl_raw[mask] * 0.8 - 0.3, color="steelblue",
                  linewidth=0.8, label="TTL (Pi trigger, scaled)")
    for s in sched_matched[sched_matched <= t_end]:
        ax_trace.axvline(s * 1e3, color="gray", linewidth=0.7, linestyle="--", alpha=0.7)
    for tm in ttl_matched[ttl_matched <= t_end]:
        ax_trace.axvline(tm * 1e3, color="steelblue", linewidth=0.5, alpha=0.4)
    ax_trace.set_xlabel("Time relative to LED rising edge (ms)")
    ax_trace.set_ylabel("Voltage (V)")
    ax_trace.set_title("Step 2 — LED t=0 reference, TTL pulses vs scheduled times (dashed)")
    ax_trace.legend(fontsize=8, loc="upper right")

    ax_hist = fig.add_subplot(gs[1])
    _hist_panel(ax_hist, pi_errors, "Pi-side scheduling error (TTL rising edge − scheduled time)",
                "steelblue")

    fig.suptitle("Click timing — Step 2: Pi-side scheduling error", fontweight="bold")
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved → {save_path}")
    else:
        plt.show()


def plot_full(t: np.ndarray, ttl_raw: np.ndarray, dac_raw: np.ndarray,
              sched: np.ndarray, ttl_matched: np.ndarray, dac_matched: np.ndarray,
              pi_errors: np.ndarray, mcu_latency: np.ndarray,
              save_path: str | None = None) -> None:
    e2e = pi_errors + mcu_latency
    fig = plt.figure(figsize=(14, 8))
    gs  = gridspec.GridSpec(2, 3, figure=fig, height_ratios=[1.2, 1], hspace=0.45, wspace=0.35)

    ax_trace = fig.add_subplot(gs[0, :])
    t_end = min(t[-1], 0.30)
    mask  = (t >= 0) & (t <= t_end)
    ax_trace.plot(t[mask] * 1e3, ttl_raw[mask], color="steelblue",
                  linewidth=0.8, label="TTL (Pi trigger)")
    ax_trace.plot(t[mask] * 1e3, dac_raw[mask] * 0.8 - 0.5, color="darkorange",
                  linewidth=0.8, label="DAC (ItsyBitsy, scaled)")
    for s in sched[sched <= t_end]:
        ax_trace.axvline(s * 1e3, color="gray", linewidth=0.7, linestyle="--", alpha=0.7)
    ax_trace.set_xlabel("Time relative to LED rising edge (ms)")
    ax_trace.set_ylabel("Voltage (V)")
    ax_trace.set_title("Oscilloscope trace — dashed: scheduled, verticals: detected edges")
    ax_trace.legend(fontsize=8, loc="upper right")

    for col, (arr_s, title, color) in enumerate([
        (pi_errors,   "Pi-side scheduling error\n(TTL − scheduled)",  "steelblue"),
        (mcu_latency, "MCU onset latency\n(DAC − TTL)",                "darkorange"),
        (e2e,         "End-to-end error\n(DAC − scheduled)",           "seagreen"),
    ]):
        _hist_panel(fig.add_subplot(gs[1, col]), arr_s, title, color)

    fig.suptitle("Click timing validation — full 3-channel", fontweight="bold")
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved → {save_path}")
    else:
        plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="Click timing validation — oscilloscope CSV + database analysis"
    )
    p.add_argument("--mode", required=True,
                   choices=["ttl-dac", "pi-sched", "led-ttl", "full"],
                   help="ttl-dac: step 1 MCU latency (2 probes); "
                        "pi-sched: step 2 Pi scheduling (database, no oscilloscope); "
                        "led-ttl: step 2 Pi scheduling (2 probes); "
                        "full: all 3 metrics (3 probes)")
    p.add_argument("--csv",        default=None,  help="Oscilloscope CSV export path")
    p.add_argument("--trial-id",   default=None,
                   help="trial_id for PostgreSQL lookup (required for led-ttl and full)")
    p.add_argument("--session-id", type=int, default=None,
                   help="Restrict pi-sched to a specific session_id")
    p.add_argument("--n-recent",   type=int, default=500,
                   help="Number of most-recent trials to include in pi-sched (default: 500)")
    p.add_argument("--col-led",    default="CH1",  help="CSV column for LED GPIO (default: CH1)")
    p.add_argument("--col-ttl",    default="CH2",  help="CSV column for Pi TTL (default: CH2)")
    p.add_argument("--col-dac",    default="CH3",  help="CSV column for DAC output (default: CH3)")
    p.add_argument("--thr-led",    type=float, default=1.5,  help="LED threshold V (default: 1.5)")
    p.add_argument("--thr-ttl",    type=float, default=1.5,  help="TTL threshold V (default: 1.5)")
    p.add_argument("--thr-dac",    type=float, default=None,
                   help="DAC threshold V (default: midpoint of DAC range)")
    p.add_argument("--refractory-ttl", type=float, default=0.0005,
                   help="TTL refractory period s (default: 0.5 ms)")
    p.add_argument("--refractory-dac", type=float, default=0.004,
                   help="DAC refractory period s (default: 4 ms)")
    p.add_argument("--verify",  action="store_true",
                   help="(pi-sched only) Print stored vs recomputed sched_error_us comparison")
    p.add_argument("--save",    default=None, help="Save plot to file instead of displaying")
    p.add_argument("--out-csv", default=None, help="Save per-click table to CSV")
    args = p.parse_args()

    if args.mode in ("ttl-dac", "led-ttl", "full") and args.csv is None:
        p.error(f"--csv is required for --mode {args.mode}")
    if args.mode in ("led-ttl", "full") and args.trial_id is None:
        p.error(f"--trial-id is required for --mode {args.mode}")

    # ── pi-sched mode — purely database, no oscilloscope ─────────────────────
    if args.mode == "pi-sched":
        print(f"Querying PostgreSQL for click_fire_log events ...")
        if args.session_id is not None:
            print(f"  Filter: session_id = {args.session_id}")
        else:
            print(f"  Filter: {args.n_recent} most recent trials")

        errors_s = load_pi_sched_errors(session_id=args.session_id,
                                         n_recent=args.n_recent,
                                         verify=args.verify)
        s = _stats_us(errors_s)
        print(f"  click_fire_log records: {s['n']}")
        _print_stats("Pi-side scheduling error  (fired_mono − scheduled_mono)", errors_s)

        if args.out_csv:
            with open(args.out_csv, "w", newline="") as f:
                w = csv_mod.DictWriter(f, fieldnames=["click_idx", "sched_error_us"])
                w.writeheader()
                for i, e in enumerate(errors_s * 1e6):
                    w.writerow({"click_idx": i, "sched_error_us": round(float(e), 3)})
            print(f"Saved per-click table → {args.out_csv}")

        plot_pi_sched(errors_s, save_path=args.save)
        return

    # ── Load waveforms ────────────────────────────────────────────────────────
    print(f"Loading {args.csv}  [mode={args.mode}] ...")

    if args.mode == "ttl-dac":
        t, ttl_raw, dac_raw = load_oscilloscope_csv(args.csv, args.col_ttl, args.col_dac)
        led_raw = None
    elif args.mode == "led-ttl":
        t, led_raw, ttl_raw = load_oscilloscope_csv(args.csv, args.col_led, args.col_ttl)
        dac_raw = None
    else:  # full
        t, led_raw, ttl_raw, dac_raw = load_oscilloscope_csv(
            args.csv, args.col_led, args.col_ttl, args.col_dac)

    dt_us = float(np.median(np.diff(t))) * 1e6
    print(f"  {len(t):,} samples  dt={dt_us:.2f} µs  duration={t[-1]-t[0]:.3f} s")

    # ── t = 0 reference ───────────────────────────────────────────────────────
    if args.mode == "ttl-dac":
        # No LED — use first TTL edge as t=0 reference for the trace plot
        ttl_edges_abs = rising_edges(t, ttl_raw, args.thr_ttl,
                                     refractory_s=args.refractory_ttl)
        if len(ttl_edges_abs) == 0:
            sys.exit("ERROR: no TTL rising edges found — check --thr-ttl and --col-ttl.")
        t0 = float(ttl_edges_abs[0])
    else:
        led_edges = rising_edges(t, led_raw, args.thr_led, refractory_s=0.001)
        if len(led_edges) == 0:
            sys.exit("ERROR: no LED rising edge found — check --thr-led and --col-led.")
        t0 = float(led_edges[0])
        print(f"  LED rising edge (t=0) at {t0:.6f} s absolute")

    t_rel    = t - t0
    ttl_edges = rising_edges(t_rel, ttl_raw, args.thr_ttl,
                              refractory_s=args.refractory_ttl)
    ttl_edges = ttl_edges[ttl_edges > -0.001]
    print(f"  TTL edges detected: {len(ttl_edges)}")

    if dac_raw is not None:
        if args.thr_dac is not None:
            thr_dac = args.thr_dac
        else:
            # Use midpoint between idle level (mode) and peak, not global min/max,
            # so a startup transient or DC offset doesn't skew the threshold.
            counts, edges = np.histogram(dac_raw, bins=100)
            idle_level = float(edges[int(np.argmax(counts))])
            thr_dac = float((idle_level + dac_raw.max()) / 2)
        dac_edges = rising_edges(t_rel, dac_raw, thr_dac,
                                 refractory_s=args.refractory_dac)
        dac_edges = dac_edges[dac_edges > -0.001]
        print(f"  DAC edges detected: {len(dac_edges)}  (threshold {thr_dac:.3f} V)")

    # ── Mode-specific analysis ────────────────────────────────────────────────
    print("\n── Results ──────────────────────────────────────────────────────────────")

    if args.mode == "ttl-dac":
        ttl_matched, dac_matched, mcu_latency = match_ttl_to_dac(
            ttl_edges, dac_edges, _MCU_WINDOW_S)
        print(f"  Matched TTL→DAC pairs: {len(mcu_latency)}")
        if len(mcu_latency) == 0:
            sys.exit("ERROR: no TTL→DAC pairs matched — check thresholds.")
        _print_stats("MCU onset latency  (DAC rising edge − TTL rising edge)", mcu_latency)

        if args.out_csv:
            with open(args.out_csv, "w", newline="") as f:
                w = csv_mod.DictWriter(f, fieldnames=["click_idx", "ttl_s", "dac_s",
                                                       "mcu_latency_us"])
                w.writeheader()
                for i in range(len(mcu_latency)):
                    w.writerow({"click_idx": i,
                                "ttl_s":          round(float(ttl_matched[i]), 6),
                                "dac_s":          round(float(dac_matched[i]), 6),
                                "mcu_latency_us": round(float(mcu_latency[i]) * 1e6, 2)})
            print(f"\nSaved per-click table → {args.out_csv}")

        plot_ttl_dac(t_rel, ttl_raw, dac_raw, ttl_matched, dac_matched,
                     mcu_latency, save_path=args.save)

    elif args.mode == "led-ttl":
        print(f"Fetching trial '{args.trial_id}' from PostgreSQL ...")
        left_clicks, right_clicks = load_scheduled_clicks(args.trial_id)
        scheduled = np.array(sorted(left_clicks + right_clicks))
        print(f"  Scheduled clicks: {len(scheduled)}  ({len(left_clicks)} L + {len(right_clicks)} R)")

        sched_matched, ttl_matched, pi_errors = match_ttl_to_scheduled(
            ttl_edges, scheduled, _MATCH_TOLERANCE_S)
        print(f"  Matched scheduled→TTL pairs: {len(pi_errors)}")
        if len(pi_errors) == 0:
            sys.exit("ERROR: no scheduled→TTL pairs matched — check thresholds and trial-id.")
        _print_stats("Pi-side scheduling error  (TTL rising edge − scheduled time)", pi_errors)

        if args.out_csv:
            with open(args.out_csv, "w", newline="") as f:
                w = csv_mod.DictWriter(f, fieldnames=["click_idx", "scheduled_s", "ttl_s",
                                                       "pi_error_us"])
                w.writeheader()
                for i in range(len(pi_errors)):
                    w.writerow({"click_idx":   i,
                                "scheduled_s": round(float(sched_matched[i]), 6),
                                "ttl_s":       round(float(ttl_matched[i]),   6),
                                "pi_error_us": round(float(pi_errors[i]) * 1e6, 2)})
            print(f"\nSaved per-click table → {args.out_csv}")

        plot_led_ttl(t_rel, led_raw, ttl_raw, sched_matched, ttl_matched,
                     pi_errors, save_path=args.save)

    else:  # full
        print(f"Fetching trial '{args.trial_id}' from PostgreSQL ...")
        left_clicks, right_clicks = load_scheduled_clicks(args.trial_id)
        scheduled = np.array(sorted(left_clicks + right_clicks))
        print(f"  Scheduled clicks: {len(scheduled)}  ({len(left_clicks)} L + {len(right_clicks)} R)")

        sched_matched, ttl_matched, pi_errors = match_ttl_to_scheduled(
            ttl_edges, scheduled, _MATCH_TOLERANCE_S)
        ttl_m2, dac_matched, mcu_latency = match_ttl_to_dac(
            ttl_matched, dac_edges, _MCU_WINDOW_S)
        # Trim to fully matched triples
        idx = np.isin(ttl_matched, ttl_m2)
        sched_matched = sched_matched[idx]
        ttl_matched   = ttl_matched[idx]
        pi_errors     = pi_errors[idx]
        e2e_errors    = pi_errors + mcu_latency

        print(f"  Fully matched triples: {len(pi_errors)}")
        if len(pi_errors) == 0:
            sys.exit("ERROR: no fully matched triples — check thresholds and trial-id.")
        _print_stats("Pi-side scheduling error  (TTL − scheduled)", pi_errors)
        _print_stats("MCU onset latency         (DAC − TTL)       ", mcu_latency)
        _print_stats("End-to-end error          (DAC − scheduled) ", e2e_errors)

        if args.out_csv:
            with open(args.out_csv, "w", newline="") as f:
                w = csv_mod.DictWriter(f, fieldnames=[
                    "click_idx", "scheduled_s", "ttl_s", "dac_s",
                    "pi_error_us", "mcu_latency_us", "e2e_error_us"])
                w.writeheader()
                for i in range(len(pi_errors)):
                    w.writerow({
                        "click_idx":      i,
                        "scheduled_s":    round(float(sched_matched[i]), 6),
                        "ttl_s":          round(float(ttl_matched[i]),   6),
                        "dac_s":          round(float(dac_matched[i]),   6),
                        "pi_error_us":    round(float(pi_errors[i])    * 1e6, 2),
                        "mcu_latency_us": round(float(mcu_latency[i])  * 1e6, 2),
                        "e2e_error_us":   round(float(e2e_errors[i])   * 1e6, 2),
                    })
            print(f"\nSaved per-click table → {args.out_csv}")

        plot_full(t_rel, ttl_raw, dac_raw, sched_matched, ttl_matched, dac_matched,
                  pi_errors, mcu_latency, save_path=args.save)


if __name__ == "__main__":
    main()
