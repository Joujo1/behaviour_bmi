"""
Metrics and DB overview endpoints.
"""
from datetime import datetime, timezone
import logging

import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, render_template, request

import config

metrics_bp = Blueprint("metrics", __name__)
_log = logging.getLogger("metrics")


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


@metrics_bp.get("/metrics-page")
def metrics_page():
    return render_template("metrics.html")


# Legacy
@metrics_bp.get("/metrics")
def cage_metrics():
    """Per-cage trial metrics aggregated from trial_results."""
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    cage_id,
                    COUNT(*)                                                   AS total,
                    COUNT(*) FILTER (WHERE outcome = 'correct')                AS successes,
                    COUNT(*) FILTER (WHERE outcome = 'wrong')                  AS failures,
                    COUNT(*) FILTER (WHERE outcome = 'aborted')                AS aborted_count,
                    AVG(
                        CASE WHEN jsonb_array_length(events) > 0
                             THEN (events -> -1 ->> 't')::float
                        END
                    ) FILTER (WHERE outcome = 'correct')                       AS avg_success_s,
                    AVG(
                        CASE WHEN jsonb_array_length(events) > 0
                             THEN (events -> -1 ->> 't')::float
                        END
                    ) FILTER (WHERE outcome = 'wrong')                         AS avg_fail_s,
                    (array_agg(outcome ORDER BY completed_at DESC))[1]         AS last_outcome
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




@metrics_bp.get("/metrics/animals")
def animal_metrics():
    """
    Per-subject summary with rolling last-N % correct.
    ?n=20  — window size (default 20)
    """
    n = max(1, min(request.args.get("n", 20, type=int), 10000))

    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                WITH ranked AS (
                    SELECT
                        se.subject_id,
                        tr.outcome,
                        ROW_NUMBER() OVER (
                            PARTITION BY se.subject_id
                            ORDER BY tr.completed_at DESC
                        ) AS rn
                    FROM trial_results tr
                    JOIN sessions se ON se.id = tr.session_id
                    WHERE se.subject_id IS NOT NULL
                ),
                last_n AS (
                    SELECT
                        subject_id,
                        COUNT(*) FILTER (WHERE outcome = 'correct')            AS last_n_correct,
                        COUNT(*) FILTER (WHERE outcome IN ('correct','wrong'))  AS last_n_decided
                    FROM ranked
                    WHERE rn <= %(n)s
                    GROUP BY subject_id
                ),
                sess AS (
                    SELECT subject_id,
                           COUNT(*)        AS total_sessions,
                           MAX(started_at) AS last_session_at
                    FROM sessions
                    WHERE subject_id IS NOT NULL
                    GROUP BY subject_id
                )
                SELECT
                    su.id,
                    su.code,
                    su.sex,
                    su.enrolled_at,
                    tst.name           AS stage_name,
                    ts.label           AS substage_label,
                    ts.substage_number,
                    COUNT(tr.id)                                               AS total_trials,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'correct')         AS correct,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'wrong')           AS wrong,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'aborted')         AS aborted,
                    sess.total_sessions,
                    sess.last_session_at,
                    ln.last_n_correct,
                    ln.last_n_decided
                FROM subjects su
                LEFT JOIN training_substages ts   ON ts.id  = su.current_substage_id
                LEFT JOIN training_stages    tst  ON tst.id = ts.stage_id
                LEFT JOIN sessions           se   ON se.subject_id = su.id
                LEFT JOIN trial_results      tr   ON tr.session_id = se.id
                LEFT JOIN sess                    ON sess.subject_id = su.id
                LEFT JOIN last_n             ln   ON ln.subject_id  = su.id
                GROUP BY su.id, su.code, su.sex, su.enrolled_at,
                         tst.name, ts.label, ts.substage_number,
                         sess.total_sessions, sess.last_session_at,
                         ln.last_n_correct, ln.last_n_decided
                ORDER BY su.code
            """, {"n": n})
            rows = cur.fetchall()
    finally:
        conn.close()

    now = datetime.now(timezone.utc)
    result = []
    for row in rows:
        d = dict(row)
        decided = (d["correct"] or 0) + (d["wrong"] or 0)
        d["success_pct"] = round(100 * d["correct"] / decided, 1) if decided > 0 else None
        ln_d = d["last_n_decided"] or 0
        ln_c = d["last_n_correct"] or 0
        d["last_n_pct"] = round(100 * ln_c / ln_d, 1) if ln_d > 0 else None
        if d["enrolled_at"]:
            enrolled = d["enrolled_at"]
            if enrolled.tzinfo is None:
                enrolled = enrolled.replace(tzinfo=timezone.utc)
            d["days_enrolled"] = (now - enrolled).days
            d["enrolled_at"]   = enrolled.isoformat()
        else:
            d["days_enrolled"] = None
        if d["last_session_at"]:
            ls = d["last_session_at"]
            if ls.tzinfo is None:
                ls = ls.replace(tzinfo=timezone.utc)
            d["last_session_at"] = ls.isoformat()
        result.append(d)

    return jsonify(result)


@metrics_bp.get("/metrics/learning-curve")
def learning_curve():
    """
    Per-session % correct for learning curve plotting.
    ?subject_id=X  — filter to one subject (omit for all)
    """
    subject_id = request.args.get("subject_id", type=int)

    conditions = ["se.session_number IS NOT NULL", "se.subject_id IS NOT NULL"]
    params = {}
    if subject_id:
        conditions.append("se.subject_id = %(subject_id)s")
        params["subject_id"] = subject_id

    where = " AND ".join(conditions)

    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT
                    su.id               AS subject_id,
                    su.code             AS subject_code,
                    se.session_number,
                    se.started_at::date AS session_date,
                    ts.label            AS substage_label,
                    COUNT(tr.id)                                              AS total,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'correct')        AS correct,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'wrong')          AS wrong,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'aborted')        AS aborted
                FROM sessions se
                JOIN subjects su ON su.id = se.subject_id
                LEFT JOIN trial_results      tr ON tr.session_id = se.id
                LEFT JOIN training_substages ts ON ts.id = se.substage_id
                WHERE {where}
                GROUP BY su.id, su.code, se.session_number, se.started_at::date, ts.label
                ORDER BY su.code, se.session_number
            """, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        d = dict(row)
        decided = (d["correct"] or 0) + (d["wrong"] or 0)
        d["pct_correct"] = round(100 * d["correct"] / decided, 1) if decided > 0 else None
        d["session_date"] = str(d["session_date"]) if d["session_date"] else None
        result.append(d)

    return jsonify(result)


