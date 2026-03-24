import psycopg2
from flask import Blueprint, abort, jsonify, request

import config

trial_bp = Blueprint("trial", __name__)


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


@trial_bp.get("/cage/<int:cage_id>/trial")
def get_next_trial(cage_id: int):
    """Pi polls this to get the next trial config."""
    if not (0 <= cage_id < config.N_CAGES):
        abort(404)

    # TODO: implement trial queue logic
    # For now returns an empty placeholder so the Pi can poll without error.
    return jsonify({"cage_id": cage_id, "trial": None})


@trial_bp.post("/cage/<int:cage_id>/trial/<int:trial_id>/result")
def post_trial_result(cage_id: int, trial_id: int):
    """Pi posts the result of a completed trial."""
    if not (0 <= cage_id < config.N_CAGES):
        abort(404)

    result = request.get_json(force=True)
    if result is None:
        abort(400)

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE trials SET result = %s WHERE id = %s AND cage_id = %s",
                    (psycopg2.extras.Json(result), trial_id, cage_id),
                )
    finally:
        conn.close()

    return jsonify({"status": "ok"})
