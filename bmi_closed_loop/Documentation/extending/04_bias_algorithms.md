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
| `brody` | 20 | Calculates the rat's recent left bias and counteracts it — if the rat chose left 60 % of the time, future trials are pushed toward more right-heavy click ratios. |
| `ibl` | 10 | Calculates the same bias but accommodates it, making the correct side match the animal's current preference slightly more often. |
| `rebalance` | 20 | Forces equal left/right trial presentations regardless of the rat's choices. |

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
