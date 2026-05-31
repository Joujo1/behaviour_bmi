# Cage Runner Flowchart

<!-- TODO: side resolution and bias algorithm flowchart -->

`CageRunner` (`ui/cage_runner.py`) is the PC-side trial loop. One instance exists per cage permanently; a worker thread starts and stops inside it per session. Each iteration of the loop prepares a trial during the ITI, dispatches it to the Pi, and waits for the result.

---

## Trial loop (`_run_loop`)

```
┌─────────────────────────────────────────────────┐
│  Wait for ITI duration (base_iti ± jitter)       │
│                                                   │
│  _apply_bias()        ← query recent trial_results│
│  _resolve_sides()     ← assign left_rate/right_rate│
│  _expand_clicks()     ← generate Poisson trains   │
│  _resolve_aliases()   ← expand shorthand fields   │
│                                                   │
│  sender.send(trial_json)  ──────────────────────► Pi │
│                                                   │
│  event.wait()   ◄──────── on_trial_complete()     │
└─────────────────────────────────────────────────┘
```

The entire trial preparation runs during the inter-trial interval of the *previous* trial, so `sender.send()` never blocks the ITI — by the time the ITI ends the trial is ready to transmit immediately.

`event.wait()` blocks until `on_trial_complete(event)` is called from the TCP reader thread (in `event_handler`). The runner does not poll; it wakes exactly once per trial result.

---

## Context dict

At any point the runner holds a `context` dict that `event_handler` reads before signalling completion:

```python
{
  "session_id":   int | None,
  "substage_id":  int | None,
  "correct_side": "left" | "right" | None,
  "click_seed":   int | None,
}
```

`event_handler` reads this *before* calling `on_trial_complete()` because `on_trial_complete` wakes the runner thread, which immediately overwrites `correct_side` during the next ITI pre-computation.

---

## Side resolution (`_apply_bias` → `_resolve_sides`)

`_apply_bias()` queries recent `trial_results` from Postgres and calls the registered bias algorithm (from `bias_algorithms.REGISTRY`) to produce a `left_probability` in [0, 1]. The algorithm can return `None` to leave the trial unchanged.

`_resolve_sides()` uses `left_probability` (or 0.5 if no bias) to coin-flip the correct side, then assigns `left_rate` and `right_rate` from the substage's `task_config` to the correct and incorrect sides respectively.

Three algorithms are available:

| Name | Logic | Window |
|---|---|---|
| `brody` | Pushes trials toward the side the animal finds harder: `P(left) = fc_right / (fc_left + fc_right)` | 20 |
| `ibl` | After a wrong trial, repeats on the side the animal tends to respond to (layup) | 10 |
| `rebalance` | Pushes toward the under-presented side: `P(left) = n_right / (n_left + n_right)` | 20 |
| `none` | No correction — pure 50/50 | — |

---

## Click generation (`_expand_clicks`)

`click_generator.generate_clicks(left_rate, right_rate, duration, seed)` generates two independent Poisson click trains. A fixed RNG seed (stored as `click_seed` in the context and persisted to `trial_results`) makes any trial exactly reproducible for offline analysis or stimulus regeneration.

A minimum inter-click interval of `2 × CLICK_WIDTH_S = 6 ms` (start-to-start) is enforced to prevent waveform addition artifacts in the Pi's audio buffer. Clicks drawn closer than this are shifted forward; none are dropped.

---

## Mid-session substage switch (`switch_substage`)

`switch_substage(new_task_config, new_substage_id)` can be called from `event_handler` at any point between trials (while the runner is in `event.wait()`). It replaces the task config and substage ID for the next iteration without stopping the runner thread. If called while the runner is actively sending a trial, it returns `False` and `event_handler` falls back to stopping the runner.
