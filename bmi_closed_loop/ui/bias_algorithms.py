"""
Side-bias correction algorithm registry.

To add a new algorithm:
  1. Write a function with the signature below and add it to this file.
  2. Register it in REGISTRY at the bottom of this file.
  3. Run a schema migration to drop the old CHECK constraint if it still exists
     (see bmi_closed_loop/db/schema.sql — the migration is already included).

Algorithm function signature::

    def my_alg(
        recent: list[dict],
        trial_def: dict,
        last_click_ratio: float | None,
    ) -> float | None:

Args:
    recent: Recent trials, most-recent first, up to ``window`` entries.
        Each dict has keys ``correct_side`` ("left"|"right"|None) and
        ``outcome`` ("correct"|"wrong").
    trial_def: The full trial definition dict for the upcoming trial.
        Read-only — do not mutate.
    last_click_ratio: high_clicks / low_clicks of the most recently
        completed trial, or None if not available.

Returns:
    A ``left_probability`` in [0, 1], or None to leave the trial
    definition unchanged (no bias correction this trial).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

AlgorithmFn = Callable[[list[dict], dict, float | None], float | None]


@dataclass(frozen=True)
class AlgorithmSpec:
    """Metadata and implementation for one bias correction algorithm."""

    label: str       # Human-readable name shown in the UI dropdown
    fn: AlgorithmFn  # The algorithm function (see module docstring for signature)
    window: int      # Number of recent trials to query from the database


def _brody(recent: list[dict], trial_def: dict,
           last_click_ratio: float | None) -> float | None:
    """Performance-equalisation: push more trials to the side the animal finds harder.

    Computes fraction-correct separately for left and right trials, then sets
    P(left) = fc_right / (fc_left + fc_right).  Returns None when there are not
    enough trials on both sides to compute the ratio.
    """
    left_hits  = [t["outcome"] == "correct" for t in recent if t["correct_side"] == "left"]
    right_hits = [t["outcome"] == "correct" for t in recent if t["correct_side"] == "right"]
    if not left_hits or not right_hits:
        return None
    fc_l  = sum(left_hits)  / len(left_hits)
    fc_r  = sum(right_hits) / len(right_hits)
    total = fc_l + fc_r
    left_prob = (fc_r / total) if total > 0 else 0.5
    logger.info("Brody bias: fc_l=%.2f fc_r=%.2f → P(left)=%.2f", fc_l, fc_r, left_prob)
    return left_prob


def _ibl(recent: list[dict], trial_def: dict,
         last_click_ratio: float | None) -> float | None:
    """Layup on preferred side: after a wrong trial, present the side the animal prefers.

    Only triggers when the last trial was wrong.  An optional easy-trial gate
    (key ``ibl_easy_min_ratio`` in trial_def) skips the correction when the last
    trial's click ratio was below the threshold (ambiguous stimulus).
    """
    if not recent or recent[0]["outcome"] != "wrong":
        return None

    easy_min_ratio = trial_def.get("ibl_easy_min_ratio", 2.5)
    if (easy_min_ratio is not None
            and last_click_ratio is not None
            and last_click_ratio < easy_min_ratio):
        logger.debug("IBL debias skipped: last trial ratio %.2f < threshold %.2f",
                     last_click_ratio, easy_min_ratio)
        return None

    responded = []
    for t in recent:
        cs = t["correct_side"]
        if cs is None:
            continue
        resp = cs if t["outcome"] == "correct" else ("right" if cs == "left" else "left")
        responded.append(resp)

    if not responded:
        return None

    avg_right = sum(1 for s in responded if s == "right") / len(responded)
    left_prob = 1.0 - avg_right
    logger.info("IBL debias triggered: ratio=%.2f avg_right=%.2f → P(left)=%.2f",
                last_click_ratio or -1, avg_right, left_prob)
    return left_prob


REGISTRY: dict[str, AlgorithmSpec] = {
    "brody": AlgorithmSpec(label="Brody (performance eq.)", fn=_brody, window=20),
    "ibl":   AlgorithmSpec(label="IBL (layup on preferred)", fn=_ibl,   window=10),
}
