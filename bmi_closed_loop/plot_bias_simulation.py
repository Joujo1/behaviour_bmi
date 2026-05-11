#!/usr/bin/env python3
"""
Side-bias correction algorithm simulator.

Simulates a biased animal and shows how Brody / IBL algorithms respond.

Usage:
    python plot_bias_simulation.py                     # default: 70% left, 200 trials, both algorithms
    python plot_bias_simulation.py --bias 0.8          # animal chooses left 80% of the time
    python plot_bias_simulation.py --trials 500
    python plot_bias_simulation.py --alg brody
    python plot_bias_simulation.py --alg ibl
    python plot_bias_simulation.py --save bias_sim.png
"""

import argparse
import random

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

WINDOW = 20   # trials looked back by both algorithms
IBL_WINDOW = 10  # IBL looks back at the last 10 responded trials for choice history


# ---------------------------------------------------------------------------
# Algorithm implementations (mirror of cage_runner.py, no DB needed)
# ---------------------------------------------------------------------------

def brody_left_prob(history: list[dict]) -> float:
    """Return P(next correct_side = left) using Brody anti-bias."""
    recent = history[-WINDOW:]
    left_hits  = [t["outcome"] == "correct" for t in recent if t["correct_side"] == "left"]
    right_hits = [t["outcome"] == "correct" for t in recent if t["correct_side"] == "right"]
    if not left_hits or not right_hits:
        return 0.5
    fc_l  = sum(left_hits)  / len(left_hits)
    fc_r  = sum(right_hits) / len(right_hits)
    total = fc_l + fc_r
    return (fc_r / total) if total > 0 else 0.5


def ibl_left_prob(history: list[dict]) -> float | None:
    """
    Return P(next correct_side = left) using IBL debias, or None if not triggered.
    Triggers only when the most recent trial was wrong.
    """
    responded = [t for t in history if t["outcome"] != "aborted"]
    if not responded or responded[-1]["outcome"] != "wrong":
        return None
    recent = responded[-IBL_WINDOW:]
    choices = []
    for t in recent:
        cs = t["correct_side"]
        resp = cs if t["outcome"] == "correct" else ("right" if cs == "left" else "left")
        choices.append(resp)
    if not choices:
        return None
    avg_right = sum(1 for c in choices if c == "right") / len(choices)
    return 1.0 - avg_right


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def simulate(n_trials: int, animal_left_bias: float, alg: str, seed: int = 42) -> dict:
    """
    Run one simulation.

    animal_left_bias: probability animal actually chooses left (0.7 = biased)
    alg: 'brody', 'ibl', or 'none'

    Returns arrays of per-trial values for plotting.
    """
    rng = random.Random(seed)
    history = []

    left_probs     = []   # P(correct_side = left) used for this trial
    correct_sides  = []   # which side was the correct side this trial
    animal_choices = []   # what the animal actually did
    outcomes       = []   # correct / wrong
    ibl_triggered  = []   # bool: did IBL fire this trial?

    for _ in range(n_trials):
        # Compute left_probability for this trial
        if alg == "brody":
            p_left = brody_left_prob(history)
        elif alg == "ibl":
            nudge = ibl_left_prob(history)
            p_left = nudge if nudge is not None else 0.5
            ibl_triggered.append(nudge is not None)
        else:
            p_left = 0.5

        left_probs.append(p_left)

        # Coin flip to pick correct side
        correct_side = "left" if rng.random() < p_left else "right"
        correct_sides.append(correct_side)

        # Animal chooses based on its bias
        animal_choice = "left" if rng.random() < animal_left_bias else "right"
        animal_choices.append(animal_choice)

        outcome = "correct" if animal_choice == correct_side else "wrong"
        outcomes.append(outcome)

        history.append({
            "correct_side": correct_side,
            "outcome":      outcome,
        })

    return {
        "left_probs":     np.array(left_probs),
        "correct_sides":  correct_sides,
        "animal_choices": animal_choices,
        "outcomes":       outcomes,
        "ibl_triggered":  ibl_triggered,
    }


