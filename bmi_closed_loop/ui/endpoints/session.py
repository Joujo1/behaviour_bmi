import psycopg2
from flask import Blueprint, jsonify, request

import config

session_bp = Blueprint("session", __name__)


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


@session_bp.post("/session/open")
def open_session():
    """Researcher opens a new session."""
    body = request.get_json(force=True) or {}

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO sessions (researcher, notes) VALUES (%s, %s) RETURNING id",
                    (body.get("researcher"), body.get("notes")),
                )
                session_id = cur.fetchone()[0]
    finally:
        conn.close()

    return jsonify({"status": "ok", "session_id": session_id})


@session_bp.post("/session/<int:session_id>/close")
def close_session(session_id: int):
    """Researcher closes an open session."""
    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE sessions SET closed_at = NOW() WHERE id = %s",
                    (session_id,),
                )
    finally:
        conn.close()

    return jsonify({"status": "ok"})
