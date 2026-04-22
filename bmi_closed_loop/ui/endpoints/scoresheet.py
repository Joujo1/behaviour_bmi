"""
Scoresheet endpoints.

One scoresheet_entries row is auto-created when a session is opened.
Researchers fill in scores, weight, and notes via the scoresheet UI.
Export downloads a filled copy of the .xlsx template.
"""
import logging
import os
from datetime import date, datetime

import psycopg2
import psycopg2.extras
from flask import Blueprint, abort, jsonify, render_template, request

import config

scoresheet_bp = Blueprint("scoresheet", __name__)
_log = logging.getLogger("scoresheet")


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


@scoresheet_bp.get("/scoresheet-page")
def scoresheet_page():
    return render_template("scoresheet.html")


@scoresheet_bp.get("/subjects/<int:subject_id>/scoresheet")
def list_scoresheet(subject_id: int):
    """Return all entries for a subject, newest first."""
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, subject_id, session_id, entry_date, entry_time,
                       days_in_experiment, procedure_nr, procedure_details,
                       weight_g, weight_change_pct,
                       score_a, score_b, score_c, score_d,
                       medication, remarks, created_at
                FROM scoresheet_entries
                WHERE subject_id = %s
                ORDER BY entry_date DESC, entry_time DESC
                """,
                (subject_id,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    for r in rows:
        r["entry_date"] = r["entry_date"].isoformat() if r["entry_date"] else None
        r["entry_time"] = str(r["entry_time"])[:5] if r["entry_time"] else None
        r["created_at"] = r["created_at"].isoformat() if r["created_at"] else None
    return jsonify(rows)


@scoresheet_bp.post("/subjects/<int:subject_id>/scoresheet")
def create_scoresheet(subject_id: int):
    """Create a welfare entry manually (auto-creation happens via auto_create_scoresheet_entry)."""
    body = request.get_json(force=True) or {}
    conn = _get_db()
    try:
        with conn:
            entry_id = _insert_scoresheet_entry(
                conn, subject_id,
                session_id=body.get("session_id"),
                weight_g=body.get("weight_g"),
                allow_duplicate=True,
            )
    finally:
        conn.close()
    return jsonify({"ok": True, "id": entry_id})


@scoresheet_bp.patch("/scoresheet/<int:entry_id>")
def patch_scoresheet(entry_id: int):
    """Update editable fields of a welfare entry."""
    body = request.get_json(force=True) or {}
    allowed = {
        "procedure_nr", "procedure_details", "weight_g",
        "score_a", "score_b", "score_c", "score_d",
        "medication", "remarks",
    }
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return jsonify({"ok": False, "msg": "no updatable fields provided"}), 400

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                # Fetch current subject_id + weight for reference_weight logic
                cur.execute(
                    "SELECT subject_id, weight_g FROM scoresheet_entries WHERE id = %s",
                    (entry_id,),
                )
                row = cur.fetchone()
                if row is None:
                    abort(404)
                subject_id, old_weight_g = row

                if "weight_g" in updates and updates["weight_g"] is not None:
                    _update_weight_change(cur, subject_id, entry_id, updates["weight_g"])

                set_clause = ", ".join(f"{k} = %s" for k in updates)
                cur.execute(
                    f"UPDATE scoresheet_entries SET {set_clause} WHERE id = %s",
                    list(updates.values()) + [entry_id],
                )
    finally:
        conn.close()

    return jsonify({"ok": True})


@scoresheet_bp.post("/subjects/<int:subject_id>/scoresheet/export")
def export_scoresheet(subject_id: int):
    """Fill the scoresheet template and save it to NAS_BASE_PATH/scoresheets/<code>.xlsx."""
    try:
        import openpyxl
    except ImportError:
        return jsonify({"ok": False, "msg": "openpyxl not installed on server"}), 500

    template_path = getattr(config, "SCORESHEET_TEMPLATE_PATH", None)
    if not template_path:
        return jsonify({"ok": False, "msg": "SCORESHEET_TEMPLATE_PATH not set in config"}), 500

    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT code, sex, dob, species, strain, experiment_nr,
                       reference_weight_g, enrolled_at
                FROM subjects WHERE id = %s
                """,
                (subject_id,),
            )
            subject = cur.fetchone()
            if subject is None:
                abort(404)
            subject = dict(subject)

            cur.execute(
                """
                SELECT entry_date, entry_time, days_in_experiment,
                       procedure_nr, procedure_details,
                       weight_g, weight_change_pct,
                       score_a, score_b, score_c, score_d,
                       medication, remarks
                FROM scoresheet_entries
                WHERE subject_id = %s
                ORDER BY entry_date ASC, entry_time ASC
                """,
                (subject_id,),
            )
            entries = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    wb = openpyxl.load_workbook(template_path)
    ws = wb.active

    def _safe_write(row, col, value):
        """Write to a cell only if it is not a MergedCell (read-only proxy)."""
        cell = ws.cell(row=row, column=col)
        if hasattr(cell, "value") and not isinstance(cell, openpyxl.cell.cell.MergedCell):
            cell.value = value

    # Row 2: keep exact label text from template, append value after it.
    dob_str = subject["dob"].isoformat() if subject["dob"] else ""
    species_str = "/".join(filter(None, [subject.get("species"), subject.get("strain"), subject.get("sex")]))
    _safe_write(2, 1,  f"Animal ID & Cage nr: {subject['code']}")
    _safe_write(2, 6,  f"Date of birth: {dob_str}")
    _safe_write(2, 9,  f"Experiment Nr: {subject.get('experiment_nr') or ''}")
    _safe_write(2, 12, f"Species, strain & sex: {species_str}")
    # E2 (Experimenter) and P2 (Page Nr) left as-is — not in our data

    # F4 = reference weight value; E4 "Reference weight:" label stays untouched
    ref_w = subject.get("reference_weight_g")
    if ref_w is not None:
        _safe_write(4, 6, float(ref_w))

    # Data rows start at row 5; row 17 is the divider — skip it.
    # Column map: A=1 Date, B=2 Time, C=3 Day, D=4 Proc nr, E=5 Details,
    #   F=6 Weight, G=7 ScoreA, H=8 B, I=9 C, J=10 D, K=11 Total, L=12 Medication
    # Remarks column varies by row:
    #   rows 5–16 and 18–21 → P (col 16)
    #   rows 22–23          → M (col 13, top-left of their respective merges)
    #   rows 24–30          → not writable (merged into M23:Q30)
    DIVIDER_ROW = 17
    row = 5
    for e in entries:
        if row == DIVIDER_ROW:
            row += 1

        d = e["entry_date"]
        date_str = f"{d.day:02d}/{d.month:02d}/{str(d.year)[2:]}" if d else ""
        _safe_write(row, 1,  date_str)
        _safe_write(row, 2,  str(e["entry_time"])[:5] if e["entry_time"] else "")
        _safe_write(row, 3,  e["days_in_experiment"])
        _safe_write(row, 4,  e["procedure_nr"] or "")
        _safe_write(row, 5,  e["procedure_details"] or "")
        weight_str = ""
        if e["weight_g"] is not None:
            weight_str = f"{e['weight_g']}g"
            if e["weight_change_pct"] is not None:
                weight_str += f" / {float(e['weight_change_pct']):+.1f}%"
        _safe_write(row, 6,  weight_str)
        sa = int(e["score_a"] or 0)
        sb = int(e["score_b"] or 0)
        sc = int(e["score_c"] or 0)
        sd = int(e["score_d"] or 0)
        _safe_write(row, 7,  sa)
        _safe_write(row, 8,  sb)
        _safe_write(row, 9,  sc)
        _safe_write(row, 10, sd)
        _safe_write(row, 11, sa + sb + sc + sd)
        _safe_write(row, 12, e["medication"] or "")
        remarks = e["remarks"] or ""
        if row <= 16 or 18 <= row <= 21:
            _safe_write(row, 16, remarks)   # column P
        elif row in (22, 23):
            _safe_write(row, 13, remarks)   # column M (top-left of merge)
        # rows 24–30: P is merged into M23:Q30 — not writable
        row += 1

    out_dir = os.path.join(config.NAS_BASE_PATH, "scoresheets")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{subject['code']}.xlsx")
    wb.save(out_path)

    _log.info("Scoresheet saved to %s", out_path)
    return jsonify({"ok": True, "path": out_path})


