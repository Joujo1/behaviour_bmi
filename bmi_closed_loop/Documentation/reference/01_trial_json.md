# Trial JSON Document Reference

A trial definition is a JSON object that fully describes one trial — its states, the actions to run in each state, and the transitions between them. It is authored in the curriculum builder UI, stored in `training_substages.task_config`, and sent to the Pi over TCP when a trial starts.

---

## Top-level fields

| Field | Type | Description |
|---|---|---|
| `trial_id` | string | Identifier for this trial template (e.g. `"sample"`, `"easy_left"`). Stored in `trial_results` for traceability. |
| `side_mode` | string | How the correct side is determined. `"random"` = drawn independently each trial; `"fixed_left"` / `"fixed_right"` = always that side. |
| `base_iti_s` | float | Inter-trial interval (seconds) after a correct outcome. |
| `fail_iti_s` | float | Inter-trial interval (seconds) after a wrong or aborted outcome. |
| `initial_state` | string | The `id` of the state the FSM enters at trial start. |
| `states` | array | Ordered list of state objects (see below). |

---

## State object

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique name for this state within the trial. Referenced by transitions and `initial_state`. |
| `duration` | float | Maximum time (seconds) the FSM stays in this state before a timeout transition fires. |
| `entry_actions` | array | Actions executed when the state is entered (see Action object below). |
| `exit_actions` | array | Actions executed when the state is left, regardless of which transition fires. |
| `transitions` | array | Ordered list of transition objects (see below). First matching transition wins. |

---

## Action object

| Field | Type | Description |
|---|---|---|
| `type` | string | Action type key. One of `"led_on"`, `"led_off"`, `"valve_open"`, `"play_clicks"`. |
| `target` | string | For LED and valve actions: `"left"`, `"right"`, `"center"`, `"high_click_side"`, or `"low_click_side"`. |
| `left_rate` | float | *(play_clicks only, template form)* Mean click rate for the left channel (clicks/sec). Replaced with `left_clicks` before being sent to the Pi. |
| `right_rate` | float | *(play_clicks only, template form)* Mean click rate for the right channel. Replaced with `right_clicks` before being sent to the Pi. |
| `click_duration` | float | *(play_clicks only)* Length of the click stimulus in seconds. |
| `left_clicks` | array of float | *(play_clicks only, runtime form)* Pre-generated click timestamps in seconds, left channel. Present after `CageRunner` calls `generate_clicks()`. |
| `right_clicks` | array of float | *(play_clicks only, runtime form)* Pre-generated click timestamps in seconds, right channel. |

`high_click_side` and `low_click_side` are symbolic targets resolved by the engine at runtime based on which side has the higher click rate for that trial.

---

## Transition object

| Field | Type | Description |
|---|---|---|
| `trigger` | string | What causes this transition. `"beam_break"` = sensor event; `"timeout"` = state duration elapsed. |
| `target` | string | *(beam_break only)* Which sensor must be active: `"left"`, `"right"`, `"center"`, `"high_click_side"`, `"low_click_side"`. |
| `hold_ms` | int | *(beam_break only, optional)* Sensor must stay active for this many milliseconds before the transition fires (debounce). |
| `next_state` | string | The `id` of the state to move to. Special values: `"__correct__"` ends the trial as correct; `"__wrong__"` ends it as wrong/aborted. |

---

## Template form vs. runtime form

The trial builder stores `play_clicks` actions with `left_rate`, `right_rate`, and `click_duration`. Before the trial is dispatched to the Pi, `CageRunner` calls `generate_clicks()` to replace those rate parameters with concrete timestamp arrays (`left_clicks`, `right_clicks`). The Pi never sees the rate parameters — it only receives the determined form.

---

## Example (template form)

```json
{
  "trial_id": "sample",
  "side_mode": "random",
  "base_iti_s": 5.0,
  "fail_iti_s": 15.0,
  "initial_state": "stimulus",
  "states": [
    {
      "id": "stimulus",
      "duration": 10.0,
      "entry_actions": [
        { "type": "play_clicks", "left_rate": 80, "right_rate": 20, "click_duration": 2.5 },
        { "type": "led_on", "target": "high_click_side" }
      ],
      "exit_actions": [
        { "type": "led_off", "target": "high_click_side" }
      ],
      "transitions": [
        { "trigger": "beam_break", "target": "center", "next_state": "choice", "hold_ms": 100 },
        { "trigger": "timeout", "next_state": "__wrong__" }
      ]
    },
    {
      "id": "choice",
      "duration": 5.0,
      "entry_actions": [],
      "exit_actions": [],
      "transitions": [
        { "trigger": "beam_break", "target": "high_click_side", "next_state": "reward" },
        { "trigger": "beam_break", "target": "low_click_side",  "next_state": "__wrong__" },
        { "trigger": "timeout", "next_state": "__wrong__" }
      ]
    },
    {
      "id": "reward",
      "duration": 2.0,
      "entry_actions": [
        { "type": "valve_open", "target": "high_click_side" }
      ],
      "exit_actions": [],
      "transitions": [
        { "trigger": "timeout", "next_state": "__correct__" }
      ]
    }
  ]
}
```
