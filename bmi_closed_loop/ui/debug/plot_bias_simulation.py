#!/usr/bin/env python3
"""
Bias correction algorithm validation (sec:val_bias_correction).

Runs both the Brody and IBL algorithms against a synthetic animal with a
fixed right-side preference and plots:
  - Top panel:    rolling P(correct=left) set by each algorithm vs trial number
  - Bottom panel: rolling fraction-correct for each algorithm vs trial number

The algorithm implementations are extracted verbatim from cage_runner.py so
the simulation exercises the exact production logic, not an approximation.

Usage:
    python plot_bias_simulation.py
    python plot_bias_simulation.py --p-right 0.8 --n-trials 500
    python plot_bias_simulation.py --save bias_validation.png
"""

import argparse

import matplotlib.pyplot as plt
import numpy as np

_BRODY_WINDOW = 20   # matches cage_runner._query_recent_trials window
_IBL_WINDOW   = 10   # matches cage_runner IBL look-back


# ── Algorithm implementations (mirror of cage_runner._apply_bias, no DB) ─────

def _brody_p_left(history: list[dict]) -> float:
    """Exact Brody logic from cage_runner.py applied to a local history list."""
    recent     = history[-_BRODY_WINDOW:]
    left_hits  = [t["outcome"] == "correct" for t in recent if t["correct_side"] == "left"]
    right_hits = [t["outcome"] == "correct" for t in recent if t["correct_side"] == "right"]
    if not left_hits or not right_hits:
        return 0.5
    fc_l  = sum(left_hits)  / len(left_hits)
    fc_r  = sum(right_hits) / len(right_hits)
    total = fc_l + fc_r
    return (fc_r / total) if total > 0 else 0.5


def _ibl_p_left(history: list[dict]) -> float | None:
    """
    Exact IBL logic from cage_runner.py applied to a local history list.

    The easy-trial ratio gate requires actual click counts which do not exist
    in this simulation, so it is disabled (fires on any wrong trial), matching
    the cage_runner fallback when click_ratio is None.

    Returns None when the algorithm does not trigger (no update this trial).
    """
    if not history or history[-1]["outcome"] != "wrong":
        return None
    recent  = history[-_IBL_WINDOW:]
    choices = []
    for t in recent:
        cs   = t["correct_side"]
        resp = cs if t["outcome"] == "correct" else ("right" if cs == "left" else "left")
        choices.append(resp)
    if not choices:
        return None
    avg_right = sum(1 for c in choices if c == "right") / len(choices)
    return 1.0 - avg_right


# ── Simulation ────────────────────────────────────────────────────────────────

def simulate(n_trials: int, p_right: float, alg: str, seed: int) -> dict:
    """
    Simulate n_trials against a fixed-bias animal (responds right with
    probability p_right on every trial, regardless of correct side).

    Returns arrays of length n_trials:
      p_left    — P(correct=left) chosen by the algorithm each trial
      correct   — 1.0 if animal responded correctly, 0.0 otherwise
    """
    rng     = np.random.default_rng(seed)
    history: list[dict] = []
    p_left_arr = np.empty(n_trials)
    correct_arr = np.empty(n_trials)

    for i in range(n_trials):
        if alg == "brody":
            p_left = _brody_p_left(history)
        elif alg == "ibl":
            nudge  = _ibl_p_left(history)
            p_left = nudge if nudge is not None else 0.5
        else:
            p_left = 0.5

        correct_side  = "left" if rng.random() < p_left else "right"
        animal_choice = "right" if rng.random() < p_right else "left"
        outcome       = "correct" if animal_choice == correct_side else "wrong"

        p_left_arr[i]  = p_left
        correct_arr[i] = 1.0 if outcome == "correct" else 0.0
        history.append({"correct_side": correct_side, "outcome": outcome})

    return {"p_left": p_left_arr, "correct": correct_arr}


def _rolling(arr: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        out[i] = arr[i - window + 1 : i + 1].mean()
    return out


# ── Plot ──────────────────────────────────────────────────────────────────────

def plot(brody: dict, ibl: dict, p_right: float, n_trials: int,
         window: int, save_path: str | None) -> None:

    trials = np.arange(1, n_trials + 1)

    fig, ax = plt.subplots(figsize=(10, 4))

    ax.plot(trials, _rolling(brody["p_left"], window), color="steelblue", lw=2.0,
            label=f"Force-other-side (rolling {window})")
    ax.plot(trials, _rolling(ibl["p_left"],  window), color="darkorange", lw=2.0,
            label=f"Reward-for-engagement (rolling {window})")
    ax.axhline(0.5, color="gray", lw=0.8, ls="--", label="Unbiased (0.5)")
    ax.set_ylim(0, 1)
    ax.set_xlabel("Trial number")
    ax.set_ylabel("P(correct side = left)")
    ax.legend(fontsize=9, loc="upper right")

    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved → {save_path}")
    else:
        plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="Bias correction algorithm validation")
    p.add_argument("--p-right",   type=float, default=0.3,
                   help="Animal's true P(respond right) — the side preference (default: 0.7)")
    p.add_argument("--n-trials",  type=int,   default=300,
                   help="Number of trials to simulate (default: 300)")
    p.add_argument("--window",    type=int,   default=20,
                   help="Rolling average window for plots (default: 20)")
    p.add_argument("--seed",      type=int,   default=42,
                   help="RNG seed (default: 42)")
    p.add_argument("--save",      default=None,
                   help="Save figure to this path instead of displaying")
    args = p.parse_args()

    brody = simulate(args.n_trials, args.p_right, "brody", seed=args.seed)
    ibl   = simulate(args.n_trials, args.p_right, "ibl",   seed=args.seed)

    # Print convergence summary
    tail = max(1, args.n_trials // 5)
    for name, res in [("Brody", brody), ("IBL", ibl)]:
        p_left_final  = res["p_left"][-tail:].mean()
        correct_final = res["correct"][-tail:].mean()
        print(f"{name:6s}  final P(left)={p_left_final:.3f}  "
              f"final correct rate={correct_final:.3f}")

    plot(brody, ibl, args.p_right, args.n_trials, args.window, args.save)


if __name__ == "__main__":
    main()
