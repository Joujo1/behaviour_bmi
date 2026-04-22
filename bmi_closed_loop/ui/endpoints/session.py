import json
import logging

import psycopg2
import valkey as valkey_client
from flask import Blueprint, current_app, jsonify, request

import config
from ui.cage_runner import runners
from ui.endpoints.trial import start_runner
from ui.endpoints.scoresheet import auto_create_scoresheet_entry

session_bp = Blueprint("session", __name__)
_log = logging.getLogger("session")
_valkey = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


@session_bp.post("/session/open")
def open_session():
    """
    Open a new session. If cage_id + subject_id are provided, automatically:
      - enables frame recording for that cage (cage:{id}:recording = 1)
      - starts the trial runner using the subject's current substage
    """
    body = request.get_json(force=True) or {}

    subject_id         = body.get("subject_id")
    cage_id            = body.get("cage_id")
    substage_id        = None
    task_config        = None
    reference_weight_g = None

    if subject_id is not None:
        conn = _get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT s.current_substage_id, ts.task_config, s.reference_weight_g
                    FROM subjects s
                    LEFT JOIN training_substages ts ON ts.id = s.current_substage_id
                    WHERE s.id = %s
                    """,
                    (subject_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row is None:
            return jsonify({"ok": False, "msg": f"subject {subject_id} not found"}), 404
        substage_id       = row[0]
        task_config       = row[1]
        reference_weight_g = row[2]

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                if subject_id is not None:
                    cur.execute(
                        "SELECT COUNT(*) + 1 FROM sessions WHERE subject_id = %s",
                        (subject_id,),
                    )
                    session_number = cur.fetchone()[0]
                else:
                    session_number = None

                cur.execute(
                    """
                    INSERT INTO sessions
                        (cage_id, session_number, researcher, notes, subject_id, substage_id, weight_g, water_ml)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        cage_id,
                        session_number,
                        body.get("researcher"),
                        body.get("notes"),
                        subject_id,
                        substage_id,
                        body.get("weight_g"),
                        body.get("water_ml"),
                    ),
                )
                session_id = cur.fetchone()[0]

                if subject_id is not None:
                    auto_create_scoresheet_entry(subject_id, session_id, conn)
    finally:
        conn.close()

    # Store active session state for UI restoration on page reload
    if cage_id is not None:
        _valkey.set(f"cage:{cage_id}:active_session", json.dumps({
            "session_id":     session_id,
            "session_number": session_number,
            "subject_id":     subject_id,
            "substage_id":    substage_id,
        }))

    # Enable recording and start streaming for the cage
    if cage_id is not None:
        _valkey.set(f"cage:{cage_id}:recording", "1")
        if _valkey.get(f"cage:{cage_id}:streaming") != b"1":
            sender = current_app.config["COMMAND_SENDERS"].get(cage_id)
            if sender:
                ok, _ = sender.send("START_STREAMING")
                if ok:
                    _valkey.set(f"cage:{cage_id}:streaming", "1")

    # Auto-start trials if the substage has a valid task config
    trials_started = False
    trials_msg = None
    if cage_id is not None and substage_id is not None:
        trials_started, trials_msg = start_runner(
            cage_id, substage_id, session_id, task_config=task_config
        )

    _log.info(
        "Session %d opened (cage=%s subject=%s substage=%s session_number=%s trials_started=%s)",
        session_id, cage_id, subject_id, substage_id, session_number, trials_started,
    )
    needs_ref_weight = (
        subject_id is not None
        and session_number == 1
        and reference_weight_g is None
    )
    return jsonify({
        "ok":                  True,
        "session_id":          session_id,
        "session_number":      session_number,
        "substage_id":         substage_id,
        "trials_started":      trials_started,
        "trials_msg":          trials_msg,
        "needs_reference_weight": needs_ref_weight,
        "subject_id":          subject_id,
    })


@session_bp.post("/session/<int:session_id>/close")
def close_session(session_id: int):
    """Close an open session. Disables recording and stops the trial runner for the cage."""
    body = request.get_json(force=True) or {}

    fields = ["closed_at = NOW()"]
    values = []

    if "weight_g" in body:
        fields.append("weight_g = %s"); values.append(body["weight_g"])
    if "water_ml" in body:
        fields.append("water_ml = %s"); values.append(body["water_ml"])

    values.append(session_id)
    cage_id = None
    _log.info("close_session called: session_id=%s body=%s", session_id, body)
    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE sessions SET {', '.join(fields)} WHERE id = %s RETURNING cage_id",
                    values,
                )
                row = cur.fetchone()
                _log.info("close_session UPDATE returned row=%s", row)
                if row:
                    cage_id = row[0]
    except Exception as e:
        _log.error("close_session DB error: %s", e)
        raise
    finally:
        conn.close()

    if cage_id is not None:
        # Clear Valkey state before any potentially blocking calls
        _valkey.delete(f"cage:{cage_id}:active_session")
        _valkey.set(f"cage:{cage_id}:recording", "0")
        runner = runners.get(cage_id)
        if runner:
            runner.stop()
        sender = current_app.config["COMMAND_SENDERS"].get(cage_id)
        if sender:
            sender.send("STOP_TRIAL")

    _log.info("Session %d closed (cage=%s)", session_id, cage_id)
    return jsonify({"ok": True})


@session_bp.get("/sessions/active")
def active_sessions():
    """Return active session state per cage from Valkey (set on open, deleted on close)."""
    result = {}
    for cage_id in range(1, config.N_CAGES + 1):
        raw = _valkey.get(f"cage:{cage_id}:active_session")
        if raw:
            try:
                result[cage_id] = json.loads(raw)
            except Exception:
                pass
    return jsonify(result)


@session_bp.get("/sessions")
def list_sessions():
    """List recent sessions with subject and substage info."""
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    se.id,
                    se.cage_id,
                    se.session_number,
                    se.researcher,
                    se.started_at,
                    se.closed_at,
                    se.weight_g,
                    se.water_ml,
                    se.notes,
                    su.code         AS subject_code,
                    ts.label        AS substage_label,
                    tst.name        AS stage_name
                FROM sessions se
                LEFT JOIN subjects           su  ON su.id  = se.subject_id
                LEFT JOIN training_substages ts  ON ts.id  = se.substage_id
                LEFT JOIN training_stages    tst ON tst.id = ts.stage_id
                ORDER BY se.started_at DESC
                LIMIT 100
            """)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
    finally:
        conn.close()

    return jsonify([dict(zip(cols, r)) for r in rows])
