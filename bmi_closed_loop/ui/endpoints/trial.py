import json
import logging

import psycopg2
import valkey as valkey_client
from flask import Blueprint, abort, current_app, jsonify, request

import config
from ui.cage_runner import runners
from ui.event_handler import handle_trial_event  # re-exported for ui_main wiring

_valkey = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)

trial_bp = Blueprint("trial", __name__)
_log = logging.getLogger("trial")


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)



def start_runner(cage_id: int, substage_id: int, session_id: int | None,
                 task_config: dict | None = None) -> tuple[bool, str]:
    """
    Start the trial runner for a cage.  If task_config is not supplied it is
    fetched from the DB.  Returns (ok, message).  Must be called inside a
    Flask request context (needs current_app for COMMAND_SENDERS).
    """
    if task_config is None:
        conn = _get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT task_config FROM training_substages WHERE id = %s",
                            (substage_id,))
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return False, f"substage {substage_id} not found"
        task_config = row[0]

    base_iti_s = task_config.get("base_iti_s")
    fail_iti_s = task_config.get("fail_iti_s")
    if base_iti_s is None or fail_iti_s is None:
        return False, "substage has no ITI defined — set Base ITI and Fail ITI in the curriculum builder"

    runner = runners.get(cage_id)
    sender = current_app.config["COMMAND_SENDERS"].get(cage_id)
    if runner is None or sender is None:
        return False, f"no runner/sender for cage {cage_id}"

    return runner.start(
        task_config, sender,
        max(0.0, float(base_iti_s)),
        max(0.0, float(fail_iti_s)),
        session_id=session_id,
        substage_id=substage_id,
    )


@trial_bp.post("/cage/<int:cage_id>/trial/run")
def run_start(cage_id: int):
    """
    Start a continuous run on a cage using a substage's task_config.
    Runs indefinitely until stopped manually or advancement criteria are met.
    """
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)

    body = request.get_json(force=True) or {}
    substage_id = body.get("substage_id")
    session_id  = body.get("session_id")

    if not substage_id:
        return jsonify({"ok": False, "msg": "substage_id is required"}), 400

    ok, msg = start_runner(cage_id, substage_id, session_id)
    return jsonify({"ok": ok, "msg": msg})


@trial_bp.post("/cage/<int:cage_id>/trial/run/stop")
def run_stop(cage_id: int):
    """Abort the current trial on the Pi immediately and stop the runner."""
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    sender = current_app.config["COMMAND_SENDERS"].get(cage_id)
    if sender:
        sender.send("STOP_TRIAL")
    runner = runners.get(cage_id)
    ok, msg = runner.stop() if runner else (False, "no runner for this cage")
    return jsonify({"ok": ok, "msg": msg})




@trial_bp.get("/cage/<int:cage_id>/run/status")
def run_status(cage_id: int):
    """Return running state, current substage label, and elapsed seconds."""
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    runner = runners.get(cage_id)
    if runner is None:
        abort(404)
    status = runner.get_status()
    substage_label = None
    if status["substage_id"] is not None:
        conn = _get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT label FROM training_substages WHERE id = %s",
                            (status["substage_id"],))
                row = cur.fetchone()
            substage_label = row[0] if row else None
        finally:
            conn.close()
    return jsonify({
        "running":        status["running"],
        "substage_id":    status["substage_id"],
        "substage_label": substage_label,
        "started_at":     status["started_at"],
    })


@trial_bp.get("/cage/<int:cage_id>/advancement")
def get_advancement(cage_id: int):
    """Return the pending advancement notification for a cage, if any."""
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    raw = _valkey.get(f"cage:{cage_id}:advancement")
    if raw is None:
        return jsonify(None)
    return jsonify(json.loads(raw))
