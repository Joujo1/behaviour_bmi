"""
Data export endpoints.

EXPORT_TYPES registry — adding a new export:
1. Add an entry to EXPORT_TYPES (label, description, columns, flags).
2. Add a matching branch in _run_query().

Event JSONB shapes (trial_results.events):
    {t, output, active: bool}            hardware output  (led_*, valve_*, clicks)
    {t, output: "click_fire_log",
        active: [{channel, scheduled_s,
                  fired_mono, sched_error_us}]}  per-click latency log
    {t, sensor, active: bool}            beam break/restore
    {t, from, to}                        state transition

Note: valve_close is no longer a logged event — valves close automatically after
duration_ms. Valve-close time = valve_open t + duration_ms (from trial definition).

Filters (query-string params, all optional):
    subject_ids  — repeated int  (omit = all)
    date_from    — ISO date
    date_to      — ISO date (inclusive)
    substage_id  — int
    session_id   — int
"""

import csv
import io
import logging

import psycopg2
import psycopg2.extras
from flask import Blueprint, Response, jsonify, render_template, request

import config

export_bp = Blueprint("export", __name__)
logger = logging.getLogger(__name__)


EXPORT_TYPES: dict[str, dict] = {
    "trials": {
        "label":       "Trials",
        "description": "One row per trial. Outcome, side, timing, substage — the starting point for most analyses.",
        "columns":     ["subject", "session_date", "session_nr", "stage", "substage",
                        "outcome", "correct_side", "completed_at",
                        "trial_start_us", "click_seed", "trial_id"],
        "has_substage_filter": True,
        "has_session_filter":  True,
    },
    "events": {
        "label":       "Trial Events",
        "description": (
            "One row per hardware event per trial: LED on/off, valve open, "
            "beam breaks and restores, state transitions, and click start/stop. "
            "event_type is 'output' | 'beam' | 'transition'. "
            "Per-click latency detail is in the Click Timing export. "
            "Note: valve_close time = valve_open t + duration_ms from trial definition."
        ),
        "columns":     ["subject", "session_date", "session_nr", "trial_id",
                        "stage", "substage", "trial_outcome", "correct_side",
                        "event_type", "event_category", "event_name",
                        "active", "t_from_trial_start_s"],
        "has_substage_filter": True,
        "has_session_filter":  True,
    },
    "click_timing": {
        "label":       "Click Timing",
        "description": (
            "One row per individual click fired. "
            "sched_error_us is the deviation from the scheduled fire time in microseconds — "
            "use this for click timing accuracy / latency analysis."
        ),
        "columns":     ["subject", "session_date", "session_nr", "trial_id",
                        "substage", "trial_outcome", "correct_side",
                        "channel", "scheduled_s", "sched_error_us"],
        "has_substage_filter": True,
        "has_session_filter":  True,
    },
    "substage_timeline": {
        "label":       "Substage Timeline",
        "description": (
            "One row per substage block per session — when the animal entered each substage "
            "and how it performed. Captures mid-session advancements and fallbacks."
        ),
        "columns":     ["subject", "session_date", "session_nr", "stage", "substage",
                        "first_trial_at", "last_trial_at", "n_trials", "pct_correct"],
        "has_substage_filter": False,
        "has_session_filter":  False,
    },
    "sessions": {
        "label":       "Sessions",
        "description": "One row per session with aggregate performance and welfare fields.",
        "columns":     ["subject", "session_date", "session_nr", "researcher", "cage_id",
                        "opening_stage", "opening_substage",
                        "total_trials", "correct_trials", "wrong_trials", "aborted_trials",
                        "pct_correct", "duration_min", "water_ml", "weight_g"],
        "has_substage_filter": False,
        "has_session_filter":  False,
    },
    "performance": {
        "label":       "Daily Performance",
        "description": "One row per subject per day per substage. Clean for learning-curve plots.",
        "columns":     ["subject", "date", "stage", "substage", "n_trials", "pct_correct"],
        "has_substage_filter": True,
        "has_session_filter":  False,
    },
}


def _get_db() -> psycopg2.extensions.connection:
    return psycopg2.connect(config.POSTGRES_DSN)


