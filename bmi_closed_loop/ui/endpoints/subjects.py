"""
Subject (animal) CRUD endpoints.

Subjects are the animals under experiment. Each subject tracks its current
substage, welfare fields, and side-bias algorithm. Deletion is guarded by
session references; moving a subject's substage live-switches the running trial
loop if a session is active.
"""

import datetime
import logging

import psycopg2
import psycopg2.extras
from flask import Blueprint, abort, jsonify, render_template, request

import config
from ui.bias_algorithms import REGISTRY as _BIAS_REGISTRY
from ui.cage_runner import runners

subjects_bp = Blueprint("subjects", __name__)
logger = logging.getLogger(__name__)


def _get_db() -> psycopg2.extensions.connection:
    return psycopg2.connect(config.POSTGRES_DSN)


def _serialize(d: dict) -> dict:
    for k, v in d.items():
        if isinstance(v, (datetime.date, datetime.datetime)):
            d[k] = v.isoformat()
    return d


@subjects_bp.get("/bias-algorithms")
def list_bias_algorithms():
    """Return available bias correction algorithms for the UI dropdown."""
    return jsonify([{"value": k, "label": v.label} for k, v in _BIAS_REGISTRY.items()])


@subjects_bp.get("/subjects-page")
def subjects_page():
    return render_template("subjects.html")


@subjects_bp.get("/subjects")
def list_subjects():
    """List all subjects with their current substage label."""
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    s.id,
                    s.code,
                    s.sex,
                    s.dob,
                    s.weight_g,
                    s.water_restricted,
                    s.enrolled_at,
                    s.notes,
                    s.current_substage_id,
                    s.species,
                    s.strain,
                    s.experiment_nr,
                    s.reference_weight_g,
                    s.side_bias_alg,
                    ts.label        AS substage_label,
                    tst.name        AS stage_name
                FROM subjects s
                LEFT JOIN training_substages ts  ON ts.id = s.current_substage_id
                LEFT JOIN training_stages    tst ON tst.id = ts.stage_id
                ORDER BY s.code
            """)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
    finally:
        conn.close()

    return jsonify([_serialize(dict(zip(cols, r))) for r in rows])


@subjects_bp.post("/subjects")
def create_subject():
    """Create a new subject."""
    body = request.get_json(force=True) or {}
    code = body.get("code", "").strip()
    if not code:
        return jsonify({"ok": False, "msg": "code is required"}), 400

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO subjects
                        (code, sex, dob, weight_g, water_restricted, current_substage_id,
                         notes, species, strain, experiment_nr)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    code,
                    body.get("sex"),
                    body.get("dob"),
                    body.get("weight_g"),
                    bool(body.get("water_restricted", False)),
                    body.get("current_substage_id"),
                    body.get("notes"),
                    body.get("species"),
                    body.get("strain"),
                    body.get("experiment_nr"),
                ))
                subject_id = cur.fetchone()[0]
    except psycopg2.errors.UniqueViolation:
        return jsonify({"ok": False, "msg": f"subject '{code}' already exists"}), 409
    finally:
        conn.close()

    logger.info("Created subject %s (id=%d)", code, subject_id)
    return jsonify({"ok": True, "id": subject_id})


@subjects_bp.get("/subjects/<int:subject_id>")
def get_subject(subject_id: int):
    """Return subject detail plus recent trial performance on current substage."""
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    s.*,
                    ts.label        AS substage_label,
                    ts.advance_criteria,
                    ts.fallback_criteria,
                    tst.name        AS stage_name
                FROM subjects s
                LEFT JOIN training_substages ts  ON ts.id = s.current_substage_id
                LEFT JOIN training_stages    tst ON tst.id = ts.stage_id
                WHERE s.id = %s
            """, (subject_id,))
            row = cur.fetchone()
            if row is None:
                abort(404)
            subject = dict(row)

            substage_id = subject.get("current_substage_id")
            if substage_id is not None:
                cur.execute("""
                    SELECT
                        COUNT(*)                                            AS total,
                        COUNT(*) FILTER (WHERE outcome = 'correct')         AS correct,
                        COUNT(*) FILTER (WHERE outcome = 'wrong')           AS wrong,
                        COUNT(*) FILTER (WHERE outcome = 'aborted')         AS aborted
                    FROM trial_results
                    WHERE substage_id = %s
                      AND session_id IN (
                          SELECT id FROM sessions WHERE subject_id = %s
                      )
                """, (substage_id, subject_id))
                subject["stats"] = dict(cur.fetchone())
            else:
                subject["stats"] = None

    finally:
        conn.close()

    return jsonify(_serialize(subject))


