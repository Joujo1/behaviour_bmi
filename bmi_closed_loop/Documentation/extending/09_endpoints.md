# Adding Endpoints

The Flask web UI uses the Blueprint pattern — each area of functionality lives in its own file in [bmi_closed_loop/ui/endpoints/](../../ui/endpoints/) and exports a single Blueprint object. All blueprints are registered in [bmi_closed_loop/ui/ui_main.py](../../ui/ui_main.py).

---

## Existing blueprints

| Blueprint | File | What it handles |
|---|---|---|
| `control_bp` | `endpoints/control.py` | Fan duty, strip light, FSM graph render, NTP sync status |
| `session_bp` | `endpoints/session.py` | Open / close sessions, list active sessions |
| `trial_bp` | `endpoints/trial.py` | Start / stop trials, trial status |
| `stream_bp` | `endpoints/stream.py` | Start / stop camera stream, recording |
| `curriculum_bp` | `endpoints/curriculum.py` | Training stages, substages, criteria types |
| `subjects_bp` | `endpoints/subjects.py` | Create / list / update subjects |
| `metrics_bp` | `endpoints/metrics.py` | Performance metrics for plots |
| `export_bp` | `endpoints/export.py` | CSV data exports |
| `scoresheet_bp` | `endpoints/scoresheet.py` | Daily welfare scoresheet |
| `builder_bp` | `endpoints/builder.py` | Trial definition builder |
| `dev_bp` | `endpoints/dev.py` | Dev/debug tools (truncate tables, etc.) |

---

## How to add an endpoint to an existing blueprint

Open the relevant file (e.g. `endpoints/control.py`) and add a route using Flask's decorator syntax:

```python
@control_bp.get("/cage/<int:cage_id>/my-feature")
def get_my_feature(cage_id: int) -> Response:
    """Return some data for a cage."""
    data = {"cage": cage_id, "value": 42}
    return jsonify(data)
```

```python
@control_bp.post("/cage/<int:cage_id>/my-feature")
def set_my_feature(cage_id: int) -> Response:
    """Accept a JSON body and do something."""
    body = request.get_json(force=True)
    value = body.get("value")
    # ... do something ...
    return jsonify({"ok": True})
```

No registration step is needed — the endpoint is live as soon as the module is saved and the Flask app is restarted.

---

## How to add a new blueprint

If your endpoints don't fit into any existing blueprint, create a new file:

**`ui/endpoints/my_feature.py`**

```python
"""
One paragraph describing what this blueprint handles.
"""

import logging

from flask import Blueprint, Response, jsonify, request

logger = logging.getLogger(__name__)

my_feature_bp = Blueprint("my_feature", __name__)


@my_feature_bp.get("/my-feature/status")
def get_status() -> Response:
    return jsonify({"status": "ok"})
```

Then register it in `ui_main.py` (lines 21–73):

```python
# at the top with the other imports
from ui.endpoints.my_feature import my_feature_bp

# in create_app(), with the other register_blueprint calls
app.register_blueprint(my_feature_bp)
```

---

## Accessing shared resources from endpoints

| Resource | How to get it |
|---|---|
| Database connection | `current_app.db_pool.getconn()` — return it with `db_pool.putconn(conn)` after use |
| Valkey client | `current_app.valkey` |
| `CageRunner` instances | `current_app.cage_runners[cage_id]` |
| Configuration | `import config` — module-level constants are safe to read from any thread |

All of these are attached to the Flask app object in `ui_main.py` during startup.

---

## Returning errors

Use `abort()` for HTTP errors:

```python
from flask import abort
abort(404, description="Cage not found")
abort(400, description="Missing required field: value")
```

For internal errors, log with `logger.error(...)` and return a 500:

```python
return jsonify({"error": "something went wrong"}), 500
```
