import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, render_template, request

import config

builder_bp = Blueprint("builder", __name__)


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


@builder_bp.get("/builder")
def builder_page():
    return render_template("builder.html")


@builder_bp.post("/trial-configs")
def save_trial_config():
    body = request.get_json(force=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "msg": "name is required"}), 400
    definition = body.get("definition")
    if not definition:
        return jsonify({"ok": False, "msg": "definition is required"}), 400

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trial_configs (name, description, definition)
                    VALUES (%s, %s, %s) RETURNING id
                    """,
                    (name, body.get("description", ""), psycopg2.extras.Json(definition)),
                )
                config_id = cur.fetchone()[0]
    finally:
        conn.close()

    return jsonify({"ok": True, "id": config_id})
