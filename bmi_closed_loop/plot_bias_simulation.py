#!/usr/bin/env python3
"""
Side-bias correction algorithm simulator.

Simulates a biased animal and shows how Brody / IBL algorithms respond.

Simple mode (--rat-model simple):
    Animal is a fixed coin flip with probability `--bias` of choosing left.

GLM-based modes (--rat-model glm | hmm | learn):
    Animal is a SimulatedRat (GLM + optional HMM + optional Kalman learning)
    from Ashwood et al. 2022 / Roy et al. 2021. --w-bias sets initial logit bias,
    --w-stim sets stimulus sensitivity, --lapse sets lapse rate.

Usage:
    python plot_bias_simulation.py                               # simple, 70% left, 200 trials
    python plot_bias_simulation.py --bias 0.8                   # simple: 80% left fixed bias
    python plot_bias_simulation.py --rat-model glm --w-bias 1.5 --trials 1000 --alg both
    python plot_bias_simulation.py --rat-model hmm --w-bias 1.5 --trials 1000 --seeds 5
    python plot_bias_simulation.py --rat-model learn --w-stim 0.5 --trials 3000
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
# SimulatedRat — GLM + HMM + learning (Ashwood 2022 / Roy 2021)
# ---------------------------------------------------------------------------

class SimulatedRat:
    """
    Generative rat for a Poisson-click 2AFC task.

    choose(rclicks, lclicks) -> 'left' | 'right'
    update(correct_side, outcome)  -> None   (called by rig/simulator after each trial)

    rat_model controls which features are active:
        'glm'   — static GLM weights only (no HMM, no learning)
        'hmm'   — 3-state GLM-HMM (engaged / bias-left / bias-right)
        'learn' — 3-state HMM + Kalman weight drift toward asymptote
    """

    def __init__(self,
                 w_stim=4.0,
                 w_bias=0.0,
                 w_prevchoice=0.10,
                 w_wsls=0.30,
                 lapse=0.04,
                 use_hmm=False,
                 p_stay_engaged=0.98,
                 p_stay_biased=0.95,
                 p_engaged_init=0.85,
                 bias_state_offset=2.5,
                 bias_state_w_stim=0.6,
                 learn=False,
                 learn_mode='kalman',
                 lr=0.01,
                 sigma_walk=0.005,
                 sigma_bias_walk=0.01,
                 asymptote_w_stim=4.0,
                 seed=None):

        seed_int = seed if seed is not None else random.randrange(2**31)
        self._rng = np.random.default_rng(seed_int)

        self.lapse = lapse
        self.use_hmm = use_hmm
        self.learn = learn
        self.learn_mode = learn_mode
        self.lr = lr
        self.sigma_walk = sigma_walk
        self.sigma_bias_walk = sigma_bias_walk
        self.asymptote_w_stim = asymptote_w_stim

        # Engaged-state weights (also the sole weights when use_hmm=False)
        self.w = dict(stim=w_stim, bias=w_bias, prev=w_prevchoice, wsls=w_wsls)

        # 3-state HMM: 0=engaged, 1=bias-left, 2=bias-right
        A_raw = np.array([
            [p_stay_engaged, (1 - p_stay_engaged) / 2, (1 - p_stay_engaged) / 2],
            [1 - p_stay_biased, p_stay_biased, 0.0],
            [1 - p_stay_biased, 0.0, p_stay_biased],
        ])
        self.A = A_raw / A_raw.sum(axis=1, keepdims=True)

        self.state_w = [
            dict(stim=w_stim, bias=w_bias, prev=w_prevchoice, wsls=w_wsls),
            dict(stim=bias_state_w_stim, bias=-bias_state_offset, prev=0.0, wsls=0.0),
            dict(stim=bias_state_w_stim, bias=+bias_state_offset, prev=0.0, wsls=0.0),
        ]
        self.state = self._rng.choice(
            3, p=[p_engaged_init, (1 - p_engaged_init) / 2, (1 - p_engaged_init) / 2])

        self.prev_choice = 0
        self.prev_reward = 0
        self._last_x = None
        self._last_logit = None
        self._last_choice = 0

    def _features(self, rclicks, lclicks):
        delta = len(rclicks) - len(lclicks)
        delta_noisy = delta + self._rng.normal(0, 0.5 * np.sqrt(max(1, abs(delta))))
        return dict(stim=delta_noisy, bias=1.0,
                    prev=self.prev_choice,
                    wsls=self.prev_choice * self.prev_reward)

    @staticmethod
    def _logit(x, w):
        return w['stim'] * x['stim'] + w['bias'] * x['bias'] + w['prev'] * x['prev'] + w['wsls'] * x['wsls']

    def choose(self, rclicks, lclicks):
        """rclicks, lclicks: sequences (only length matters). Returns 'left'|'right'."""
        if self.use_hmm:
            self.state = self._rng.choice(3, p=self.A[self.state])
            wk = self.state_w[self.state]
        else:
            wk = self.w

        x = self._features(rclicks, lclicks)
        logit = self._logit(x, wk)
        p_right = 1 / (1 + np.exp(-logit))
        p_right = (1 - self.lapse) * p_right + self.lapse * 0.5

        choice = 'right' if self._rng.random() < p_right else 'left'
        self._last_x = x
        self._last_logit = logit
        self._last_choice = +1 if choice == 'right' else -1
        return choice

    def update(self, correct_side, outcome):
        """Called by the simulator after each trial."""
        self.prev_choice = self._last_choice
        self.prev_reward = int(outcome == 'correct')

        if not self.learn:
            return

        x = self._last_x
        y = 1.0 if correct_side == 'right' else 0.0

        if self.learn_mode == 'sgd':
            p = 1 / (1 + np.exp(-self._last_logit))
            err = y - p
            for k in ('stim', 'bias', 'prev', 'wsls'):
                self.state_w[0][k] += self.lr * err * x[k]
            self.w = dict(self.state_w[0])

        elif self.learn_mode == 'kalman':
            drift = 0.0002 * (self.asymptote_w_stim - self.state_w[0]['stim'])
            self.state_w[0]['stim'] += drift + self._rng.normal(0, self.sigma_walk)
            self.state_w[0]['bias'] += self._rng.normal(0, self.sigma_bias_walk)
            self.state_w[0]['prev'] += self._rng.normal(0, self.sigma_walk)
            self.state_w[0]['wsls'] += self._rng.normal(0, self.sigma_walk)
            self.w = dict(self.state_w[0])


def _generate_click_counts(correct_side, rng, high_rate=20, low_rate=5, duration=0.5):
    """
    Sample Poisson click counts for one trial.  Only counts matter to SimulatedRat,
    so timing is not generated.  Returns (n_right, n_left).
    """
    if correct_side == 'right':
        n_right = rng.poisson(high_rate * duration)
        n_left  = rng.poisson(low_rate  * duration)
    else:
        n_right = rng.poisson(low_rate  * duration)
        n_left  = rng.poisson(high_rate * duration)
    return int(n_right), int(n_left)


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


def ibl_left_prob(history: list[dict], easy_min_ratio: float | None = None) -> float | None:
    """
    Return P(next correct_side = left) using IBL debias, or None if not triggered.

    Triggers only when both conditions hold:
      1. The most recent trial was wrong.
      2. That trial was "easy": high_clicks / low_clicks >= easy_min_ratio.
         e.g. easy_min_ratio=2.0 means the winning side had at least twice as many
         clicks — a 30:10 trial (ratio 3.0) qualifies; a 13:11 trial (ratio 1.18) does not.
         If easy_min_ratio is None, or the trial has no click_ratio recorded,
         the difficulty condition is skipped (backward-compatible).
    """
    responded = [t for t in history if t["outcome"] != "aborted"]
    if not responded or responded[-1]["outcome"] != "wrong":
        return None

    # Difficulty guard: only act on errors where the answer was unambiguous.
    if easy_min_ratio is not None:
        ratio = responded[-1].get("click_ratio")
        if ratio is not None and ratio < easy_min_ratio:
            return None   # hard trial — failure is expected noise, not bias evidence

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
# Simulation — simple (fixed-bias coin flip)
# ---------------------------------------------------------------------------

def simulate(n_trials: int, animal_left_bias: float, alg: str, seed: int = 42,
             easy_min_ratio: float | None = None) -> dict:
    """
    Simple simulation: animal is a fixed-bias coin flip.

    animal_left_bias: probability animal actually chooses left (0.7 = biased)
    alg: 'brody', 'ibl', or 'none'
    easy_min_ratio: IBL difficulty threshold (no click info in simple mode,
                    so this has no effect here — kept for API consistency)
    """
    rng = random.Random(seed)
    history = []

    left_probs     = []
    correct_sides  = []
    animal_choices = []
    outcomes       = []
    ibl_triggered  = []

    for _ in range(n_trials):
        if alg == "brody":
            p_left = brody_left_prob(history)
        elif alg == "ibl":
            # click_ratio is None in simple mode → difficulty guard is skipped
            nudge = ibl_left_prob(history, easy_min_ratio=easy_min_ratio)
            p_left = nudge if nudge is not None else 0.5
            ibl_triggered.append(nudge is not None)
        else:
            p_left = 0.5

        left_probs.append(p_left)

        correct_side = "left" if rng.random() < p_left else "right"
        correct_sides.append(correct_side)

        animal_choice = "left" if rng.random() < animal_left_bias else "right"
        animal_choices.append(animal_choice)

        outcome = "correct" if animal_choice == correct_side else "wrong"
        outcomes.append(outcome)

        # click_ratio=None: simple model has no click information
        history.append({"correct_side": correct_side, "outcome": outcome, "click_ratio": None})

    return {
        "left_probs":     np.array(left_probs),
        "correct_sides":  correct_sides,
        "animal_choices": animal_choices,
        "outcomes":       outcomes,
        "ibl_triggered":  ibl_triggered,
        "stim_weights":   None,
    }


# ---------------------------------------------------------------------------
# Simulation — GLM-based (SimulatedRat)
# ---------------------------------------------------------------------------

def simulate_glm(n_trials: int, alg: str, rat_params: dict, seed: int = 42,
                 easy_min_ratio: float | None = None) -> dict:
    """
    GLM-based simulation: animal is a SimulatedRat.

    rat_params: kwargs forwarded to SimulatedRat.__init__
    easy_min_ratio: IBL only fires when high_clicks / low_clicks >= this value.
                    None = no difficulty filter (fires on any wrong trial).
                    e.g. 2.0 means the winning side needs ≥2× the clicks of the losing side.
    """
    rng_alg = random.Random(seed)
    rng_clicks = np.random.default_rng(seed + 1)
    rat = SimulatedRat(seed=seed + 2, **rat_params)

    history = []

    left_probs     = []
    correct_sides  = []
    animal_choices = []
    outcomes       = []
    ibl_triggered  = []
    stim_weights   = []

    for _ in range(n_trials):
        if alg == "brody":
            p_left = brody_left_prob(history)
        elif alg == "ibl":
            nudge = ibl_left_prob(history, easy_min_ratio=easy_min_ratio)
            p_left = nudge if nudge is not None else 0.5
            ibl_triggered.append(nudge is not None)
        else:
            p_left = 0.5

        left_probs.append(p_left)

        correct_side = "left" if rng_alg.random() < p_left else "right"
        correct_sides.append(correct_side)

        n_right, n_left = _generate_click_counts(correct_side, rng_clicks)
        choice = rat.choose(list(range(n_right)), list(range(n_left)))
        animal_choices.append(choice)

        outcome = "correct" if choice == correct_side else "wrong"
        outcomes.append(outcome)

        rat.update(correct_side, outcome)
        n_hi, n_lo = (n_right, n_left) if n_right >= n_left else (n_left, n_right)
        history.append({
            "correct_side": correct_side,
            "outcome":      outcome,
            "click_ratio":  n_hi / max(n_lo, 1),   # high / low click count ratio
        })

        stim_weights.append(rat.w['stim'])

    return {
        "left_probs":     np.array(left_probs),
        "correct_sides":  correct_sides,
        "animal_choices": animal_choices,
        "outcomes":       outcomes,
        "ibl_triggered":  ibl_triggered,
        "stim_weights":   np.array(stim_weights),
    }


def simulate_multi(n_trials: int, alg: str, rat_params: dict, n_seeds: int,
                   easy_min_ratio: float | None = None) -> dict:
    """
    Run simulate_glm over n_seeds seeds and return mean ± std per-trial arrays.
    """
    all_left_probs     = []
    all_choices_left   = []
    all_correct        = []
    all_stim_weights   = []

    for s in range(n_seeds):
        r = simulate_glm(n_trials, alg, rat_params, seed=s * 137, easy_min_ratio=easy_min_ratio)
        all_left_probs.append(r["left_probs"])
        all_choices_left.append(
            np.array([1 if c == "left" else 0 for c in r["animal_choices"]], dtype=float)
        )
        all_correct.append(
            np.array([1 if o == "correct" else 0 for o in r["outcomes"]], dtype=float)
        )
        if r["stim_weights"] is not None:
            all_stim_weights.append(r["stim_weights"])

    def ms(lst):
        a = np.stack(lst)
        return a.mean(axis=0), a.std(axis=0)

    mean_lp, std_lp = ms(all_left_probs)
    mean_cl, std_cl = ms(all_choices_left)
    mean_co, std_co = ms(all_correct)
    mean_sw, std_sw = ms(all_stim_weights) if all_stim_weights else (None, None)

    # Return a synthetic single-run dict augmented with std arrays
    first = simulate_glm(n_trials, alg, rat_params, seed=0, easy_min_ratio=easy_min_ratio)
    first["left_probs"]   = mean_lp
    first["_std_lp"]      = std_lp
    first["_choices_left"]= mean_cl
    first["_std_cl"]      = std_cl
    first["_correct"]     = mean_co
    first["_std_co"]      = std_co
    first["_stim_w_mean"] = mean_sw
    first["_stim_w_std"]  = std_sw
    return first


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rolling_mean(arr, window: int) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        out[i] = np.mean(arr[i - window + 1 : i + 1])
    return out


def rolling_arr(arr, window: int) -> np.ndarray:
    """Rolling mean of a pre-computed per-trial array."""
    return rolling_mean(arr, window)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot(results: dict[str, dict], animal_bias: float | None, n_trials: int,
         save: str | None, rat_model: str = "simple"):

    algs  = list(results.keys())
    n_alg = len(algs)
    show_stim = rat_model == "learn"
    n_cols = 3 if show_stim else 2
    fig   = plt.figure(figsize=(6 * n_cols, 4 * n_alg + 1))

    bias_label = (f"animal P(left)={animal_bias:.0%}" if rat_model == "simple"
                  else f"rat-model={rat_model}")
    fig.suptitle(f"Side-bias simulation — {bias_label}, {n_trials} trials",
                 fontsize=13, fontweight="bold")

    gs = gridspec.GridSpec(n_alg, n_cols, figure=fig, wspace=0.35, hspace=0.55)

    for row, alg in enumerate(algs):
        r      = results[alg]
        trials = np.arange(1, n_trials + 1)

        # Derive per-trial binary arrays (multi-seed path stores pre-computed means)
        if "_choices_left" in r:
            choices_left = r["_choices_left"]
            correct_arr  = r["_correct"]
            std_cl       = r.get("_std_cl")
            std_co       = r.get("_std_co")
        else:
            choices_left = np.array([1 if c == "left" else 0 for c in r["animal_choices"]], dtype=float)
            correct_arr  = np.array([1 if o == "correct" else 0 for o in r["outcomes"]], dtype=float)
            std_cl = std_co = None

        roll_choice = rolling_arr(choices_left, WINDOW)
        roll_corr   = rolling_arr(correct_arr,  WINDOW)

        # ── Left panel: side allocation ───────────────────────────────────
        ax1 = fig.add_subplot(gs[row, 0])
        ax1.plot(trials, r["left_probs"], color="steelblue", lw=1.2, alpha=0.8,
                 label="P(correct=left) set by alg")
        ax1.plot(trials, roll_choice, color="tomato", lw=1.5,
                 label=f"Animal left-choice rate (rolling {WINDOW})")
        if std_cl is not None:
            rc_mean = rolling_arr(r["_choices_left"], WINDOW)
            rc_std  = rolling_arr(r["_std_cl"], WINDOW)
            ax1.fill_between(trials, rc_mean - rc_std, rc_mean + rc_std,
                             color="tomato", alpha=0.18)

        if rat_model == "simple" and animal_bias is not None:
            ax1.axhline(animal_bias, color="tomato", lw=0.8, ls="--", alpha=0.5,
                        label=f"True animal bias ({animal_bias:.0%})")
        ax1.axhline(0.5, color="gray", lw=0.6, ls=":")

        if alg == "ibl" and r.get("ibl_triggered"):
            trig_x = [i + 1 for i, t in enumerate(r["ibl_triggered"]) if t]
            ax1.scatter(trig_x, [r["left_probs"][i - 1] for i in trig_x],
                        marker="|", color="orange", s=40, zorder=3, label="IBL triggered")
        ax1.set_ylim(0, 1)
        ax1.set_xlabel("Trial")
        ax1.set_ylabel("Probability")
        ax1.set_title(f"{alg.upper()} — side allocation")
        ax1.legend(fontsize=7, loc="upper right")

        # ── Middle panel: rolling accuracy ────────────────────────────────
        ax2 = fig.add_subplot(gs[row, 1])
        ax2.plot(trials, roll_corr, color="seagreen", lw=1.5,
                 label=f"Rolling accuracy (window {WINDOW})")
        if std_co is not None:
            rc_mean = rolling_arr(r["_correct"], WINDOW)
            rc_std  = rolling_arr(r["_std_co"], WINDOW)
            ax2.fill_between(trials, rc_mean - rc_std, rc_mean + rc_std,
                             color="seagreen", alpha=0.18)
        ax2.axhline(0.5, color="gray", lw=0.6, ls=":", label="Chance")
        ax2.set_ylim(0, 1)
        ax2.set_xlabel("Trial")
        ax2.set_ylabel("Fraction correct")
        ax2.set_title(f"{alg.upper()} — accuracy")
        ax2.legend(fontsize=7, loc="upper right")

        # ── Right panel: stimulus weight (learn mode only) ────────────────
        if show_stim:
            ax3 = fig.add_subplot(gs[row, 2])
            sw_mean = r.get("_stim_w_mean") if "_stim_w_mean" in r else r.get("stim_weights")
            sw_std  = r.get("_stim_w_std")
            if sw_mean is not None:
                ax3.plot(trials, sw_mean, color="purple", lw=1.5, label="w_stim (engaged)")
                if sw_std is not None:
                    ax3.fill_between(trials, sw_mean - sw_std, sw_mean + sw_std,
                                     color="purple", alpha=0.18)
            ax3.set_xlabel("Trial")
            ax3.set_ylabel("w_stim (logit/click)")
            ax3.set_title(f"{alg.upper()} — stimulus weight")
            ax3.legend(fontsize=7)

    fig.set_constrained_layout(True)
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

    # Simple-mode flags
    parser.add_argument("--bias",   type=float, default=0.7,
                        help="[simple] Animal's true P(choose left), e.g. 0.7")

    # Shared flags
    parser.add_argument("--trials", type=int,   default=200,
                        help="Number of trials to simulate")
    parser.add_argument("--alg",    choices=["brody", "ibl", "both", "none"], default="both",
                        help="Which algorithm(s) to show")
    parser.add_argument("--save",   type=str,   default=None,
                        help="Save figure to this path instead of showing")
    parser.add_argument("--seed",   type=int,   default=42)

    # GLM-mode flags
    parser.add_argument("--rat-model", choices=["simple", "glm", "hmm", "learn"],
                        default="simple",
                        help="Animal model: simple (fixed bias), glm, hmm, or learn")
    parser.add_argument("--w-bias",  type=float, default=1.5,
                        help="[glm/hmm/learn] Initial bias weight in logit units (>0 = right bias)")
    parser.add_argument("--w-stim",  type=float, default=None,
                        help="[glm/hmm/learn] Stimulus weight (default: 4.0; 0.5 for learn)")
    parser.add_argument("--lapse",   type=float, default=0.04,
                        help="[glm/hmm/learn] Lapse rate (default 0.04)")
    parser.add_argument("--seeds",   type=int,   default=1,
                        help="[glm/hmm/learn] Number of seeds to average (1 = single run)")
    parser.add_argument("--ibl-easy-ratio", type=float, default=None,
                        dest="ibl_easy_ratio",
                        help="[ibl] IBL only fires when high_clicks / low_clicks >= this ratio. "
                             "e.g. 2.0 means the correct side needs ≥2× the clicks of the wrong side "
                             "(a 30:10 trial has ratio 3.0 and qualifies; a 13:11 trial has ratio 1.18 "
                             "and does not). None = fire on any wrong trial (original behaviour).")

    args = parser.parse_args()

    algs_to_run = ["brody", "ibl"] if args.alg == "both" else [args.alg]

    if args.rat_model == "simple":
        results = {
            alg: simulate(args.trials, args.bias, alg, seed=args.seed,
                          easy_min_ratio=args.ibl_easy_ratio)
            for alg in algs_to_run
        }
        plot(results, args.bias, args.trials, args.save, rat_model="simple")

    else:
        w_stim = args.w_stim if args.w_stim is not None else (0.5 if args.rat_model == "learn" else 4.0)

        rat_params = dict(
            w_stim=w_stim,
            w_bias=args.w_bias,
            lapse=args.lapse,
            use_hmm=(args.rat_model in ("hmm", "learn")),
            learn=(args.rat_model == "learn"),
        )

        if args.seeds > 1:
            results = {
                alg: simulate_multi(args.trials, alg, rat_params, args.seeds,
                                    easy_min_ratio=args.ibl_easy_ratio)
                for alg in algs_to_run
            }
        else:
            results = {
                alg: simulate_glm(args.trials, alg, rat_params, seed=args.seed,
                                  easy_min_ratio=args.ibl_easy_ratio)
                for alg in algs_to_run
            }

        plot(results, None, args.trials, args.save, rat_model=args.rat_model)


if __name__ == "__main__":
    main()
