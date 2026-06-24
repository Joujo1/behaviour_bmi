# Bias Algorithms Reference

Bias algorithms adjust the left/right click ratio trial-by-trial based on the rat's recent choice history. The active algorithm is selected per substage in the curriculum editor. All algorithms are defined in [ui/bias_algorithms.py](../../ui/bias_algorithms.py).

For how to add a new algorithm, see [extending/04_bias_algorithms.md](../extending/04_bias_algorithms.md).

---

## Algorithm list

### `brody` — Counteract bias (window: 20)

Calculates the rat's left-choice fraction over the last 20 trials and counteracts it. If the rat chose left 70 % of the time, the algorithm shifts the click ratio so that future correct-side assignments favour the right. The rat is pushed away from its dominant side.

Best for: early training when you want to prevent the animal from developing a persistent side preference.

### `ibl` — Accommodate bias (window: 10)

Calculates the rat's left-choice fraction over the last 10 trials and accommodates it. If the rat is currently biased left, the algorithm makes the correct side be left more often, so the animal is rewarded for its natural preference while still learning the task structure.

Best for: preventing extended failure runs that might discourage a rat that is momentarily biased.

### `rebalance` — Equal presentations (window: 20)

Forces equal left/right trial presentations regardless of the animal's choices. Counts how many left and right trials have been presented in the last 20, and biases future trials toward whichever side has been presented less.

Best for: ensuring statistically balanced datasets when side bias is not a training concern.

---

## Common interface

All algorithms receive the same inputs and return the same type:

| Input | Type | Description |
|---|---|---|
| `recent` | `list[dict]` | Last N trial results. Each dict has `"correct_side"` (`"left"`, `"right"`, or `None`) and `"outcome"` (`"correct"` or `"wrong"`). |
| `trial_def` | `dict` | The full trial definition for the upcoming trial. |
| `last_click_ratio` | `float \| None` | Left probability used on the previous trial. `None` on the first trial. |

Return value: `left_probability` as a float in [0, 1], or `None` to leave the click ratio unchanged.

The returned `left_probability` is the probability that the left channel has the higher click rate. It is passed to `generate_clicks()` in [ui/click_generator.py](../../ui/click_generator.py).

---

## `none` — No bias correction

Selecting `"none"` in the curriculum UI disables bias correction entirely. Click ratios are drawn from the trial definition's original rates without adjustment.
