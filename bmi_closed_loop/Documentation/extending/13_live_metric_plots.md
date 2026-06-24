# Adding Live Metric Plots

The metrics page ([ui/templates/metrics.html](../../ui/templates/metrics.html)) fetches data from endpoints in [ui/endpoints/metrics.py](../../ui/endpoints/metrics.py) and renders it as interactive plots. Each plot is driven by one endpoint that runs a SQL query and returns JSON.

---

## Existing metric endpoints

| Endpoint | What it returns |
|---|---|
| `GET /metrics/animals?n=20` | Per-subject summary: total trials, pct correct, last-N pct correct, substage, days enrolled |
| `GET /metrics/learning-curve?subject_id=X` | Per-session pct correct ordered by session number — the standard learning curve |
| `GET /metrics/side-bias?subject_id=X` | Left/right trial counts and correct/wrong breakdown per side |
| `GET /metrics/dwell?subject_id=X` | Time spent at each substage: sessions, trials, pct correct |
| `GET /metrics/sessions?subject_id=X&cage_id=Y&from=…&to=…` | Filterable session log |
| `GET /metrics/trials?session_id=X` | Individual trial results for one session in order |

---

## How to add a new plot

### Step 1 — Add the SQL endpoint to `metrics.py`

Open `metrics.py` and add a new route that queries the database and returns JSON:

```python
@metrics_bp.get("/metrics/my-plot")
def my_plot():
    """One sentence describing what this endpoint returns."""
    subject_id = request.args.get("subject_id", type=int)
    if not subject_id:
        return jsonify([])

    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    se.started_at::date AS date,
                    AVG(my_metric)      AS avg_my_metric
                FROM trial_results tr
                JOIN sessions se ON se.id = tr.session_id
                WHERE se.subject_id = %(subject_id)s
                GROUP BY se.started_at::date
                ORDER BY date
            """, {"subject_id": subject_id})
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    return jsonify(rows)
```

### Step 2 — Add the plot to `metrics.html`

Open `metrics.html` and:

1. Add a `<canvas>` or `<div>` element where the plot will render:

```html
<canvas id="my-plot-canvas"></canvas>
```

2. Add a JavaScript function that fetches the endpoint and draws the chart. The existing plots use Chart.js — add a new chart instance using the same pattern as the other plots in the file.

3. Call your function when the page loads or when the subject selection changes.

---

## Where metrics data comes from

All metric endpoints query PostgreSQL directly via `psycopg2`. The tables used are:

- `trial_results` — one row per completed trial (outcome, correct_side, substage_id, events JSON)
- `sessions` — one row per session (subject_id, cage_id, started_at, weight_g, water_ml)
- `subjects` — subject identity and current substage
- `training_substages` / `training_stages` — curriculum structure

There is no caching layer. Every page load runs a fresh query. For queries over very large trial sets, add a `LIMIT` or pre-aggregate into a CTE.
