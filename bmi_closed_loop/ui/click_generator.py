"""
Poisson click train generator.

Generates independent left and right Poisson click trains
  - Each side is an independent Poisson process
  - Inter-click intervals are exponentially distributed: ICI ~ Exp(1/rate)
  - Difficulty is controlled by the ratio of left_rate to right_rate
  - Total rate (left_rate + right_rate)

Usage:
    from ui.click_generator import generate_clicks
    clicks = generate_clicks(left_rate=39, right_rate=9, duration=1.0)
    # clicks = {"left_clicks": [0.023, ...], "right_clicks": [0.045, ...]}
"""

import numpy as np


def generate_clicks(left_rate: float, right_rate: float, duration: float, seed: int = None,) -> dict:
    """
    Generate one trial's worth of Poisson click trains.
    Args:
        left_rate:  Mean click rate for the left channel (clicks/sec).
        right_rate: Mean click rate for the right channel (clicks/sec).
        duration:   Stimulus duration in seconds.
        seed:       Optional RNG seed for reproducibility.

    Returns:
        dict with keys:
            "left_clicks":  sorted list of click times in seconds
            "right_clicks": sorted list of click times in seconds
    """
    rng = np.random.default_rng(seed)
    return {
        "left_clicks":  _poisson_train(left_rate,  duration, rng),
        "right_clicks": _poisson_train(right_rate, duration, rng),
    }


def _poisson_train(rate: float, duration: float, rng: np.random.Generator) -> list:
    """Generate click times for one side as a Poisson process."""
    if rate <= 0:
        return []
    clicks = []
    t = 0.0
    while True:
        t += rng.exponential(1.0 / rate)
        if t >= duration:
            break
        clicks.append(round(float(t), 4))
    return clicks
