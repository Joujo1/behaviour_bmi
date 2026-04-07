import psycopg2
from flask import Blueprint, jsonify

import config

dev_bp = Blueprint("dev", __name__)

_ALLOWED_TABLES = {"trial_results", "recordings"}


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


@dev_bp.post("/dev/truncate/<table>")
def truncate_table(table: str):
    if table not in _ALLOWED_TABLES:
        return jsonify({"ok": False, "msg": f"unknown table '{table}'"}), 400
    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(f"TRUNCATE {table} RESTART IDENTITY")
    finally:
        conn.close()
    return jsonify({"ok": True, "msg": f"{table} truncated"})