@metrics_bp.get("/metrics/sessions")
def session_log():
    """
    Filterable session log.
    ?subject_id=X&cage_id=Y&from=YYYY-MM-DD&to=YYYY-MM-DD&limit=50
    """
    subject_id = request.args.get("subject_id", type=int)
    cage_id    = request.args.get("cage_id",    type=int)
    from_date  = request.args.get("from")
    to_date    = request.args.get("to")
    limit      = min(request.args.get("limit", 50, type=int), 500)

    conditions = ["1=1"]
    params     = {"limit": limit}

    if subject_id:
        conditions.append("se.subject_id = %(subject_id)s")
        params["subject_id"] = subject_id
    if cage_id:
        conditions.append("se.cage_id = %(cage_id)s")
        params["cage_id"] = cage_id
    if from_date:
        conditions.append("se.started_at >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("se.started_at < %(to_date)s::date + interval '1 day'")
        params["to_date"] = to_date

    where = " AND ".join(conditions)

    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT
                    se.id,
                    se.session_number,
                    se.cage_id,
                    se.started_at,
                    se.closed_at,
                    EXTRACT(EPOCH FROM (se.closed_at - se.started_at)) AS duration_s,
                    se.researcher,
                    se.weight_g,
                    se.water_ml,
                    su.code             AS subject_code,
                    ts.label            AS substage_label,
                    tst.name            AS stage_name,
                    COUNT(tr.id)                                               AS total_trials,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'correct')         AS correct,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'wrong')           AS wrong,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'aborted')         AS aborted
                FROM sessions se
                LEFT JOIN subjects           su  ON su.id  = se.subject_id
                LEFT JOIN training_substages ts  ON ts.id  = se.substage_id
                LEFT JOIN training_stages    tst ON tst.id = ts.stage_id
                LEFT JOIN trial_results      tr  ON tr.session_id = se.id
                WHERE {where}
                GROUP BY se.id, su.code, ts.label, tst.name
                ORDER BY se.started_at DESC
                LIMIT %(limit)s
            """, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        d = dict(row)
        decided = (d["correct"] or 0) + (d["wrong"] or 0)
        d["pct_correct"] = round(100 * d["correct"] / decided, 1) if decided > 0 else None
        d["duration_s"]  = round(float(d["duration_s"]), 0) if d["duration_s"] else None
        for k in ("started_at", "closed_at"):
            if d[k]:
                d[k] = d[k].isoformat()
        result.append(d)

    return jsonify(result)


@metrics_bp.get("/metrics/trials")
def session_trials():
    """
    Individual trial results for one session, in order.
    ?session_id=X  (required)
    """
    session_id = request.args.get("session_id", type=int)
    if not session_id:
        return jsonify([])

    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    ROW_NUMBER() OVER (ORDER BY tr.completed_at) AS trial_num,
                    tr.outcome,
                    tr.correct_side,
                    tr.completed_at,
                    ts.label AS substage_label,
                    CASE WHEN jsonb_array_length(tr.events) > 0
                         THEN (tr.events -> -1 ->> 't')::float
                    END AS duration_s
                FROM trial_results tr
                LEFT JOIN training_substages ts ON ts.id = tr.substage_id
                WHERE tr.session_id = %(session_id)s
                ORDER BY tr.completed_at
            """, {"session_id": session_id})
            rows = cur.fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        d = dict(row)
        if d["completed_at"]:
            d["completed_at"] = d["completed_at"].isoformat()
        if d["duration_s"] is not None:
            d["duration_s"] = round(float(d["duration_s"]), 2)
        result.append(d)

    return jsonify(result)


