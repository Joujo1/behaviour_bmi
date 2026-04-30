"""
Poisson click train generator.

Generates independent left and right Poisson click trains
  - Inter-click intervals are exponentially distributed: ICI ~ Exp(1/rate)
  - Difficulty is controlled by the ratio of left_rate to right_rate
  - min_ici (default: click width = 3 ms) prevents clicks from overlapping
    in the audio buffer and distorting each other via waveform addition.
    Clicks drawn closer than min_ici are dropped (rejection thinning);
    only timestamps that will actually be rendered are returned.
"""

import numpy as np

import config

CLICK_WIDTH_S = config.CLICK_WIDTH_S


def generate_clicks(left_rate: float, right_rate: float, duration: float,
                    seed: int = None,
                    min_ici: float = CLICK_WIDTH_S) -> dict:
    """
    Args:
        left_rate:  Mean click rate for the left channel (clicks/sec).
        right_rate: Mean click rate for the right channel (clicks/sec).
        duration:   Stimulus duration in seconds.
        seed:       Optional RNG seed for reproducibility.
        min_ici:    Minimum inter-click interval in seconds.  Defaults to the
                    click width (3 ms) so no two clicks overlap in the audio
                    buffer.  Pass 0.0 to disable.

    Returns:
        dict with keys:
            "left_clicks":  sorted list of click times (seconds) that will be rendered
            "right_clicks": sorted list of click times (seconds) that will be rendered
    """
    rng = np.random.default_rng(seed)
    return {
        "left_clicks":  _poisson_train(left_rate,  duration, rng, min_ici),
        "right_clicks": _poisson_train(right_rate, duration, rng, min_ici),
    }


def _poisson_train(rate: float, duration: float, rng: np.random.Generator,
                   min_ici: float) -> list:
    if rate <= 0:
        return []
    clicks = []
    t = 0.0
    last_t = -np.inf
    while True:
        t += rng.exponential(1.0 / rate)
        t = max(t, last_t + min_ici)   # shift forward if too close — never drop
        if t >= duration:
            break
        clicks.append(round(float(t), 4))
        last_t = t
    return clicks