def _trial_filters(args, tr: str = "tr") -> tuple[str, list]:
    """WHERE conditions + params for trial_results-based queries."""
    conds, params = [], []
    subject_ids = [int(x) for x in args.getlist("subject_ids") if x]
    if subject_ids:
        conds.append("s.id = ANY(%s)");    params.append(subject_ids)
    date_from = args.get("date_from", "").strip()
    date_to   = args.get("date_to",   "").strip()
    if date_from:
        conds.append(f"{tr}.completed_at >= %s");                         params.append(date_from)
    if date_to:
        conds.append(f"{tr}.completed_at < %s::date + INTERVAL '1 day'"); params.append(date_to)
    substage_id = args.get("substage_id", "").strip()
    if substage_id:
        conds.append(f"{tr}.substage_id = %s"); params.append(int(substage_id))
    session_id = args.get("session_id", "").strip()
    if session_id:
        conds.append(f"{tr}.session_id = %s"); params.append(int(session_id))
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return where, params


def _session_filters(args) -> tuple[str, list]:
    """WHERE conditions + params for session-based queries."""
    conds, params = [], []
    subject_ids = [int(x) for x in args.getlist("subject_ids") if x]
    if subject_ids:
        conds.append("s.id = ANY(%s)"); params.append(subject_ids)
    date_from = args.get("date_from", "").strip()
    date_to   = args.get("date_to",   "").strip()
    if date_from:
        conds.append("sess.started_at >= %s");                              params.append(date_from)
    if date_to:
        conds.append("sess.started_at < %s::date + INTERVAL '1 day'");     params.append(date_to)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return where, params