@metrics_bp.get("/metrics/side-bias")
def side_bias():
    """
    Left/right trial counts and correct/wrong breakdown per side.
    ?subject_id=X  (required)
    """
    subject_id = request.args.get("subject_id", type=int)
    if not subject_id:
        return jsonify([])

    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    tr.correct_side,
                    COUNT(*)                                           AS total,
                    COUNT(*) FILTER (WHERE tr.outcome = 'correct')    AS correct,
                    COUNT(*) FILTER (WHERE tr.outcome = 'wrong')      AS wrong
                FROM trial_results tr
                JOIN sessions se ON se.id = tr.session_id
                WHERE se.subject_id = %(subject_id)s
                  AND tr.correct_side IS NOT NULL
                  AND tr.outcome IN ('correct', 'wrong')
                GROUP BY tr.correct_side
                ORDER BY tr.correct_side
            """, {"subject_id": subject_id})
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    return jsonify(rows)


@metrics_bp.get("/metrics/dwell")
def substage_dwell():
    """
    Time spent at each substage for a subject.
    ?subject_id=X  (required)
    """
    subject_id = request.args.get("subject_id", type=int)
    if not subject_id:
        return jsonify([])

    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    ts.id               AS substage_id,
                    ts.substage_number,
                    ts.label,
                    tst.name            AS stage_name,
                    COUNT(DISTINCT se.id)                                        AS sessions_count,
                    COUNT(tr.id)                                                 AS total_trials,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'correct')           AS correct,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'wrong')             AS wrong,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'aborted')           AS aborted,
                    MIN(se.started_at)  AS first_seen,
                    MAX(se.started_at)  AS last_seen
                FROM sessions se
                JOIN trial_results      tr  ON tr.session_id = se.id
                JOIN training_substages ts  ON ts.id  = se.substage_id
                JOIN training_stages    tst ON tst.id = ts.stage_id
                WHERE se.subject_id = %(subject_id)s
                  AND se.substage_id IS NOT NULL
                GROUP BY ts.id, ts.substage_number, ts.label, tst.name, tst.sort_order
                ORDER BY tst.sort_order, ts.substage_number
            """, {"subject_id": subject_id})
            rows = cur.fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        d = dict(row)
        decided = (d["correct"] or 0) + (d["wrong"] or 0)
        d["pct_correct"] = round(100 * d["correct"] / decided, 1) if decided > 0 else None
        for k in ("first_seen", "last_seen"):
            if d[k]:
                d[k] = d[k].isoformat()
        result.append(d)

    return jsonify(result)
