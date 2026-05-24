"""
Trial definition builder endpoint.

Provides a single endpoint to save the full trial definition (task_config JSON)
for an existing substage.  The task_config is the JSON sent verbatim to the Pi
and also used by the runner to expand click trains.
"""

import logging

import psycopg2
import psycopg2.extras
from flask import Blueprint, abort, jsonify, request

import config

builder_bp = Blueprint("builder", __name__)
logger = logging.getLogger(__name__)


def _get_db() -> psycopg2.extensions.connection:
    return psycopg2.connect(config.POSTGRES_DSN)


@builder_bp.patch("/training-substages/<int:substage_id>/task-config")
def save_task_config(substage_id: int):
    """Save the trial definition (task_config) for an existing substage."""
    body = request.get_json(force=True) or {}
    definition = body.get("definition")
    if not definition:
        return jsonify({"ok": False, "msg": "definition is required"}), 400

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE training_substages SET task_config = %s WHERE id = %s RETURNING id",
                    (psycopg2.extras.Json(definition), substage_id),
                )
                if cur.fetchone() is None:
                    abort(404)
    finally:
        conn.close()

    logger.info("task_config saved for substage %d", substage_id)
    return jsonify({"ok": True})
