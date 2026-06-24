# Adding Advancement Criteria

Advancement criteria decide when a rat moves forward (or falls back) to a different training substage. All criteria are registered in one dictionary in [bmi_closed_loop/ui/advancement.py](../../ui/advancement.py).

---

## The two existing criteria

| Type key | Parameters | What it does |
|---|---|---|
| `pct_correct` | `window`, `threshold` | Looks at the last `window` trials. If percent correct ≥ `threshold`, advances. If percent correct < `threshold` and the criterion is a fallback, triggers a fallback. |
| `min_trials` | `window` | Looks at the last `window` trials and advances once that many trials exist. Never triggers a fallback (always returns `False` when used as fallback). |

---

## The interface

Each handler is a function with this signature:

```python
def handler(
    criteria:     dict,
    subject_id:   int,
    substage_id:  int,
    conn:         psycopg2.extensions.connection,
    is_fallback:  bool,
) -> bool:
```

| Argument | Contents |
|---|---|
| `criteria` | The parsed JSONB from `advance_criteria` or `fallback_criteria` in `training_substages`. The `"type"` key has already been consumed — only the parameter keys remain (e.g. `{"window": 20, "threshold": 0.75}`). |
| `subject_id` | Database ID of the subject being evaluated. |
| `substage_id` | Database ID of the substage being evaluated. |
| `conn` | An open database connection. Use it to run whatever query you need. |
| `is_fallback` | `True` when evaluating the fallback criterion. Most handlers should invert their comparison: if the advance condition is `pct >= threshold`, the fallback condition is `pct < threshold`. |

Return `True` to trigger the transition, `False` to stay on the current substage.

All handlers are collected in the `CRITERIA_HANDLERS` dict at the bottom of `advancement.py`:

```python
CRITERIA_HANDLERS: dict[str, Callable] = {
    "pct_correct": _pct_correct,
    "min_trials":  _min_trials,
}
```

---

## How to add a new criterion — step by step

### Step 1 — Write the handler

Add a private function in `advancement.py`:

```python
def _my_criterion(
    criteria: dict,
    subject_id: int,
    substage_id: int,
    conn: psycopg2.extensions.connection,
    is_fallback: bool,
) -> bool:
    """Advance once the rat's median reaction time drops below a threshold."""
    window    = criteria["window"]
    threshold = criteria["threshold_ms"]
    cur = conn.cursor()
    cur.execute("""
        SELECT AVG(reaction_ms) FROM trial_results
        WHERE subject_id = %s AND substage_id = %s
        ORDER BY completed_at DESC LIMIT %s
    """, (subject_id, substage_id, window))
    row = cur.fetchone()
    if row is None or row[0] is None:
        return False
    fast_enough = row[0] < threshold
    return (not fast_enough) if is_fallback else fast_enough
```

### Step 2 — Add it to `CRITERIA_HANDLERS`

```python
CRITERIA_HANDLERS: dict[str, Callable] = {
    "pct_correct":   _pct_correct,
    "min_trials":    _min_trials,
    "reaction_time": _my_criterion,   # new
}
```

### Step 3 — Done (no UI change needed for the type list)

The endpoint `GET /criteria-types` in [ui/endpoints/curriculum.py](../../ui/endpoints/curriculum.py) reads `CRITERIA_HANDLERS` directly and returns all registered keys to the UI. Your new type will appear in the criteria type dropdown automatically.

**UI parameter fields**: The curriculum builder currently renders `window` and `threshold` input fields for any criteria type. If your new criterion uses different parameter names, you need to update the criteria form in [ui/templates/curriculum.html](../../ui/templates/curriculum.html) to add or rename fields accordingly.

---

## Where criteria are evaluated

After every trial completes, `CageRunner` (in [cage_runner.py](../../ui/cage_runner.py)) calls `advancement.py` to evaluate both the advance and fallback criteria for the current substage. If either returns `True`, the subject is moved to the target substage in the database and a Valkey notification is published to update the UI.
