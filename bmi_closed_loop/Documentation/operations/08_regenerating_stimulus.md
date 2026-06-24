# Regenerating a Stimulus

Every trial stores the random seed used to generate its click sequence. This lets you reproduce the exact same left/right click timestamps for any past trial — useful for offline analysis, validating timing, or replaying a specific stimulus.

---

## Where the seed is stored

The seed is stored in `trial_results.click_seed` (an integer). It is set by `CageRunner` before calling `generate_clicks()` and saved to the database when the trial completes.

---

## How to regenerate

```python
from bmi_closed_loop.ui.click_generator import generate_clicks

# Fetch the trial's parameters from the database
import psycopg2
conn = psycopg2.connect("postgresql://bmi:yaniklab@localhost/bmi_closed_loop")
cur  = conn.cursor()
cur.execute("""
    SELECT click_seed, trial_definition
    FROM trial_results
    WHERE id = %s
""", (trial_id,))
seed, trial_def = cur.fetchone()

# Find the play_clicks action in the trial definition to get left_rate, right_rate, duration
for state in trial_def["states"]:
    for action in state.get("entry_actions", []):
        if action["type"] == "play_clicks":
            left_rate  = action["left_rate"]
            right_rate = action["right_rate"]
            duration   = action["click_duration"]
            break

clicks = generate_clicks(
    left_rate=left_rate,
    right_rate=right_rate,
    duration=duration,
    seed=seed,
)

print(clicks["left_clicks"])   # identical to what was sent to the Pi
print(clicks["right_clicks"])
```

The output is guaranteed to match what was dispatched to the Pi for that trial as long as the `CLICK_WIDTH_S` constant has not changed since the trial was recorded.

---

## When seeds may not match

- If `CLICK_WIDTH_S` was changed between when the trial ran and when you regenerate (because `min_ici = 2 × CLICK_WIDTH_S` affects the output).
- If the `generate_clicks()` function itself was modified.
- If `click_seed` is `NULL` in the database — this means the trial predates the seed-logging feature.

---

## Validating click timing post-hoc

The `click_timing` export (Export page) contains the scheduled time and the actual fire time for every click in every trial, along with the jitter. Use this to verify that the Pi fired clicks within the expected latency bounds without needing to regenerate the sequence manually.