def auto_create_scoresheet_entry(subject_id: int, session_id: int, conn) -> int:
    return _insert_scoresheet_entry(conn, subject_id, session_id=session_id)


def _insert_scoresheet_entry(conn, subject_id: int, session_id=None,
                              weight_g=None, allow_duplicate: bool = False) -> int:
    today = date.today()
    with conn.cursor() as cur:
        if not allow_duplicate:
            if session_id is not None:
                cur.execute(
                    "SELECT id FROM scoresheet_entries WHERE session_id = %s LIMIT 1",
                    (session_id,),
                )
            else:
                cur.execute(
                    "SELECT id FROM scoresheet_entries WHERE subject_id = %s AND entry_date = %s AND session_id IS NULL LIMIT 1",
                    (subject_id, today),
                )
            existing = cur.fetchone()
            if existing:
                return existing[0]

        cur.execute("SELECT enrolled_at, reference_weight_g FROM subjects WHERE id = %s", (subject_id,))
        srow = cur.fetchone()
        enrolled_at = srow[0] if srow else None
        reference_weight_g = srow[1] if srow else None
        days = (today - enrolled_at.date()).days + 1 if enrolled_at else None

        weight_change_pct = None
        if weight_g is not None and reference_weight_g is not None and float(reference_weight_g) != 0:
            weight_change_pct = (float(weight_g) - float(reference_weight_g)) / float(reference_weight_g) * 100

        cur.execute(
            """
            INSERT INTO scoresheet_entries
                (subject_id, session_id, entry_date, entry_time,
                 days_in_experiment, weight_g, weight_change_pct,
                 procedure_nr, procedure_details, medication, remarks)
            VALUES (%s, %s, %s, CURRENT_TIME, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (subject_id, session_id, today, days, weight_g, weight_change_pct,
             "-", "-", "-", "-"),
        )
        entry_id = cur.fetchone()[0]

        if weight_g is not None and reference_weight_g is None:
            cur.execute(
                "UPDATE subjects SET reference_weight_g = %s WHERE id = %s",
                (weight_g, subject_id),
            )

        _log.info("Scoresheet entry %d created for subject %d (session %s)", entry_id, subject_id, session_id)
        return entry_id


def _update_weight_change(cur, subject_id: int, entry_id: int, weight_g: float) -> None:
    """Recompute weight_change_pct and update the entry; also seed reference_weight_g if missing."""
    cur.execute("SELECT reference_weight_g FROM subjects WHERE id = %s", (subject_id,))
    row = cur.fetchone()
    reference_weight_g = row[0] if row else None

    if reference_weight_g is None:
        cur.execute("UPDATE subjects SET reference_weight_g = %s WHERE id = %s", (weight_g, subject_id))
        reference_weight_g = weight_g

    pct = None
    if float(reference_weight_g) != 0:
        pct = (float(weight_g) - float(reference_weight_g)) / float(reference_weight_g) * 100

    cur.execute(
        "UPDATE scoresheet_entries SET weight_change_pct = %s WHERE id = %s",
        (pct, entry_id),
    )
