"""
Poisson click train distribution validator (sec:val_click_stats).

Generates N click trains using the production click_generator routine and
produces the thesis figure (fig:click_stats):
  Left panel  — log-y ICI histogram across rates with theoretical Exp overlaid;
                theoretical line dashed below the min_ici support boundary.
  Right panel — zoom on the first 20 ms showing the point mass at min_ici.

Also prints the KS test results and clamp fraction table for the thesis.

Runs anywhere (no hardware needed).

Usage:
    python debug/validate_clicks.py
    python debug/validate_clicks.py --n 2000 --dur 1.0
    python debug/validate_clicks.py --out output/click_stats.png
"""

import argparse
import os
import sys
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from ui.click_generator import generate_clicks, CLICK_WIDTH_S

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

MIN_ICI    = 2 * CLICK_WIDTH_S          # 6 ms — matches generate_clicks() default
TEST_RATES = [5, 10, 20, 40]             # per-channel click rates (clicks/s)
COLORS     = ["#4e79a7", "#f28e2b", "#e15759", "#59a14f"]


def collect_icis(rate: float, n_trains: int, duration: float) -> list[float]:
    """Generate n_trains via the production routine and return all ICIs (seconds)."""
    icis = []
    for seed in range(n_trains):
        result = generate_clicks(rate, rate, duration, seed=seed, min_ici=MIN_ICI)
        for channel in ("left_clicks", "right_clicks"):
            clicks = result[channel]
            for i in range(1, len(clicks)):
                icis.append(clicks[i] - clicks[i - 1])
    return icis


def validate_rate(rate: float, icis: list[float]) -> dict:
    """Compute KS test and clamp statistics for one rate."""
    ks_stat, ks_p = np.nan, np.nan
    clamp_tol = 1e-4

    n_clamped  = sum(1 for ici in icis if ici < MIN_ICI + clamp_tol)
    clamp_frac = n_clamped / len(icis) if icis else np.nan
    clamp_frac_theory = 1.0 - np.exp(-rate * MIN_ICI)

    # KS test on the unclamped (continuous) portion against Expon(loc=MIN_ICI, scale=1/rate)
    unclamped = [ici for ici in icis if ici >= MIN_ICI + clamp_tol]
    if len(unclamped) >= 10:
        ks_stat, ks_p = stats.kstest(
            unclamped, stats.expon(loc=MIN_ICI, scale=1.0 / rate).cdf
        )

    return {
        "rate":              rate,
        "n_icis":            len(icis),
        "ks_stat":           ks_stat,
        "ks_p":              ks_p,
        "clamp_frac":        clamp_frac,
        "clamp_frac_theory": clamp_frac_theory,
    }


