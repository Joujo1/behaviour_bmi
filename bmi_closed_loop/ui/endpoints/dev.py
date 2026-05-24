"""
Development-only endpoints.

These endpoints are only safe to expose in a local dev environment.
They provide destructive operations (table truncation) for resetting
the database between test runs.
"""

import logging

import psycopg2
from flask import Blueprint, jsonify

import config

dev_bp = Blueprint("dev", __name__)
logger = logging.getLogger(__name__)

_ALLOWED_TABLES = {
    "trial_results", "recordings", "sessions",
    "subjects", "training_substages", "training_stages",
    "scoresheet_entries",
}


def _get_db() -> psycopg2.extensions.connection:
    return psycopg2.connect(config.POSTGRES_DSN)


@dev_bp.post("/dev/truncate/<table>")
def truncate_table(table: str):
    if table not in _ALLOWED_TABLES:
        return jsonify({"ok": False, "msg": f"unknown table '{table}'"}), 400
    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(f"TRUNCATE {table} RESTART IDENTITY CASCADE")
    finally:
        conn.close()
    logger.warning("Table '%s' truncated (dev endpoint)", table)
    return jsonify({"ok": True, "msg": f"{table} truncated"})
