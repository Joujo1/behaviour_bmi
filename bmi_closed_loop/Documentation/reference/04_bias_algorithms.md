# Bias Algorithms Reference

Bias algorithms adjust the left/right click ratio trial-by-trial based on the rat's recent choice history. The active algorithm is selected per substage in the curriculum editor. All algorithms are defined in [ui/bias_algorithms.py](../../ui/bias_algorithms.py).

For how to add a new algorithm, see [extending/04_bias_algorithms.md](../extending/04_bias_algorithms.md).

---

## Algorithm list

### `brody` — Performance equalisation (window: 20)

Computes the fraction correct separately for left and right trials and increases the presentation rate of whichever side the animal finds harder:

```
fc_l  = (correct left trials)  / (total left trials in window)
fc_r  = (correct right trials) / (total right trials in window)
P(left) = fc_r / (fc_l + fc_r)
```

When `fc_l + fc_r == 0` or one side has no trials yet, returns `None` (no adjustment). The formula ensures that if the animal is worse on the right (`fc_r < fc_l`), `P(left)` falls below 0.5, so the animal receives more right trials on the next draw.

Best for: early training when you want to prevent the animal from developing a persistent side preference.

### `ibl` — Layup on preferred side (window: 10)

Only fires when the most recent trial was wrong. Infers the animal's actual response side for each recent trial (the side it went to, regardless of which was correct), then sets the next trial's correct side to match the animal's current response tendency:

```
responded[i] = correct_side[i]             if outcome[i] == "correct"
             = opposite(correct_side[i])   if outcome[i] == "wrong"

avg_right = count("right" in responded) / len(responded)
P(left)   = 1 − avg_right
```

Returns `None` (no adjustment) if the most recent trial was not wrong, or if there are no sided trials in the window. An optional difficulty gate skips the correction when the previous trial's click ratio was below `ibl_easy_min_ratio` (configurable per trial definition, default `2.5`) — no layup is given on an already-ambiguous stimulus.

Best for: preventing extended failure runs by giving the animal a recovery trial after a wrong response.

### `rebalance` — Equal presentations (window: 20)

Counts left and right presentations in the recent window and biases toward whichever side has been shown less:

```
n_left, n_right = presentations per side in window (by correct_side)
P(left) = n_right / (n_left + n_right)
```

Returns `None` if there are no sided trials in the window.

Best for: ensuring statistically balanced datasets when side bias is not a training concern.

---

## Common interface

All algorithms receive the same inputs and return the same type:

| Input | Type | Description |
|---|---|---|
| `recent` | `list[dict]` | Last N trial results. Each dict has `"correct_side"` (`"left"`, `"right"`, or `None`) and `"outcome"` (`"correct"` or `"wrong"`). |
| `trial_def` | `dict` | The full trial definition for the upcoming trial. |
| `last_click_ratio` | `float \| None` | Click ratio from the previous trial: `n_hi / n_lo` where `n_hi` and `n_lo` are the generated click counts on the high-rate and low-rate channels respectively (e.g. `4.0` for an 80/20 split). `None` on the first trial or when no click stimulus was present. |

Return value: `left_probability` as a float in [0, 1], or `None` to leave the click ratio unchanged.

The returned `left_probability` is stored in the trial dict as `side_mode = "weighted"`. `CageRunner._resolve_sides()` then uses it as a biased coin-flip probability to determine which side gets the high click rate for that trial, after which `_expand_clicks()` calls `generate_clicks()` with the resolved rates.

---

## `none` — No bias correction

Selecting `"none"` in the curriculum UI disables bias correction entirely. Click ratios are drawn from the trial definition's original rates without adjustment.