@subjects_bp.patch("/subjects/<int:subject_id>")
def update_subject(subject_id: int):
    """Update editable fields of a subject."""
    body = request.get_json(force=True) or {}
    allowed = {
        "code", "sex", "dob", "weight_g", "water_restricted",
        "species", "strain", "experiment_nr", "notes", "reference_weight_g",
        "side_bias_alg",
    }
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return jsonify({"ok": False, "msg": "no updatable fields provided"}), 400

    if "side_bias_alg" in updates:
        valid_algs = {"none"} | set(_BIAS_REGISTRY.keys())
        if updates["side_bias_alg"] not in valid_algs:
            return jsonify({"ok": False, "msg": f"unknown bias algorithm '{updates['side_bias_alg']}'"}), 400

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                set_clause = ", ".join(f"{k} = %s" for k in updates)
                cur.execute(
                    f"UPDATE subjects SET {set_clause} WHERE id = %s RETURNING id",
                    list(updates.values()) + [subject_id],
                )
                if cur.fetchone() is None:
                    abort(404)
    except psycopg2.errors.UniqueViolation:
        return jsonify({"ok": False, "msg": "subject code already exists"}), 409
    finally:
        conn.close()

    logger.info("Subject %d updated: %s", subject_id, list(updates.keys()))
    return jsonify({"ok": True})


@subjects_bp.patch("/subjects/<int:subject_id>/substage")
def set_substage(subject_id: int):
    """Manually move a subject to a different substage."""
    body = request.get_json(force=True) or {}
    substage_id = body.get("substage_id")
    if substage_id is None:
        return jsonify({"ok": False, "msg": "substage_id is required"}), 400

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE subjects SET current_substage_id = %s, substage_entered_at = NOW() WHERE id = %s RETURNING id",
                    (substage_id, subject_id),
                )
                if cur.fetchone() is None:
                    abort(404)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT task_config FROM training_substages WHERE id = %s",
                (substage_id,),
            )
            tc_row = cur.fetchone()

        with conn.cursor() as cur:
            cur.execute(
                "SELECT cage_id FROM sessions WHERE subject_id = %s AND closed_at IS NULL ORDER BY started_at DESC LIMIT 1",
                (subject_id,),
            )
            sess_row = cur.fetchone()
    finally:
        conn.close()

    live_switched = False
    cage_id = sess_row[0] if sess_row else None
    if cage_id and tc_row and tc_row[0].get("base_iti_s") is not None:
        runner = runners.get(cage_id)
        if runner:
            live_switched = runner.switch_substage(tc_row[0], substage_id)

    logger.info("Subject %d manually moved to substage %d (cage=%s live_switched=%s)",
                subject_id, substage_id, cage_id, live_switched)
    return jsonify({"ok": True, "live_switched": live_switched})


@subjects_bp.delete("/subjects/<int:subject_id>")
def delete_subject(subject_id: int):
    """Delete a subject. Fails if any sessions reference it."""
    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM sessions WHERE subject_id = %s", (subject_id,))
                if cur.fetchone()[0] > 0:
                    return jsonify({
                        "ok": False,
                        "msg": "Cannot delete: subject has sessions.",
                    }), 409
                cur.execute("DELETE FROM subjects WHERE id = %s RETURNING id", (subject_id,))
                if cur.fetchone() is None:
                    abort(404)
    finally:
        conn.close()

    logger.info("Subject %d deleted", subject_id)
    return jsonify({"ok": True})
