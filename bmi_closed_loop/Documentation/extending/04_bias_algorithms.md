# Adding Side Bias Algorithms

Side bias algorithms adjust the left/right click ratio trial-by-trial to counteract or accommodate a rat's tendency to prefer one side. All algorithms live in one file: [bmi_closed_loop/ui/bias_algorithms.py](../../ui/bias_algorithms.py).

---

## How it works

When `CageRunner` starts a new trial it calls the active algorithm to get a `left_probability` value. That value is passed to `generate_clicks()`, which draws the actual click ratio for the trial. If the algorithm returns `None`, the system falls back to the trial definition's original rates unchanged.

The curriculum UI lets the operator pick one algorithm per substage from a dropdown. The key stored in the database is the REGISTRY key (e.g. `"brody"`).

---

## The three existing algorithms

| Registry key | Window | What it does |
|---|---|---|
| `brody` | 20 | Performance equalisation: computes per-side accuracy and pushes more trials toward the side the animal performs worse on. |
| `ibl` | 10 | Layup on preferred side: after a wrong trial, presents the side the animal responds to most often, skipping the correction on ambiguous stimuli. |
| `rebalance` | 20 | Presentation rebalance: pushes trials toward whichever side has been shown less often, regardless of outcome. |

### `brody` — performance equalisation

Computes the fraction correct separately for left trials and right trials over the last `window` completed trials. Sets the left probability so that the harder side is presented more often:

```
fc_l  = (correct left trials) / (total left trials in window)
fc_r  = (correct right trials) / (total right trials in window)
P(left) = fc_r / (fc_l + fc_r)
```

If `fc_l + fc_r == 0`, or if there are no trials on one side, returns `None` (no adjustment). The formula ensures that when the animal is worse on the right (`fc_r < fc_l`), `P(left)` falls below 0.5, giving the animal more right trials.

### `ibl` — layup on preferred side

Only fires when the most recent trial was wrong. Computes each trial's *actual response side* (the side the animal went to, regardless of which was correct) and finds the average right-response rate over the last `window` trials:

```
responded[i] = correct_side[i]            if outcome[i] == "correct"
             = opposite(correct_side[i])  if outcome[i] == "wrong"

avg_right = count("right" in responded) / len(responded)
P(left)   = 1 − avg_right
```

An optional difficulty gate skips the correction when the previous trial's click ratio was below `ibl_easy_min_ratio` (default `2.5` — configurable per trial definition). The idea is not to give a layup on an already-ambiguous stimulus. Returns `None` if the last trial was not wrong, or if there are no sided trials in the window.

### `rebalance` — presentation rebalance

Counts left and right presentations (by `correct_side`) in the recent window and sets the left probability so that the under-presented side is favoured:

```
n_left, n_right = presentations per side in window
P(left) = n_right / (n_left + n_right)
```

Returns `None` if there are no sided trials in the window.

---

## The interface

Each algorithm is a plain function with this type alias (defined at the top of `bias_algorithms.py`):

```python
AlgorithmFn = Callable[[list[dict], dict, float | None], float | None]
```

The three arguments:

| Argument | Type | Contents |
|---|---|---|
| `recent` | `list[dict]` | Last N trial results (N = the algorithm's `window`). Each dict has `"correct_side"` (`"left"`, `"right"`, or `None`) and `"outcome"` (`"correct"` or `"wrong"`). |
| `trial_def` | `dict` | The full trial definition JSON for the upcoming trial. Useful if you need the base click rates. |
| `last_click_ratio` | `float \| None` | The left probability used on the previous trial. `None` on the first trial. |

The function must return `left_probability` as a float in [0, 1], or `None` to skip bias adjustment for this trial.

Each algorithm is wrapped in an `AlgorithmSpec` frozen dataclass:

```python
@dataclass(frozen=True)
class AlgorithmSpec:
    label:  str           # display name shown in the UI dropdown
    fn:     AlgorithmFn   # the function itself
    window: int           # how many recent trials to pass as `recent`
```

---

## How to add a new algorithm — step by step

### Step 1 — Write the function

Add a new private function anywhere above `REGISTRY` in `bias_algorithms.py`:

```python
def _my_algorithm(recent: list[dict], trial_def: dict, last_click_ratio: float | None) -> float | None:
    """One sentence explaining the strategy."""
    if len(recent) < 5:
        return None  # not enough data yet
    left_choices = sum(1 for r in recent if r["correct_side"] == "left")
    left_probability = ...  # your calculation
    return left_probability  # float in [0, 1]
```

### Step 2 — Add an entry to `REGISTRY`

At the bottom of `bias_algorithms.py`, find `REGISTRY` and add your entry:

```python
REGISTRY: dict[str, AlgorithmSpec] = {
    "brody":     AlgorithmSpec(...),
    "ibl":       AlgorithmSpec(...),
    "rebalance": AlgorithmSpec(...),
    "my_algo":   AlgorithmSpec(label="My Algorithm", fn=_my_algorithm, window=15),
}
```

The key (`"my_algo"`) is what gets stored in the database. The `label` is what appears in the curriculum UI dropdown — it is populated from `REGISTRY` automatically, so no UI change is needed.

### Step 3 — Run the database schema migration

The `training_substages.bias_algorithm` column has a `CHECK` constraint listing the allowed algorithm keys. Add your new key to that constraint (or drop the constraint if you want to allow any string). See [02_database_schema.md](02_database_schema.md) for how to run schema migrations.

---

## Where the algorithm is called

`CageRunner` (in [cage_runner.py](../../ui/cage_runner.py)) fetches the algorithm name from the substage, looks it up in `REGISTRY`, passes the last N trial records through `AlgorithmSpec.fn`, and uses the returned `left_probability` when calling `generate_clicks()`.
