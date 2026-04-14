import logging

import psycopg2
from flask import Blueprint, jsonify, request

import config

session_bp = Blueprint("session", __name__)
_log = logging.getLogger("session")


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


@session_bp.post("/session/open")
def open_session():
    """
    Open a new session.

    Body (all optional except researcher):
        researcher    str   — who is running the session
        subject_id    int   — animal ID; if provided, substage_id is snapshotted automatically
        weight_g      float — animal weight at session start
        water_ml      float — water given
        notes         str
    """
    body = request.get_json(force=True) or {}

    subject_id  = body.get("subject_id")
    substage_id = None

    if subject_id is not None:
        conn = _get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT current_substage_id FROM subjects WHERE id = %s",
                    (subject_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row is None:
            return jsonify({"ok": False, "msg": f"subject {subject_id} not found"}), 404
        substage_id = row[0]

    cage_id = body.get("cage_id")

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                # Compute per-subject session number atomically inside the transaction
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
    finally:
        conn.close()

    _log.info("Session %d opened (cage=%s subject=%s substage=%s session_number=%s)",
              session_id, cage_id, subject_id, substage_id, session_number)
    return jsonify({"ok": True, "session_id": session_id, "session_number": session_number,
                    "substage_id": substage_id})


@session_bp.post("/session/<int:session_id>/close")
def close_session(session_id: int):
    """Close an open session. Optionally update weight and water given."""
    body = request.get_json(force=True) or {}

    fields = ["closed_at = NOW()"]
    values = []

    if "weight_g" in body:
        fields.append("weight_g = %s"); values.append(body["weight_g"])
    if "water_ml" in body:
        fields.append("water_ml = %s"); values.append(body["water_ml"])

    values.append(session_id)
    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE sessions SET {', '.join(fields)} WHERE id = %s",
                    values,
                )
    finally:
        conn.close()

    _log.info("Session %d closed", session_id)
    return jsonify({"ok": True})


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
