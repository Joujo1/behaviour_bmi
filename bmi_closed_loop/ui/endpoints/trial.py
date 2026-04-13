import json
import logging
import time

import psycopg2
import psycopg2.extras
import valkey as valkey_client
from flask import Blueprint, abort, current_app, jsonify, request

import config
from ui.runner import start_run, stop_run, switch_substage, on_trial_complete, get_run_context, is_running
from ui import advancement

_valkey = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)

trial_bp = Blueprint("trial", __name__)
_log = logging.getLogger("trial")


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


@trial_bp.get("/metrics")
def get_metrics():
    """
    Per-cage trial metrics aggregated from trial_results.
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
    """
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)

    body = request.get_json(force=True) or {}
    substage_id = body.get("substage_id")
    session_id  = body.get("session_id")

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

    trial_definition = row[0]

    base_iti_s = trial_definition.get("base_iti_s")
    fail_iti_s = trial_definition.get("fail_iti_s")
    if base_iti_s is None or fail_iti_s is None:
        return jsonify({"ok": False, "msg": "substage has no ITI defined — set Base ITI and Fail ITI in the curriculum builder"}), 400
    base_iti_s = max(0.0, float(base_iti_s))
    fail_iti_s = max(0.0, float(fail_iti_s))

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
    """
    event_type = event.get("event")
    if event_type not in ("trial_complete", "trial_aborted"):
        return

    trial_id = event.get("trial_id", "unknown")
    outcome  = event.get("outcome", "aborted" if event_type == "trial_aborted" else "correct")
    events   = event.get("events", [])

    _log.info("Cage %d: %s  outcome=%s  trial_id=%s  n_events=%d", cage_id, event_type, outcome, trial_id, len(events))

    on_trial_complete(cage_id, event)

    # Read session/substage from the active runner
    ctx = get_run_context(cage_id)

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
                    if new_substage and is_running(cage_id):
                        # Fetch new task_config and swap the runner
                        with conn.cursor() as cur:
                            cur.execute("SELECT task_config FROM training_substages WHERE id = %s",
                                        (new_substage,))
                            tc_row = cur.fetchone()
                        if tc_row and tc_row[0].get("base_iti_s") is not None:
                            switched = switch_substage(cage_id, tc_row[0], new_substage)
                            if switched:
                                _log.info("Cage %d: auto-switched substage — subject %d %s to substage %d",
                                          cage_id, subject_id, decision, new_substage)
                            else:
                                _log.warning("Cage %d: switch_substage failed, stopping instead", cage_id)
                                stop_run(cage_id)
                        else:
                            _log.warning("Cage %d: new substage %d has no ITI — stopping runner",
                                         cage_id, new_substage)
                            stop_run(cage_id)

                    # Write UI notification to Valkey (expires after 2 minutes)
                    try:
                        with conn.cursor() as cur:
                            cur.execute("SELECT label FROM training_substages WHERE id = %s",
                                        (new_substage,))
                            lrow = cur.fetchone()
                        new_label = lrow[0] if lrow else f"substage {new_substage}"
                        _valkey.set(
                            f"cage:{cage_id}:advancement",
                            json.dumps({
                                "decision":  decision,
                                "new_id":    new_substage,
                                "new_label": new_label,
                                "ts":        time.time(),
                            }),
                            ex=20,
                        )
                    except Exception as ve:
                        _log.warning("Cage %d: could not write advancement notification: %s",
                                     cage_id, ve)

    except Exception as e:
        _log.error("Cage %d: failed to write trial result: %s", cage_id, e)
    finally:
        conn.close()


@trial_bp.get("/cage/<int:cage_id>/advancement")
def get_advancement(cage_id: int):
    """Return the pending advancement notification for a cage, if any."""
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    raw = _valkey.get(f"cage:{cage_id}:advancement")
    if raw is None:
        return jsonify(None)
    return jsonify(json.loads(raw))