def _run_query(export_type: str, args) -> tuple:
    """Execute the export query and return (cursor, connection) for streaming.

    Returns (None, None) if export_type is not recognised. The caller is
    responsible for closing both cursor and connection.
    """
    conn = _get_db()
    try:
        cur = conn.cursor()

        if export_type == "trials":
            where, params = _trial_filters(args)
            cur.execute(f"""
                SELECT
                    s.code                  AS subject,
                    sess.started_at::date   AS session_date,
                    sess.session_number     AS session_nr,
                    tst.name                AS stage,
                    ts.label                AS substage,
                    tr.outcome,
                    tr.correct_side,
                    tr.completed_at,
                    tr.trial_start_us,
                    tr.click_seed,
                    tr.trial_id
                FROM trial_results tr
                JOIN sessions sess ON sess.id = tr.session_id
                JOIN subjects  s    ON s.id   = sess.subject_id
                LEFT JOIN training_substages ts  ON ts.id  = tr.substage_id
                LEFT JOIN training_stages    tst ON tst.id = ts.stage_id
                {where}
                ORDER BY tr.completed_at
            """, params)

        elif export_type == "events":
            where, params = _trial_filters(args)
            # Excludes click_fire_log rows — active is an array there, not a bool,
            # so casting it would fail. Click detail lives in the click_timing export.
            cur.execute(f"""
                SELECT
                    s.code                AS subject,
                    sess.started_at::date AS session_date,
                    sess.session_number   AS session_nr,
                    tr.trial_id,
                    tst.name              AS stage,
                    ts.label              AS substage,
                    tr.outcome            AS trial_outcome,
                    tr.correct_side,
                    CASE
                        WHEN e ? 'sensor' THEN 'beam'
                        WHEN e ? 'from'   THEN 'transition'
                        ELSE 'output'
                    END                   AS event_type,
                    CASE
                        WHEN e ? 'sensor' THEN 'beam'
                        WHEN e ? 'from'   THEN 'transition'
                        ELSE split_part(e->>'output', '_', 1)
                    END                   AS event_category,
                    CASE
                        WHEN e ? 'sensor' THEN e->>'sensor'
                        WHEN e ? 'from'   THEN (e->>'from') || ' → ' || (e->>'to')
                        ELSE e->>'output'
                    END                   AS event_name,
                    CASE
                        WHEN e ? 'from' THEN NULL
                        ELSE (e->>'active')::boolean
                    END                   AS active,
                    round((e->>'t')::numeric, 6) AS t_from_trial_start_s
                FROM trial_results tr
                JOIN sessions sess ON sess.id = tr.session_id
                JOIN subjects  s    ON s.id   = sess.subject_id
                LEFT JOIN training_substages ts  ON ts.id  = tr.substage_id
                LEFT JOIN training_stages    tst ON tst.id = ts.stage_id
                CROSS JOIN LATERAL jsonb_array_elements(tr.events) AS e
                {where}
                AND (NOT (e ? 'output') OR e->>'output' != 'click_fire_log')
                ORDER BY tr.completed_at, t_from_trial_start_s
            """, params)

        elif export_type == "click_timing":
            where, params = _trial_filters(args)
            cur.execute(f"""
                SELECT
                    s.code                AS subject,
                    sess.started_at::date AS session_date,
                    sess.session_number   AS session_nr,
                    tr.trial_id,
                    ts.label              AS substage,
                    tr.outcome            AS trial_outcome,
                    tr.correct_side,
                    c->>'channel'         AS channel,
                    round((c->>'scheduled_s')::numeric,  9) AS scheduled_s,
                    round((c->>'sched_error_us')::numeric, 3) AS sched_error_us
                FROM trial_results tr
                JOIN sessions sess ON sess.id = tr.session_id
                JOIN subjects  s    ON s.id   = sess.subject_id
                LEFT JOIN training_substages ts  ON ts.id  = tr.substage_id
                CROSS JOIN LATERAL jsonb_array_elements(tr.events)        AS e
                CROSS JOIN LATERAL jsonb_array_elements(e->'active')      AS c
                {where}
                AND e ? 'output' AND e->>'output' = 'click_fire_log'
                AND jsonb_typeof(e->'active') = 'array'
                ORDER BY tr.completed_at, (c->>'scheduled_s')::float
            """, params)

        elif export_type == "substage_timeline":
            where, params = _trial_filters(args)
            cur.execute(f"""
                SELECT
                    s.code                AS subject,
                    sess.started_at::date AS session_date,
                    sess.session_number   AS session_nr,
                    tst.name              AS stage,
                    ts.label              AS substage,
                    MIN(tr.completed_at)  AS first_trial_at,
                    MAX(tr.completed_at)  AS last_trial_at,
                    COUNT(*) FILTER (WHERE tr.outcome IN ('correct','wrong')) AS n_trials,
                    ROUND(
                        100.0 * COUNT(*) FILTER (WHERE tr.outcome = 'correct')
                        / NULLIF(COUNT(*) FILTER (WHERE tr.outcome IN ('correct','wrong')), 0),
                    1)                    AS pct_correct
                FROM trial_results tr
                JOIN sessions sess ON sess.id = tr.session_id
                JOIN subjects  s    ON s.id   = sess.subject_id
                LEFT JOIN training_substages ts  ON ts.id  = tr.substage_id
                LEFT JOIN training_stages    tst ON tst.id = ts.stage_id
                {where}
                GROUP BY sess.id, s.code, sess.started_at, sess.session_number,
                         ts.id, ts.label, tst.id, tst.name, tst.sort_order
                ORDER BY sess.started_at, MIN(tr.completed_at)
            """, params)

        elif export_type == "sessions":
            where, params = _session_filters(args)
            cur.execute(f"""
                SELECT
                    s.code                AS subject,
                    sess.started_at::date AS session_date,
                    sess.session_number   AS session_nr,
                    sess.researcher,
                    sess.cage_id,
                    tst.name              AS opening_stage,
                    ts.label              AS opening_substage,
                    COUNT(tr.id)          AS total_trials,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'correct')  AS correct_trials,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'wrong')    AS wrong_trials,
                    COUNT(tr.id) FILTER (WHERE tr.outcome = 'aborted')  AS aborted_trials,
                    ROUND(
                        100.0 * COUNT(tr.id) FILTER (WHERE tr.outcome = 'correct')
                        / NULLIF(COUNT(tr.id) FILTER (WHERE tr.outcome IN ('correct','wrong')), 0),
                    1)                    AS pct_correct,
                    ROUND(EXTRACT(EPOCH FROM (sess.closed_at - sess.started_at)) / 60.0, 1)
                                          AS duration_min,
                    sess.water_ml,
                    sess.weight_g
                FROM sessions sess
                JOIN subjects  s    ON s.id   = sess.subject_id
                LEFT JOIN training_substages ts  ON ts.id  = sess.substage_id
                LEFT JOIN training_stages    tst ON tst.id = ts.stage_id
                LEFT JOIN trial_results tr ON tr.session_id = sess.id
                {where}
                GROUP BY sess.id, s.code, ts.label, tst.name
                ORDER BY sess.started_at
            """, params)

        elif export_type == "performance":
            where, params = _trial_filters(args)
            cur.execute(f"""
                SELECT
                    s.code                 AS subject,
                    tr.completed_at::date  AS date,
                    tst.name               AS stage,
                    ts.label               AS substage,
                    COUNT(*) FILTER (WHERE tr.outcome IN ('correct','wrong')) AS n_trials,
                    ROUND(
                        100.0 * COUNT(*) FILTER (WHERE tr.outcome = 'correct')
                        / NULLIF(COUNT(*) FILTER (WHERE tr.outcome IN ('correct','wrong')), 0),
                    1)                     AS pct_correct
                FROM trial_results tr
                JOIN sessions sess ON sess.id = tr.session_id
                JOIN subjects  s    ON s.id   = sess.subject_id
                LEFT JOIN training_substages ts  ON ts.id  = tr.substage_id
                LEFT JOIN training_stages    tst ON tst.id = ts.stage_id
                {where}
                GROUP BY s.code, tr.completed_at::date, tst.name, tst.sort_order, ts.label
                ORDER BY s.code, date, tst.sort_order
            """, params)

        else:
            cur.close()
            return None, None

        return cur, conn

    except Exception:
        conn.close()
        raise


