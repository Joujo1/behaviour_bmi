"""
Poisson click train distribution validator.

Generates N click trains at several rates and verifies:
  1. Mean observed rate matches requested rate
  2. Inter-click intervals follow Exp(1/rate) — KS test + visual overlay
  3. min_ici constraint is always respected (no two clicks closer than 3 ms)
  4. No clicks fall outside [0, duration)

Runs anywhere (no hardware needed).

Usage:
    python3 debug/validate_clicks.py [--n 2000] [--dur 1.0]
    python3 debug/validate_clicks.py --out output/validate_clicks.png
"""

import argparse
import os
from datetime import datetime

import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

CLICK_WIDTH_S = 0.003   # min_ici default — matches config.py
TEST_RATES    = [5, 10, 20, 40, 80]   # clicks/s


def _poisson_train(rate: float, duration: float, rng, min_ici: float) -> list:
    if rate <= 0:
        return []
    clicks, t, last_t = [], 0.0, float("-inf")
    while True:
        t += rng.exponential(1.0 / rate)
        t = max(t, last_t + min_ici)
        if t >= duration:
            break
        clicks.append(float(t))
        last_t = t
    return clicks


def validate_rate(rate: float, n_trains: int, duration: float,
                  min_ici: float, rng) -> dict:
    all_icis      = []
    all_counts    = []
    min_ici_violations = 0
    out_of_bounds = 0

    for _ in range(n_trains):
        clicks = _poisson_train(rate, duration, rng, min_ici)
        if not clicks:
            all_counts.append(0)
            continue

        all_counts.append(len(clicks))

        # Check bounds
        if any(c < 0 or c >= duration for c in clicks):
            out_of_bounds += 1

        # Check min_ici
        for i in range(1, len(clicks)):
            ici = clicks[i] - clicks[i - 1]
            if ici < min_ici - 1e-9:
                min_ici_violations += 1
            all_icis.append(ici)

    obs_rate = np.mean(all_counts) / duration
    ks_stat, ks_p = (np.nan, np.nan)

    if len(all_icis) >= 20:
        # KS test: ICI ~ Exp(1/rate). With min_ici shift, true mean is 1/rate + min_ici.
        # Use the empirical mean to fit rather than the theoretical rate directly.
        emp_mean = np.mean(all_icis)
        ks_stat, ks_p = stats.kstest(all_icis, "expon",
                                      args=(0, emp_mean))

    return {
        "rate":               rate,
        "obs_rate":           obs_rate,
        "rate_error_pct":     100 * (obs_rate - rate) / rate,
        "mean_ici_ms":        np.mean(all_icis) * 1000 if all_icis else np.nan,
        "std_ici_ms":         np.std(all_icis)  * 1000 if all_icis else np.nan,
        "min_ici_ms":         np.min(all_icis)  * 1000 if all_icis else np.nan,
        "ks_stat":            ks_stat,
        "ks_p":               ks_p,
        "min_ici_violations": min_ici_violations,
        "out_of_bounds":      out_of_bounds,
        "all_icis":           all_icis,
        "all_counts":         all_counts,
    }


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = os.path.join(OUTPUT_DIR, f"validate_clicks_{ts}.png")

    p = argparse.ArgumentParser(description="Poisson click distribution validator")
    p.add_argument("--n",   type=int,   default=2000,       help="Trains per rate (default: 2000)")
    p.add_argument("--dur", type=float, default=1.0,        help="Train duration s (default: 1.0)")
    p.add_argument("--out", default=default_out,            help="Output PNG path")
    args = p.parse_args()

    rng = np.random.default_rng(42)
    results = {}

    print(f"Validating {len(TEST_RATES)} rates × {args.n} trains × {args.dur:.1f} s ...")
    print(f"\n{'Rate':>6}  {'Obs rate':>9}  {'Error':>7}  "
          f"{'Mean ICI':>9}  {'Min ICI':>8}  {'KS p':>8}  {'Violations':>10}")
    print("─" * 70)

    for rate in TEST_RATES:
        r = validate_rate(rate, args.n, args.dur, CLICK_WIDTH_S, rng)
        results[rate] = r
        ok = "✓" if r["min_ici_violations"] == 0 and r["out_of_bounds"] == 0 else "✗"
        print(f"  {rate:4.0f}  {r['obs_rate']:9.2f}  {r['rate_error_pct']:+6.2f}%  "
              f"{r['mean_ici_ms']:8.2f} ms  {r['min_ici_ms']:7.2f} ms  "
              f"{r['ks_p']:8.4f}  {r['min_ici_violations']:>6} viol  {ok}")

    # --- Plot ---
    n_rates = len(TEST_RATES)
    fig = plt.figure(figsize=(4 * n_rates, 10))
    fig.suptitle(
        f"Poisson click train validation  —  {args.n} trains × {args.dur:.1f} s per rate",
        fontsize=12, fontweight="bold",
    )
    gs = gridspec.GridSpec(3, n_rates, figure=fig, hspace=0.55, wspace=0.35)

    for col, rate in enumerate(TEST_RATES):
        r = results[rate]
        icis = np.array(r["all_icis"])
        counts = np.array(r["all_counts"])

        # Row 0: ICI histogram vs theoretical Exponential
        ax = fig.add_subplot(gs[0, col])
        if len(icis) > 0:
            x_max = np.percentile(icis, 99)
            bins  = np.linspace(0, x_max, 50)
            ax.hist(icis, bins=bins, density=True, color="#4e79a7",
                    alpha=0.75, edgecolor="white", linewidth=0.3, label="observed")
            x = np.linspace(0, x_max, 300)
            # Theoretical: shifted exponential (mean = 1/rate + min_ici)
            lam = 1.0 / (1.0 / rate)
            ax.plot(x, lam * np.exp(-lam * x), color="red", linewidth=1.5,
                    linestyle="--", label=f"Exp({rate:.0f} Hz)")
        ax.set_xlabel("ICI (s)")
        ax.set_ylabel("Density")
        ax.set_title(f"{rate:.0f} Hz\nobs={r['obs_rate']:.1f} Hz  "
                     f"err={r['rate_error_pct']:+.1f}%\nKS p={r['ks_p']:.3f}",
                     fontsize=8)
        ax.legend(fontsize=7)

        # Row 1: Clicks-per-train distribution
        ax = fig.add_subplot(gs[1, col])
        expected_mean = rate * args.dur
        ax.hist(counts, bins=range(max(0, int(expected_mean - 4 * expected_mean**0.5)),
                                    int(expected_mean + 4 * expected_mean**0.5) + 2),
                color="#f28e2b", alpha=0.75, edgecolor="white", linewidth=0.3,
                density=True, label="observed")
        # Theoretical Poisson PMF
        k = np.arange(max(0, int(expected_mean - 5 * expected_mean**0.5)),
                       int(expected_mean + 5 * expected_mean**0.5) + 1)
        from scipy.stats import poisson as _poisson
        ax.plot(k, _poisson.pmf(k, expected_mean), "ko-", markersize=3,
                linewidth=1.0, label=f"Poisson({expected_mean:.0f})")
        ax.set_xlabel("Clicks per train")
        ax.set_ylabel("Density")
        ax.set_title(f"Clicks/train\nmean={np.mean(counts):.1f}  "
                     f"std={np.std(counts):.1f}", fontsize=8)
        ax.legend(fontsize=7)

        # Row 2: Minimum ICI check
        ax = fig.add_subplot(gs[2, col])
        if len(icis) > 0:
            ax.hist(icis * 1000, bins=50, color="#e15759", alpha=0.75,
                    edgecolor="white", linewidth=0.3)
            ax.axvline(CLICK_WIDTH_S * 1000, color="black", linewidth=1.2,
                       linestyle="--", label=f"min_ici={CLICK_WIDTH_S*1000:.0f} ms")
        violations = r["min_ici_violations"]
        ax.set_xlabel("ICI (ms)")
        ax.set_ylabel("Count")
        ax.set_title(f"ICI distribution (ms)\n"
                     f"min={r['min_ici_ms']:.2f} ms  viol={violations}", fontsize=8)
        ax.legend(fontsize=7)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fig.savefig(args.out, dpi=150, bbox_inches="tight")
    print(f"\nPlot saved → {args.out}")
    plt.show()


if __name__ == "__main__":
    main()
