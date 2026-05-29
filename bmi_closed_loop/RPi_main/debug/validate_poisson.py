#!/usr/bin/env python3
"""
Session-level click-count validation (sec:val_click_stats, second figure).

Generates a synthetic session of N trials using the production click_generator,
where each trial randomly draws its rate pair from a small operational set.
Plots the left- and right-channel clicks-per-trial distributions overlaid
with the analytical Poisson mixture that the per-trial randomisation predicts.

This complements the per-rate ICI validation by showing that the production
generator, including the min_ici clamp, produces session-level click-count
distributions consistent with the expected mixture of Poissons.

Usage:
    python debug/validate_clicks_session.py
    python debug/validate_clicks_session.py --n 12000 --dur 1.0
    python debug/validate_clicks_session.py --out output/click_session_stats.png
"""

import argparse
import os
import sys
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import poisson

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from ui.click_generator import generate_clicks, CLICK_WIDTH_S

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

MIN_ICI    = 2 * CLICK_WIDTH_S          # 6 ms — matches generate_clicks() default
HIGH_RATE  = 30                          # high clicks/s per channel
LOW_RATE   = 10                          # low clicks/s per channel
LEFT_COLOR  = "#1f77b4"
RIGHT_COLOR = "#d62728"


def run_session(n_trials: int, duration: float, seed: int) -> dict:
    """
    Run a synthetic session of n_trials.
    Each trial randomly assigns (high, low) or (low, high) to (left, right)
    with equal probability — matching the random side-resolution mode.
    Returns clicks-per-trial counts for each channel.
    """
    rng = np.random.default_rng(seed)
    left_counts  = np.empty(n_trials, dtype=np.int32)
    right_counts = np.empty(n_trials, dtype=np.int32)

    for i in range(n_trials):
        if rng.random() < 0.5:
            l_rate, r_rate = HIGH_RATE, LOW_RATE
        else:
            l_rate, r_rate = LOW_RATE, HIGH_RATE

        result = generate_clicks(l_rate, r_rate, duration,
                                 seed=int(rng.integers(0, 2**31 - 1)),
                                 min_ici=MIN_ICI)
        left_counts[i]  = len(result["left_clicks"])
        right_counts[i] = len(result["right_clicks"])

    return {"left": left_counts, "right": right_counts}


def mixture_pmf(k_range: np.ndarray, high: int, low: int) -> np.ndarray:
    """Analytical mixture 0.5 * Poisson(high) + 0.5 * Poisson(low) evaluated on k_range."""
    return 0.5 * poisson.pmf(k_range, high) + 0.5 * poisson.pmf(k_range, low)


def plot(counts: dict, n_trials: int, save_path: str) -> None:
    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)

    k_max = max(int(counts["left"].max()), int(counts["right"].max())) + 5
    k_range = np.arange(0, k_max + 1)
    pmf = mixture_pmf(k_range, HIGH_RATE, LOW_RATE)

    # Left channel
    ax_l.hist(counts["left"], bins=np.arange(0, k_max + 2) - 0.5,
              color=LEFT_COLOR, alpha=0.5, edgecolor=LEFT_COLOR,
              label=f"Left (N = {n_trials})")
    ax_l.plot(k_range, pmf * n_trials, color=LEFT_COLOR, linestyle="--", linewidth=2,
              label=f"0.5·Poisson({HIGH_RATE}) + 0.5·Poisson({LOW_RATE})")
    ax_l.set_xlabel("Clicks per trial")
    ax_l.set_ylabel("Count")
    ax_l.set_title(f"Left channel  (high = {HIGH_RATE}/s, low = {LOW_RATE}/s)")
    ax_l.legend(fontsize=9, loc="upper right")
    ax_l.grid(alpha=0.3)

    # Right channel
    ax_r.hist(counts["right"], bins=np.arange(0, k_max + 2) - 0.5,
              color=RIGHT_COLOR, alpha=0.5, edgecolor=RIGHT_COLOR,
              label=f"Right (N = {n_trials})")
    ax_r.plot(k_range, pmf * n_trials, color=RIGHT_COLOR, linestyle="--", linewidth=2,
              label=f"0.5·Poisson({HIGH_RATE}) + 0.5·Poisson({LOW_RATE})")
    ax_r.set_xlabel("Clicks per trial")
    ax_r.set_title(f"Right channel  (high = {HIGH_RATE}/s, low = {LOW_RATE}/s)")
    ax_r.legend(fontsize=9, loc="upper right")
    ax_r.grid(alpha=0.3)

    fig.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Plot saved → {save_path}")
    plt.show()


def main() -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = os.path.join(OUTPUT_DIR, f"validate_clicks_session_{ts}.png")

    p = argparse.ArgumentParser(description="Session-level click-count validation")
    p.add_argument("--n",    type=int,   default=12000, help="Number of trials (default: 12000)")
    p.add_argument("--dur",  type=float, default=1.0,   help="Trial duration s (default: 1.0)")
    p.add_argument("--seed", type=int,   default=42,    help="RNG seed (default: 42)")
    p.add_argument("--out",  default=default_out,       help="Output PNG path")
    args = p.parse_args()

    print(f"Running session of {args.n} trials × {args.dur:.1f} s with "
          f"random side assignment between ({HIGH_RATE}/s, {LOW_RATE}/s) ...")
    counts = run_session(args.n, args.dur, args.seed)

    # Summary
    for name, arr in [("Left", counts["left"]), ("Right", counts["right"])]:
        print(f"  {name:5s}  mean={arr.mean():.2f}  std={arr.std():.2f}  "
              f"min={arr.min()}  max={arr.max()}")

    plot(counts, args.n, args.out)


if __name__ == "__main__":
    main()