@export_bp.get("/export-page")
def export_page():
    return render_template("export.html")


@export_bp.get("/export/types")
def list_export_types():
    """Return the EXPORT_TYPES registry for the UI dropdown."""
    return jsonify([{"value": k, **v} for k, v in EXPORT_TYPES.items()])


@export_bp.get("/export/subjects")
def list_subjects():
    """Return all subjects as id + code for the filter dropdown."""
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, code FROM subjects ORDER BY code")
            return jsonify([{"id": r[0], "code": r[1]} for r in cur.fetchall()])
    finally:
        conn.close()


@export_bp.get("/export/sessions-list")
def list_sessions():
    """Sessions for the session filter dropdown, respecting subject + date filters."""
    conn = _get_db()
    try:
        conds, params = [], []
        subject_ids = [int(x) for x in request.args.getlist("subject_ids") if x]
        if subject_ids:
            conds.append("s.id = ANY(%s)"); params.append(subject_ids)
        date_from = request.args.get("date_from", "").strip()
        date_to   = request.args.get("date_to",   "").strip()
        if date_from:
            conds.append("sess.started_at >= %s");                          params.append(date_from)
        if date_to:
            conds.append("sess.started_at < %s::date + INTERVAL '1 day'"); params.append(date_to)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT sess.id, s.code, sess.started_at::date, sess.session_number
                FROM sessions sess
                JOIN subjects s ON s.id = sess.subject_id
                {where}
                ORDER BY sess.started_at DESC
                LIMIT 200
            """, params)
            return jsonify([
                {"id": r[0], "label": f"{r[2]}  {r[1]}  #{r[3]}"}
                for r in cur.fetchall()
            ])
    finally:
        conn.close()


@export_bp.get("/export/download")
def download():
    """Stream the requested export as a CSV file attachment."""
    export_type = request.args.get("type", "")
    if export_type not in EXPORT_TYPES:
        return "Unknown export type", 400

    spec = EXPORT_TYPES[export_type]

    try:
        cur, conn = _run_query(export_type, request.args)
    except Exception as exc:
        logger.exception("Export query failed for type '%s'", export_type)
        return f"Query error: {exc}", 500

    if cur is None:
        return "Unknown export type", 400

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(spec["columns"])
        yield buf.getvalue()
        try:
            for row in cur:
                buf.seek(0); buf.truncate()
                writer.writerow(row)
                yield buf.getvalue()
        finally:
            cur.close()
            conn.close()

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={export_type}.csv"},
    )
