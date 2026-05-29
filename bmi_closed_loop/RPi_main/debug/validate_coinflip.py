"""
Side assignment balance validator.

Tests all three side_modes from cage_runner._resolve_sides():
  random   — should produce 50/50 left/right regardless of trial definition
  weighted — left fraction should match left_probability within chi-squared tolerance
  fixed    — high_rate_side should always equal the high-rate side

Note: _resolve_sides no longer resolves high_click_side / low_click_side aliases;
that is done by _resolve_aliases after click expansion. This validator only tests
the rate-assignment / coin-flip behaviour, which is unchanged.

Runs anywhere (no hardware needed). Inlines _resolve_sides to avoid import path issues;
keep in sync with cage_runner.py if the function changes.

Usage:
    python3 debug/validate_coinflip.py [--n 10000]
    python3 debug/validate_coinflip.py --out output/validate_coinflip.png
"""

import argparse
import copy
import os
import random
from datetime import datetime

import numpy as np
from scipy.stats import chi2, binom
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


# ── Inlined from cage_runner._resolve_sides ─────────────────────────────────
# Keep in sync with bmi_closed_loop/ui/cage_runner.py
# Note: alias resolution is NOT part of _resolve_sides anymore; it lives in
# _resolve_aliases (post-expansion). This copy only tests rate assignment.

def _resolve_sides(trial_definition: dict) -> tuple:
    side_mode = trial_definition.get("side_mode", "random")
    trial = copy.deepcopy(trial_definition)

    if side_mode == "fixed":
        high_rate_side = None
        for state in trial.get("states", []):
            for phase in ("entry_actions", "exit_actions"):
                for action in state.get(phase, []):
                    if action.get("type") == "play_clicks":
                        lr = action.get("left_rate",  0) or 0
                        rr = action.get("right_rate", 0) or 0
                        high_rate_side = "left" if lr >= rr else "right"
        return trial, high_rate_side

    SIDE_ALIASES = {"high_click_side", "low_click_side"}
    def _uses_sides(t):
        for state in t.get("states", []):
            for phase in ("entry_actions", "exit_actions"):
                for action in state.get(phase, []):
                    if action.get("type") == "play_clicks": return True
                    if action.get("target") in SIDE_ALIASES: return True
            for transition in state.get("transitions", []):
                if transition.get("target") in SIDE_ALIASES: return True
        return False

    if not _uses_sides(trial):
        return trial, None

    if side_mode == "weighted":
        left_prob      = max(0.0, min(1.0, float(trial_definition.get("left_probability", 0.5))))
        high_rate_side = "left" if random.random() < left_prob else "right"
    else:
        high_rate_side = random.choice(["left", "right"])
    low_rate_side = "right" if high_rate_side == "left" else "left"

    for state in trial.get("states", []):
        for phase in ("entry_actions", "exit_actions"):
            for action in state.get(phase, []):
                if action.get("type") == "play_clicks":
                    lr = action.get("left_rate", 0) or 0
                    rr = action.get("right_rate", 0) or 0
                    high_rate, low_rate = max(lr, rr), min(lr, rr)
                    action["left_rate"]  = high_rate if high_rate_side == "left" else low_rate
                    action["right_rate"] = low_rate  if high_rate_side == "left" else high_rate

    return trial, high_rate_side
# ────────────────────────────────────────────────────────────────────────────


def _make_trial(side_mode: str, left_rate: float = 40.0, right_rate: float = 10.0,
                left_probability: float = 0.5) -> dict:
    """Minimal trial definition that exercises side assignment."""
    d = {
        "trial_id":    "test",
        "side_mode":   side_mode,
        "initial_state": "s0",
        "states": [{
            "id": "s0",
            "entry_actions": [
                {"type": "play_clicks", "left_rate": left_rate,
                 "right_rate": right_rate, "click_duration": 1.0},
                {"type": "led_on", "target": "high_click_side"},
            ],
            "transitions": [
                {"trigger": "beam_break", "target": "high_click_side",
                 "next_state": "__correct__"},
                {"trigger": "beam_break", "target": "low_click_side",
                 "next_state": "__wrong__"},
            ],
        }],
    }
    if side_mode == "weighted":
        d["left_probability"] = left_probability
    return d


