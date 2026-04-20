"""
Substage advancement evaluator.

After each trial completes call evaluate(subject_id, substage_id, conn).
Returns "advance", "fallback", or "stay".
"""
import logging

_log = logging.getLogger("advancement")


def evaluate(subject_id: int, substage_id: int, conn) -> str:
    """
    Check advancement and fallback criteria for a subject on a substage.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT advance_criteria, fallback_criteria,
                   advance_to_substage_id, fallback_to_substage_id
            FROM training_substages
            WHERE id = %s
        """, (substage_id,))
        row = cur.fetchone()

    if row is None:
        _log.warning("Substage %d not found — staying", substage_id)
        return "stay"

    advance_criteria, fallback_criteria, advance_target, fallback_target = row

    if advance_criteria and advance_target:
        if _meets(advance_criteria, subject_id, substage_id, conn, is_fallback=False):
            _log.info("Subject %d met advance criteria on substage %d → substage %d",
                      subject_id, substage_id, advance_target)
            return "advance"

    if fallback_criteria and fallback_target:
        if _meets(fallback_criteria, subject_id, substage_id, conn, is_fallback=True):
            _log.info("Subject %d met fallback criteria on substage %d → substage %d",
                      subject_id, substage_id, fallback_target)
            return "fallback"

    return "stay"


def apply(subject_id: int, substage_id: int, decision: str, conn) -> int | None:
    """
    Apply an advance/fallback decision by updating subjects.current_substage_id.
    Returns the new substage_id, or None if decision is "stay".
    """
    if decision == "stay":
        return None

    direction = "advance_to_substage_id" if decision == "advance" else "fallback_to_substage_id"

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {direction} FROM training_substages WHERE id = %s",
            (substage_id,)
        )
        row = cur.fetchone()

    if not row or row[0] is None:
        _log.warning("No %s target for substage %d — staying", decision, substage_id)
        return None

    new_substage_id = row[0]

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE subjects SET current_substage_id = %s, substage_entered_at = NOW() WHERE id = %s",
            (new_substage_id, subject_id)
        )

    _log.info("Subject %d moved from substage %d → %d (%s)",
              subject_id, substage_id, new_substage_id, decision)
    return new_substage_id


def _meets(criteria: dict, subject_id: int, substage_id: int, conn,
           is_fallback: bool = False) -> bool:
    ctype = criteria.get("type")
    handler = _CRITERIA_HANDLERS.get(ctype)
    if handler is None:
        _log.warning("Unknown criteria type '%s' — treating as not met", ctype)
        return False
    return handler(criteria, subject_id, substage_id, conn, is_fallback)


def _pct_correct(criteria: dict, subject_id: int, substage_id: int, conn,
                 is_fallback: bool = False) -> bool:
    """
    Advance: returns True when correct rate >= threshold over the last `window` trials.
    Fallback: returns True when correct rate <  threshold over the last `window` trials.
    """
    window    = int(criteria.get("window",    20))
    threshold = float(criteria.get("threshold", 0.80))

    # Only count trials completed since the subject last entered this substage.
    with conn.cursor() as cur:
        cur.execute("""
            SELECT outcome
            FROM trial_results
            WHERE substage_id = %s
              AND session_id IN (SELECT id FROM sessions WHERE subject_id = %s)
              AND outcome IN ('correct', 'wrong')
              AND completed_at > COALESCE(
                  (SELECT substage_entered_at FROM subjects WHERE id = %s),
                  '-infinity'::timestamptz
              )
            ORDER BY completed_at DESC
            LIMIT %s
        """, (substage_id, subject_id, subject_id, window))
        rows = cur.fetchall()

    if len(rows) < window:
        return False

    correct = sum(1 for r in rows if r[0] == "correct")
    pct = correct / len(rows)
    _log.info(
        "Subject %d substage %d: %.0f%% correct over last %d trials "
        "(threshold %.0f%%, checking %s)",
        subject_id, substage_id, pct * 100, len(rows), threshold * 100,
        "pct < threshold (fallback)" if is_fallback else "pct >= threshold (advance)",
    )
    return pct < threshold if is_fallback else pct >= threshold


_CRITERIA_HANDLERS = {
    "pct_correct": _pct_correct,
}
