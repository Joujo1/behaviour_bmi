# Adding Export Options

All exports live in one file: [bmi_closed_loop/ui/endpoints/export.py](../../ui/endpoints/export.py).

The file has two parts you need to care about:

1. **`EXPORT_TYPES`** (lines 41–110) — a dictionary that describes each export: its name, description, and what columns the CSV will have.
2. **`_run_query()`** (lines 155–356) — the function that actually fetches data from the database. It has one `if/elif` branch per export type.

To add a new export, you add one entry to `EXPORT_TYPES` and one SQL query to `_run_query()`. That's it — the download endpoint, the CSV streaming, and the filter UI all work automatically.

---

## What exports already exist

| Export name | What it contains |
|---|---|
| `trials` | One row per trial — outcome, correct side, timestamps, click seed |
| `events` | Every FSM event (state transitions, beam breaks, LED on/off) expanded into one row each |
| `click_timing` | Per-click timing detail — when each click was scheduled vs. when it actually fired |
| `substage_timeline` | Summary per substage per session — trial count, percent correct |
| `sessions` | One row per session — weight, water, duration, aggregate trial counts |
| `performance` | One row per subject per day per substage — clean for learning-curve plots |

---

## How to add a new export — step by step

### Step 1 — Add an entry to `EXPORT_TYPES`

Open `ui/endpoints/export.py` and find the `EXPORT_TYPES` dictionary starting at line 41. Add a new key at the end:

```python
"my_export": {
    "label": "My Export",
    "description": "One sentence explaining what this export contains.",
    "columns": ["subject", "session_date", "my_column_a", "my_column_b"],
    "has_substage_filter": False,
    "has_session_filter":  False,
},
```

- **`label`** — the name shown in the UI dropdown.
- **`description`** — shown below the dropdown to explain what the export is for.
- **`columns`** — the CSV header row. These must match exactly the columns your SQL query returns, in the same order.
- **`has_substage_filter`** — set to `True` if you want the user to be able to filter by substage. The filter value arrives as `args.get("substage_id")` in your query.
- **`has_session_filter`** — set to `True` if you want a per-session filter.

### Step 2 — Add the SQL query to `_run_query()`

Find `_run_query()` starting at line 155. At the bottom of the `if/elif` chain, before the final `return None, None`, add:

```python
elif export_type == "my_export":
    where, params = _trial_filters(args)
    sql = f"""
        SELECT
            s.code          AS subject,
            sess.started_at::date AS session_date,
            tr.outcome      AS my_column_a,
            tr.cage_id      AS my_column_b
        FROM trial_results tr
        JOIN sessions      sess ON sess.id = tr.session_id
        JOIN subjects      s    ON s.id   = sess.subject_id
        {where}
        ORDER BY tr.completed_at
    """
    cur.execute(sql, params)
```

- **`_trial_filters(args)`** (lines 117–136) gives you a `WHERE` clause and parameter list that handles the subject, date, substage, and session filters automatically. Use it unless your query doesn't join `trial_results` at all.
- **`_session_filters(args)`** (lines 139–152) is the same thing but for queries that join on `sessions` instead of `trial_results`.
- The column names in the `SELECT` must match the `"columns"` list you wrote in Step 1, in the same order.

### Step 3 — Done

The download endpoint at `GET /export/download?type=my_export` will stream a CSV with your new data immediately. No other changes needed.

---

## How the download works (for reference)

When someone clicks "Download" in the export UI:

1. The browser requests `GET /export/download?type=...&subject_ids=...&date_from=...` (line 415 in `export.py`).
2. `_run_query()` runs your SQL and returns an open database cursor.
3. A generator function (lines 433–451) reads the cursor one row at a time and streams the CSV to the browser. This means even very large exports don't load everything into memory at once.
4. The file is sent with `Content-Disposition: attachment; filename={type}.csv` so the browser saves it as a file automatically.

---

## Filtering — how it works

The helper `_trial_filters(args)` (line 117) builds a SQL `WHERE` clause from the query string parameters the user selected. It supports:

| Parameter | What it filters |
|---|---|
| `subject_ids` | One or more subject IDs (the user can select multiple animals) |
| `date_from` | Only trials on or after this date |
| `date_to` | Only trials on or before this date (inclusive) |
| `substage_id` | Only trials from a specific substage (only shown if `has_substage_filter: True`) |
| `session_id` | Only trials from a specific session (only shown if `has_session_filter: True`) |

If you call `_trial_filters(args)` in your query, all of these filters are applied automatically for free. You just have to make sure your SQL includes the necessary JOINs (`trial_results` → `sessions` → `subjects`).