def run_random(n: int) -> dict:
    trial = _make_trial("random")
    sides = [_resolve_sides(trial)[1] for _ in range(n)]
    n_left = sides.count("left")
    # Binomial test: H0 p=0.5
    p_val  = binom.sf(max(n_left, n - n_left) - 1, n, 0.5) * 2
    return {"n_left": n_left, "n_right": n - n_left, "p_val": p_val,
            "obs_frac": n_left / n, "expected": 0.5}


def run_weighted(n: int, probs: list) -> list:
    results = []
    for p_left in probs:
        trial = _make_trial("weighted", left_probability=p_left)
        sides = [_resolve_sides(trial)[1] for _ in range(n)]
        n_left = sides.count("left")
        p_val  = binom.sf(max(n_left, n - n_left) - 1, n, p_left) * 2
        results.append({"p_left": p_left, "n_left": n_left,
                        "obs_frac": n_left / n, "p_val": p_val})
    return results


def run_fixed(n: int) -> dict:
    """Fixed mode: high_rate_side should always be the high-rate side (left here)."""
    trial = _make_trial("fixed", left_rate=40.0, right_rate=10.0)
    sides = [_resolve_sides(trial)[1] for _ in range(n)]
    always_left = all(s == "left" for s in sides)
    return {"always_high_side": always_left,
            "n_left": sides.count("left"), "n_right": sides.count("right")}


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = os.path.join(OUTPUT_DIR, f"validate_coinflip_{ts}.png")

    p = argparse.ArgumentParser(description="Side assignment balance validator")
    p.add_argument("--n",   type=int, default=10000, help="Trials per test (default: 10000)")
    p.add_argument("--out", default=default_out)
    args = p.parse_args()

    n = args.n
    WEIGHTED_PROBS = [0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9]

    print(f"Running {n} trials per test …\n")

    rnd = run_random(n)
    wgt = run_weighted(n, WEIGHTED_PROBS)
    fxd = run_fixed(n)

    # Print summary
    print(f"RANDOM mode: left={rnd['n_left']}  right={rnd['n_right']}  "
          f"frac={rnd['obs_frac']:.4f}  (expected 0.5000)  p={rnd['p_val']:.4f} "
          f"{'✓' if rnd['p_val'] > 0.01 else '✗ FAIL'}")

    print(f"\nWEIGHTED mode:")
    print(f"  {'p_left':>7}  {'obs':>7}  {'diff':>7}  {'p_val':>8}  {'pass':>5}")
    print("  " + "─" * 40)
    for r in wgt:
        diff = r["obs_frac"] - r["p_left"]
        ok   = "✓" if r["p_val"] > 0.01 else "✗"
        print(f"  {r['p_left']:7.2f}  {r['obs_frac']:7.4f}  {diff:+7.4f}  "
              f"{r['p_val']:8.4f}  {ok}")

    print(f"\nFIXED mode: always high-rate side = {'✓' if fxd['always_high_side'] else '✗ FAIL'}  "
          f"(left={fxd['n_left']} right={fxd['n_right']})")

    # Thesis table (tab:side_modes)
    print("\n── Thesis table: tab:side_modes " + "─" * 44)
    print(f"  {'Mode':<18}  {'Target P(left)':>14}  {'Observed P(left)':>16}  {'N':>6}  {'Result':>6}")
    print("  " + "─" * 67)
    print(f"  {'Random':<18}  {'0.500':>14}  {rnd['obs_frac']:>16.4f}  {n:>6}  "
          f"{'PASS' if rnd['p_val'] > 0.01 else 'FAIL':>6}")
    for r in wgt:
        print(f"  {'Weighted':<18}  {r['p_left']:>14.3f}  {r['obs_frac']:>16.4f}  {n:>6}  "
              f"{'PASS' if r['p_val'] > 0.01 else 'FAIL':>6}")
    print(f"  {'Fixed':<18}  {'1.000 (left)':>14}  {fxd['n_left']/n:>16.4f}  {n:>6}  "
          f"{'PASS' if fxd['always_high_side'] else 'FAIL':>6}")

    # --- Plot ---
    fig = plt.figure(figsize=(14, 8))
    fig.suptitle(f"Side assignment validation  —  {n} trials per test",
                 fontsize=12, fontweight="bold")
    gs = gridspec.GridSpec(1, 3, figure=fig, wspace=0.4)

    # Panel 0: Random mode — bar chart
    ax = fig.add_subplot(gs[0])
    bars = ax.bar(["left", "right"], [rnd["n_left"], rnd["n_right"]],
                  color=["#4e79a7", "#f28e2b"])
    ax.axhline(n / 2, color="red", linewidth=1.2, linestyle="--", label="expected 50%")
    ax.set_ylabel("Count")
    ax.set_title(f"Random mode\nobs frac={rnd['obs_frac']:.4f}  p={rnd['p_val']:.3f}", fontsize=9)
    ax.legend(fontsize=8)
    for bar, cnt in zip(bars, [rnd["n_left"], rnd["n_right"]]):
        ax.text(bar.get_x() + bar.get_width() / 2, cnt + n * 0.005,
                f"{cnt}", ha="center", va="bottom", fontsize=8)

    # Panel 1: Weighted mode — observed vs expected scatter
    ax = fig.add_subplot(gs[1])
    p_left_vals = [r["p_left"]   for r in wgt]
    obs_vals    = [r["obs_frac"] for r in wgt]
    ax.plot([0, 1], [0, 1], "k--", linewidth=1.0, label="ideal")
    ax.scatter(p_left_vals, obs_vals, color="#e15759", s=60, zorder=5)
    for r in wgt:
        ax.annotate(f"{r['p_left']:.1f}", (r["p_left"], r["obs_frac"]),
                    textcoords="offset points", xytext=(5, 3), fontsize=7)
    # 95% CI bands for binomial
    ci = 1.96 * np.sqrt(np.array(p_left_vals) * (1 - np.array(p_left_vals)) / n)
    ax.fill_between(p_left_vals,
                    np.array(p_left_vals) - ci,
                    np.array(p_left_vals) + ci,
                    alpha=0.15, color="grey", label="±1.96σ")
    ax.set_xlabel("left_probability (requested)")
    ax.set_ylabel("Observed left fraction")
    ax.set_title("Weighted mode\nobserved vs requested", fontsize=9)
    ax.legend(fontsize=8)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)

    # Panel 2: Weighted mode — residuals (obs - expected)
    ax = fig.add_subplot(gs[2])
    residuals = [r["obs_frac"] - r["p_left"] for r in wgt]
    colors = ["#4e79a7" if r["p_val"] > 0.01 else "#e15759" for r in wgt]
    bars = ax.bar([f"{r['p_left']:.1f}" for r in wgt], residuals, color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    # ±1.96σ bands
    max_ci = 1.96 * np.sqrt(0.25 / n)
    ax.axhline( max_ci, color="grey", linewidth=0.8, linestyle="--", label=f"±1.96σ")
    ax.axhline(-max_ci, color="grey", linewidth=0.8, linestyle="--")
    ax.set_xlabel("left_probability")
    ax.set_ylabel("obs − expected")
    ax.set_title("Weighted mode residuals\n(blue=pass, red=fail)", fontsize=9)
    ax.legend(fontsize=8)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fig.savefig(args.out, dpi=150, bbox_inches="tight")
    print(f"\nPlot saved → {args.out}")
    plt.show()


if __name__ == "__main__":
    main()