def rolling_mean(arr, window: int) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        out[i] = np.mean(arr[i - window + 1 : i + 1])
    return out


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot(results: dict[str, dict], animal_bias: float, n_trials: int, save: str | None):
    algs = list(results.keys())
    n    = len(algs)
    fig  = plt.figure(figsize=(14, 4 * n + 1))
    fig.suptitle(
        f"Side-bias simulation — animal P(left)={animal_bias:.0%}, {n_trials} trials",
        fontsize=13, fontweight="bold",
    )
    gs = gridspec.GridSpec(n, 2, figure=fig, wspace=0.35, hspace=0.55)

    for row, alg in enumerate(algs):
        r       = results[alg]
        trials  = np.arange(1, n_trials + 1)
        choices = np.array([1 if c == "left" else 0 for c in r["animal_choices"]])
        corr    = np.array([1 if o == "correct" else 0 for o in r["outcomes"]])

        # Left panel — P(correct=left) the algorithm chose, rolling animal left-choice rate
        ax1 = fig.add_subplot(gs[row, 0])
        ax1.plot(trials, r["left_probs"], color="steelblue", lw=1.2, label="P(correct=left) set by alg")
        ax1.plot(trials, rolling_mean(choices, WINDOW), color="tomato", lw=1.5,
                 label=f"Animal left-choice rate (rolling {WINDOW})")
        ax1.axhline(animal_bias, color="tomato", lw=0.8, ls="--", alpha=0.5, label=f"True animal bias ({animal_bias:.0%})")
        ax1.axhline(0.5, color="gray", lw=0.6, ls=":")
        if alg == "ibl" and r["ibl_triggered"]:
            trig_x = [i + 1 for i, t in enumerate(r["ibl_triggered"]) if t]
            ax1.scatter(trig_x, [r["left_probs"][i - 1] for i in trig_x],
                        marker="|", color="orange", s=40, zorder=3, label="IBL triggered")
        ax1.set_ylim(0, 1)
        ax1.set_xlabel("Trial")
        ax1.set_ylabel("Probability")
        ax1.set_title(f"{alg.upper()} — side allocation")
        ax1.legend(fontsize=7, loc="upper right")

        # Right panel — rolling accuracy
        ax2 = fig.add_subplot(gs[row, 1])
        ax2.plot(trials, rolling_mean(corr, WINDOW), color="seagreen", lw=1.5,
                 label=f"Rolling accuracy (window {WINDOW})")
        ax2.axhline(0.5, color="gray", lw=0.6, ls=":", label="Chance")
        ax2.set_ylim(0, 1)
        ax2.set_xlabel("Trial")
        ax2.set_ylabel("Fraction correct")
        ax2.set_title(f"{alg.upper()} — accuracy")
        ax2.legend(fontsize=7, loc="upper right")

    plt.tight_layout()
    if save:
        fig.savefig(save, dpi=150)
        print(f"Saved to {save}")
    else:
        plt.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Side-bias algorithm simulator")
    parser.add_argument("--bias",   type=float, default=0.7,
                        help="Animal's true P(choose left), e.g. 0.7")
    parser.add_argument("--trials", type=int,   default=200,
                        help="Number of trials to simulate")
    parser.add_argument("--alg",    choices=["brody", "ibl", "both", "none"], default="both",
                        help="Which algorithm to show")
    parser.add_argument("--save",   type=str,   default=None,
                        help="Save figure to this path instead of showing")
    parser.add_argument("--seed",   type=int,   default=42)
    args = parser.parse_args()

    algs_to_run = ["brody", "ibl"] if args.alg == "both" else [args.alg]
    results = {
        alg: simulate(args.trials, args.bias, alg, seed=args.seed)
        for alg in algs_to_run
    }
    plot(results, args.bias, args.trials, args.save)


if __name__ == "__main__":
    main()
