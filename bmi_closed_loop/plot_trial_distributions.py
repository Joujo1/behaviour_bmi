#!/usr/bin/env python3
"""
Plot click generation and side shuffling distributions.

Usage:
    # Query real DB data from a session:
    python plot_trial_distributions.py --session 3

    # Simulate N trials locally (no DB needed):
    python plot_trial_distributions.py --simulate 1000

    # Save to file instead of showing:
    python plot_trial_distributions.py --session 3 --save plots.png
"""

import argparse
import random
import sys

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import psycopg2
import config
from scipy.stats import poisson as poisson_dist
from ui.click_generator import generate_clicks


def load_from_db(session_id: int) -> list[dict]:
    sys.path.insert(0, ".")
    conn = psycopg2.connect(config.POSTGRES_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT tr.correct_side, tr.click_seed, ts.task_config
                FROM trial_results tr
                JOIN training_substages ts ON ts.id = tr.substage_id
                WHERE tr.session_id = %s
                  AND tr.outcome    != 'aborted'
                  AND tr.click_seed IS NOT NULL
                  AND tr.correct_side IS NOT NULL
                ORDER BY tr.id
            """, (session_id,))
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        raise SystemExit(f"No trials with click_seed found for session {session_id}.")

    trials = []
    for correct_side, seed, task_config in rows:
        # Rates live inside the play_clicks action, not at the top level
        base_left, base_right, duration = 0.0, 0.0, 1.0
        for state in task_config.get("states", []):
            for phase in ("entry_actions", "exit_actions"):
                for action in state.get(phase, []):
                    if action.get("type") == "play_clicks":
                        base_left  = action.get("left_rate",      0) or 0
                        base_right = action.get("right_rate",     0) or 0
                        duration   = action.get("click_duration", 1.0) or 1.0

        # Reconstruct side assignment: high rate always goes to correct side
        high_rate = max(base_left, base_right)
        low_rate  = min(base_left, base_right)
        l_rate = high_rate if correct_side == "left" else low_rate
        r_rate = low_rate  if correct_side == "left" else high_rate

        clicks = generate_clicks(l_rate, r_rate, duration, seed=seed)
        trials.append({
            "correct_side":  correct_side,
            "left_clicks":   clicks["left_clicks"],
            "right_clicks":  clicks["right_clicks"],
            "left_rate":     l_rate,
            "right_rate":    r_rate,
            "duration":      duration,
        })
    return trials


def simulate_trials(n: int, left_rate: float = 40.0, right_rate: float = 10.0,
                    duration: float = 1.0) -> list[dict]:
    """Generate n synthetic trials using the same code as the live system."""
    sys.path.insert(0, ".")
    from ui.click_generator import generate_clicks

    trials = []
    for _ in range(n):
        correct_side = random.choice(["left", "right"])
        seed = random.randrange(2**32)
        hr, lr = max(left_rate, right_rate), min(left_rate, right_rate)
        l_rate = hr if correct_side == "left" else lr
        r_rate = lr if correct_side == "left" else hr
        clicks = generate_clicks(l_rate, r_rate, duration, seed=seed)
        trials.append({
            "correct_side":  correct_side,
            "left_clicks":   clicks["left_clicks"],
            "right_clicks":  clicks["right_clicks"],
            "left_rate":     l_rate,
            "right_rate":    r_rate,
            "duration":      duration,
        })
    return trials


# ── Plot ──────────────────────────────────────────────────────────────────────

def plot(trials: list[dict], title: str, save_path: str | None = None):
    n = len(trials)

    left_counts  = [len(t["left_clicks"])  for t in trials]
    right_counts = [len(t["right_clicks"]) for t in trials]
    correct_sides = [t["correct_side"] for t in trials]

    # ICI (inter-click intervals) pooled across all trials
    left_icis  = []
    right_icis = []
    for t in trials:
        if len(t["left_clicks"])  > 1: left_icis.extend(np.diff(t["left_clicks"]).tolist())
        if len(t["right_clicks"]) > 1: right_icis.extend(np.diff(t["right_clicks"]).tolist())

    # High and low rates are symmetric across sides — derive from any trial
    duration   = trials[0]["duration"]
    high_rate  = max(trials[0]["left_rate"], trials[0]["right_rate"])
    low_rate   = min(trials[0]["left_rate"], trials[0]["right_rate"])
    lam_high   = high_rate * duration
    lam_low    = low_rate  * duration

    PULSE_S = 100e-6  # CLICK_PULSE_US from RPi config
    all_icis = left_icis + right_icis
    n_overlap = sum(1 for ici in all_icis if ici < PULSE_S)

    fig = plt.figure(figsize=(18, 5))
    fig.suptitle(f"{title}  (n={n} trials)", fontsize=13, fontweight="bold")
    gs = gridspec.GridSpec(1, 4, figure=fig, hspace=0.42, wspace=0.35)

    # ── 1. Side distribution ─────────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0])

    n_left  = correct_sides.count("left")
    n_right = correct_sides.count("right")
    bars = ax1.bar(["Left", "Right"], [n_left, n_right],
                   color=["#3b82f6", "#ef4444"], width=0.5)
    ax1.axhline(n / 2, color="k", linestyle="--", linewidth=1, label="Expected 50%")
    for bar, val in zip(bars, [n_left, n_right]):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + n*0.005,
                 f"{val}\n({100*val/n:.1f}%)", ha="center", va="bottom", fontsize=9)
    ax1.set_title("Correct side distribution")
    ax1.set_ylabel("Trial count")
    ax1.legend(fontsize=8)
    ax1.set_ylim(0, max(n_left, n_right) * 1.15)

    # ── 2. Left click count distribution ─────────────────────────────────────
    ax2 = fig.add_subplot(gs[1])

    max_count = max(left_counts + right_counts) + 1
    bins = np.arange(-0.5, max_count + 0.5)
    ax2.hist(left_counts, bins=bins, color="#3b82f6", alpha=0.7, label="Left")
    k = np.arange(0, max_count + 1)
    # Mixture of Poisson(high) and Poisson(low) weighted 50/50
    mixture = 0.5 * (poisson_dist.pmf(k, lam_high) + poisson_dist.pmf(k, lam_low))
    ax2.plot(k, mixture * n, "b--", linewidth=1.5,
             label=f"0.5·Poisson({lam_high:.0f}) + 0.5·Poisson({lam_low:.0f})")
    ax2.set_title(f"Left clicks  (high={high_rate}/s  low={low_rate}/s)")
    ax2.set_xlabel("Clicks per trial")
    ax2.set_ylabel("Count")
    ax2.legend(fontsize=7)

    # ── 3. Right click count distribution ────────────────────────────────────
    ax3 = fig.add_subplot(gs[2])

    ax3.hist(right_counts, bins=bins, color="#ef4444", alpha=0.7, label="Right")
    ax3.plot(k, mixture * n, "r--", linewidth=1.5,
             label=f"0.5·Poisson({lam_high:.0f}) + 0.5·Poisson({lam_low:.0f})")
    ax3.set_title(f"Right clicks  (high={high_rate}/s  low={low_rate}/s)")
    ax3.set_xlabel("Clicks per trial")
    ax3.set_ylabel("Count")
    ax3.legend(fontsize=7)

    # Shared y-scale for click count plots
    shared_ylim = max(ax2.get_ylim()[1], ax3.get_ylim()[1])
    ax2.set_ylim(0, shared_ylim)
    ax3.set_ylim(0, shared_ylim)

    # ── 4. Short-ICI overlap check ────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[3])
    all_icis_ms = [ici * 1000 for ici in all_icis]
    if all_icis_ms:
        ax4.hist(all_icis_ms, bins=np.arange(0, max(all_icis_ms) + 0.1, 0.1), color="#888", alpha=0.8)
    ax4.axvline(PULSE_S * 1000, color="r", linestyle="--", linewidth=1.5,
                label=f"Pulse width ({PULSE_S*1e6:.0f} µs)")
    pct = 100 * n_overlap / len(all_icis) if all_icis else 0
    ax4.set_title(f"ICI distribution  ({n_overlap} overlap, {pct:.3f}%)")
    ax4.set_xlabel("ICI (ms)")
    ax4.set_ylabel("Count")
    ax4.legend(fontsize=7)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved → {save_path}")
    else:
        plt.show()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--session",  type=int,   help="Session ID to query from DB")
    group.add_argument("--simulate", type=int,   help="Number of trials to simulate")
    parser.add_argument("--left-rate",  type=float, default=40.0)
    parser.add_argument("--right-rate", type=float, default=10.0)
    parser.add_argument("--duration",   type=float, default=1.0)
    parser.add_argument("--save", type=str, default=None,
                        help="Save to this path instead of showing the window")
    args = parser.parse_args()

    if args.session is not None:
        trials = load_from_db(args.session)
        title  = f"Session {args.session}"
    else:
        trials = simulate_trials(args.simulate, args.left_rate, args.right_rate, args.duration)
        title  = f"Simulation  (left={args.left_rate}/s  right={args.right_rate}/s  dur={args.duration}s)"

    plot(trials, title, save_path=args.save)


if __name__ == "__main__":
    main()