def plot(results: dict, ici_data: dict, duration: float, n_trains: int,
         save_path: str) -> None:

    fig, (ax_main, ax_zoom) = plt.subplots(1, 2, figsize=(12, 5))

    x_max  = max(float(np.percentile(np.array(ici_data[r]), 99.5)) for r in TEST_RATES)
    x_full = np.linspace(0, x_max, 5000)
    x_zoom = np.linspace(0, 0.020, 2000)

    x_full_ms = x_full * 1000
    x_zoom_ms = x_zoom * 1000
    min_ici_ms = MIN_ICI * 1000

    for i, rate in enumerate(TEST_RATES):
        icis_ms = np.array(ici_data[rate]) * 1000
        color   = COLORS[i]
        r       = results[rate]

        # ── Main panel: log-y ICI density ────────────────────────────────────
        x_max_ms = float(np.percentile(icis_ms, 99.5))
        bins     = np.linspace(0, x_max_ms, 80)
        ax_main.hist(icis_ms, bins=bins, density=True, alpha=0.35, color=color,
                     edgecolor="none", label=f"{rate} Hz (D={r['ks_stat']:.4f})")

        # Theoretical Exp: solid for x >= min_ici, dashed for x < min_ici
        pdf = (rate / 1000) * np.exp(-(rate / 1000) * x_full_ms)
        ax_main.plot(x_full_ms[x_full_ms >= min_ici_ms], pdf[x_full_ms >= min_ici_ms],
                     color=color, lw=1.5)
        ax_main.plot(x_full_ms[x_full_ms <  min_ici_ms], pdf[x_full_ms <  min_ici_ms],
                     color=color, lw=1.0, linestyle="--")

    # Dummy lines for legend entries explaining line styles
    ax_main.plot([], [], color="gray", lw=1.5, label="Exp($\\lambda$) theoretical")
    ax_main.plot([], [], color="gray", lw=1.0, linestyle="--", label="Theoretical (below $\\Delta t_{\\min}$)")
    ax_main.axvline(min_ici_ms, color="black", lw=1.0, linestyle=":",
                    label=f"$\\Delta t_{{\\min}}$ = {min_ici_ms:.0f} ms")
    ax_main.set_yscale("log")
    ax_main.set_xlabel("Inter-click interval (ms)")
    ax_main.set_ylabel("Density (log scale)")
    ax_main.legend(fontsize=8, loc="upper right")
    ax_main.set_xlim(left=0)

    # ── Zoom panel: clamp boundary at max rate ────────────────────────────────
    max_rate  = TEST_RATES[-1]
    icis_max  = np.array(ici_data[max_rate]) * 1000
    zoom_ms   = 20
    zoom_bins = np.linspace(0, zoom_ms, 60)

    ax_zoom.hist(icis_max, bins=zoom_bins, density=True, color=COLORS[-1],
                 alpha=0.6, edgecolor="white", linewidth=0.3,
                 label=f"Observed ({max_rate} Hz)")

    pdf_zoom = (max_rate / 1000) * np.exp(-(max_rate / 1000) * x_zoom_ms)
    ax_zoom.plot(x_zoom_ms[x_zoom_ms >= min_ici_ms], pdf_zoom[x_zoom_ms >= min_ici_ms],
                 color="black", lw=1.8, label=f"Exp({max_rate} Hz)")
    ax_zoom.plot(x_zoom_ms[x_zoom_ms <  min_ici_ms], pdf_zoom[x_zoom_ms <  min_ici_ms],
                 color="black", lw=1.2, linestyle="--", label="Theoretical (below $\\Delta t_{\\min}$)")
    ax_zoom.axvline(min_ici_ms, color="black", lw=1.0, linestyle=":",
                    label=f"$\\Delta t_{{\\min}}$ = {min_ici_ms:.0f} ms")

    r_max = results[max_rate]
    ax_zoom.text(0.97, 0.97,
                 f"Clamp fraction:\n  observed: {r_max['clamp_frac']*100:.1f}%\n"
                 f"  $\\lambda \\cdot \\Delta t_{{\\min}}$:  {r_max['clamp_frac_theory']*100:.1f}%",
                 transform=ax_zoom.transAxes, ha="right", va="top", fontsize=8,
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    ax_zoom.set_xlabel("Inter-click interval (ms)")
    ax_zoom.set_ylabel("Density")
    ax_zoom.set_xlim(0, zoom_ms)
    ax_zoom.legend(fontsize=8)

    fig.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Plot saved → {save_path}")
    plt.show()


def main() -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = os.path.join(OUTPUT_DIR, f"validate_clicks_{ts}.png")

    p = argparse.ArgumentParser(description="Poisson click distribution validator")
    p.add_argument("--n",   type=int,   default=2000, help="Trains per rate (default: 2000)")
    p.add_argument("--dur", type=float, default=1.0,  help="Train duration s (default: 1.0)")
    p.add_argument("--out", default=default_out,      help="Output PNG path")
    args = p.parse_args()

    print(f"Generating {len(TEST_RATES)} rates × {args.n} trains × {args.dur:.1f} s "
          f"(min_ici={MIN_ICI*1000:.0f} ms) ...")

    ici_data = {}
    for rate in TEST_RATES:
        ici_data[rate] = collect_icis(rate, args.n, args.dur)
        print(f"  {rate:3.0f} Hz: {len(ici_data[rate]):,} ICIs collected")

    results = {rate: validate_rate(rate, ici_data[rate]) for rate in TEST_RATES}

    # Terminal table
    print(f"\n{'Rate':>6}  {'N ICIs':>8}  {'KS D':>8}  {'KS p':>8}  "
          f"{'Clamp % obs':>12}  {'Clamp % theory (λΔt)':>20}")
    print("─" * 75)
    for rate in TEST_RATES:
        r = results[rate]
        print(f"  {rate:4.0f}  {r['n_icis']:8,}  {r['ks_stat']:8.4f}  {r['ks_p']:8.4f}  "
              f"{r['clamp_frac']*100:11.2f}%  {r['clamp_frac_theory']*100:19.2f}%")

    plot(results, ici_data, args.dur, args.n, args.out)


if __name__ == "__main__":
    main()
