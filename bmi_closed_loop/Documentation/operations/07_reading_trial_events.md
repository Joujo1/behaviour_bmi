# How to Read Trial Events

Every trial stores a JSON array of FSM events in the `trial_results.events` column. This is the primary source for reconstructing exactly what happened during a trial — when each beam was broken, when states changed, and when hardware outputs toggled.

---

## Event shapes

All events have a `"t"` key: elapsed seconds since trial start, measured by `CLOCK_MONOTONIC` on the Pi.

### Beam event
```json
{"t": 1.234, "sensor": "center", "active": true}
```
Fired every time a beam sensor changes state. `active: true` = beam broken.

### State transition event
```json
{"t": 1.450, "from": "stimulus", "to": "choice"}
```
Fired when the FSM moves from one state to another.

### Output event
```json
{"t": 0.012, "output": "led_left", "active": true}
```
Fired when a hardware output turns on or off.

---

## Querying events from the database

Events are stored as a JSONB array in `trial_results.events`. PostgreSQL's JSONB operators let you query inside them directly.

### Get all events for a trial
```sql
SELECT events
FROM trial_results
WHERE id = 12345;
```

### Expand all events into rows
```sql
SELECT
    tr.id   AS trial_id,
    ev->>'t'      AS t_s,
    ev->>'sensor' AS sensor,
    ev->>'active' AS active,
    ev->>'from'   AS from_state,
    ev->>'to'     AS to_state,
    ev->>'output' AS output
FROM trial_results tr,
     jsonb_array_elements(tr.events) AS ev
WHERE tr.session_id = 42
ORDER BY tr.id, (ev->>'t')::float;
```

### Get first beam-break time in each trial
```sql
SELECT
    tr.id,
    MIN((ev->>'t')::float) AS first_beam_t
FROM trial_results tr,
     jsonb_array_elements(tr.events) AS ev
WHERE ev->>'sensor' IS NOT NULL
  AND (ev->>'active')::boolean = true
  AND tr.session_id = 42
GROUP BY tr.id;
```

### Get state transition times
```sql
SELECT
    tr.id,
    ev->>'from'   AS from_state,
    ev->>'to'     AS to_state,
    (ev->>'t')::float AS t_s
FROM trial_results tr,
     jsonb_array_elements(tr.events) AS ev
WHERE ev->>'from' IS NOT NULL
  AND tr.session_id = 42
ORDER BY tr.id, t_s;
```

---

## Using the export

The `events` export type (see the Export page) expands all events into one CSV row each, with columns for trial ID, outcome, correct side, event type, sensor/output name, active state, and timestamp. This is usually easier to work with than raw SQL for downstream analysis.

Go to the Export page, select **events**, filter by subject and date range, and click Download.
