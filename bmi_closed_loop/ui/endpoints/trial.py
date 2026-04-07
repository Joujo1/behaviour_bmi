import logging

import psycopg2
import psycopg2.extras
from flask import Blueprint, abort, current_app, jsonify, request

import config
from ui.runner import start_run, stop_run, on_trial_complete, get_run_context, is_running
from ui import advancement

trial_bp = Blueprint("trial", __name__)
_log = logging.getLogger("trial")


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


@trial_bp.get("/metrics")
def get_metrics():
    """
    Per-cage trial metrics aggregated from trial_results.
    Trial duration is taken from the timestamp of the last event in the events list.
    """
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    cage_id,
                    COUNT(*)                                                    AS total,
                    COUNT(*) FILTER (WHERE outcome = 'correct')                 AS successes,
                    COUNT(*) FILTER (WHERE outcome = 'wrong')                   AS failures,
                    COUNT(*) FILTER (WHERE outcome = 'aborted')                 AS aborted_count,
                    AVG(
                        CASE WHEN jsonb_array_length(events) > 0
                             THEN (events -> -1 ->> 't')::float
                        END
                    ) FILTER (WHERE outcome = 'correct')                        AS avg_success_s,
                    AVG(
                        CASE WHEN jsonb_array_length(events) > 0
                             THEN (events -> -1 ->> 't')::float
                        END
                    ) FILTER (WHERE outcome = 'wrong')                          AS avg_fail_s,
                    (array_agg(outcome ORDER BY completed_at DESC))[1]          AS last_outcome
                FROM trial_results
                GROUP BY cage_id
                ORDER BY cage_id
            """)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
    finally:
        conn.close()

    result = []
    for row in rows:
        d = dict(zip(cols, row))
        decided = (d["successes"] or 0) + (d["failures"] or 0)
        d["success_pct"]   = round(100 * d["successes"] / decided, 1) if decided > 0 else 0
        d["avg_success_s"] = round(float(d["avg_success_s"]), 2) if d["avg_success_s"] is not None else None
        d["avg_fail_s"]    = round(float(d["avg_fail_s"]),    2) if d["avg_fail_s"]    is not None else None
        result.append(d)

    return jsonify(result)



@trial_bp.post("/cage/<int:cage_id>/trial/run")
def run_start(cage_id: int):
    """
    Start a continuous run on a cage using a substage's task_config.
    Runs indefinitely until stopped manually or advancement criteria are met.

    Body:
        substage_id   int   — which substage to run (loads task_config from training_substages)
        session_id    int   — open session this run belongs to
        base_iti_s    float — seconds between trials after a correct outcome (default 5)
        fail_iti_s    float — seconds between trials after a wrong/aborted outcome (default 15)
    """
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)

    body = request.get_json(force=True) or {}
    substage_id = body.get("substage_id")
    session_id  = body.get("session_id")
    base_iti_s  = max(0.0, float(body.get("base_iti_s", 5.0)))
    fail_iti_s  = max(0.0, float(body.get("fail_iti_s", 15.0)))

    if not substage_id:
        return jsonify({"ok": False, "msg": "substage_id is required"}), 400

    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT task_config FROM training_substages WHERE id = %s", (substage_id,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({"ok": False, "msg": f"substage {substage_id} not found"}), 404

    trial_definition = row[0]  # psycopg2 returns JSONB as a dict

    sender = current_app.config["COMMAND_SENDERS"].get(cage_id)
    if not sender:
        abort(404)

    ok, msg = start_run(cage_id, trial_definition, sender,
                        base_iti_s, fail_iti_s,
                        session_id=session_id, substage_id=substage_id)
    return jsonify({"ok": ok, "msg": msg})


@trial_bp.post("/cage/<int:cage_id>/trial/run/stop")
def run_stop(cage_id: int):
    """Abort the current trial on the Pi immediately and stop the runner."""
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    sender = current_app.config["COMMAND_SENDERS"].get(cage_id)
    if sender:
        sender.send("STOP_TRIAL")
    ok, msg = stop_run(cage_id)
    return jsonify({"ok": ok, "msg": msg})



def handle_trial_event(cage_id: int, event: dict) -> None:
    """
    Called by the TCP reader thread when the Pi pushes a trial_complete or
    trial_aborted event. Writes the result to Postgres and unblocks the runner.

    Expected event shape:
        {"event": "trial_complete"|"trial_aborted", "trial_id": str, "events": list}
    """
    event_type = event.get("event")
    if event_type not in ("trial_complete", "trial_aborted"):
        return

    trial_id = event.get("trial_id", "unknown")
    outcome  = event.get("outcome", "aborted" if event_type == "trial_aborted" else "correct")
    events   = event.get("events", [])

    _log.info("Cage %d: %s  outcome=%s  trial_id=%s  n_events=%d", cage_id, event_type, outcome, trial_id, len(events))

    # Unblock the runner loop so the next rep can be sent
    on_trial_complete(cage_id, event)

    # Read session/substage from the active runner (may be None for one-shot runs)
    ctx = get_run_context(cage_id)

    # Persist to Postgres
    session_id  = ctx.get("session_id")
    substage_id = ctx.get("substage_id")

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trial_results
                        (cage_id, trial_id, outcome, events, session_id, substage_id, completed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (cage_id, trial_id, outcome, psycopg2.extras.Json(events),
                     session_id, substage_id),
                )

        # Evaluate advancement if this trial belongs to a tracked session + substage
        if session_id is not None and substage_id is not None:
            with conn.cursor() as cur:
                cur.execute("SELECT subject_id FROM sessions WHERE id = %s", (session_id,))
                row = cur.fetchone()
            subject_id = row[0] if row else None

            if subject_id is not None:
                decision = advancement.evaluate(subject_id, substage_id, conn)
                if decision != "stay":
                    with conn:
                        new_substage = advancement.apply(subject_id, substage_id, decision, conn)
                    # Stop the runner — animal has moved to a new substage,
                    # researcher should open a fresh session to continue
                    if is_running(cage_id):
                        stop_run(cage_id)
                        _log.info("Cage %d: runner stopped — subject %d %s to substage %d",
                                  cage_id, subject_id, decision, new_substage)

    except Exception as e:
        _log.error("Cage %d: failed to write trial result: %s", cage_id, e)
    finally:
        conn.close()
