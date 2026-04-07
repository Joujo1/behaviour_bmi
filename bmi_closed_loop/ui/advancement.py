"""
Substage advancement evaluator.

After each trial completes, call evaluate(subject_id, substage_id, conn).
Returns "advance", "fallback", or "stay".

Criteria are stored as JSONB on training_substages:
    {"type": "pct_correct", "window": 20, "threshold": 0.80}

    type      — only "pct_correct" supported for now
    window    — how many recent trials to look at
    threshold — fraction correct required (0.0–1.0)

NULL criteria means no automatic transition — always returns "stay".
"""
import logging

_log = logging.getLogger("advancement")


def evaluate(subject_id: int, substage_id: int, conn) -> str:
    """
    Check advancement and fallback criteria for a subject on a substage.

    Returns:
        "advance"  — advance criteria met, move to advance_to_substage_id
        "fallback" — fallback criteria met, move to fallback_to_substage_id
        "stay"     — neither criteria met, or no criteria defined
    """
    with conn.cursor() as cur:
        # Load criteria and advancement targets for this substage
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

    # Check advance first, then fallback
    if advance_criteria and advance_target:
        if _meets(advance_criteria, subject_id, substage_id, conn):
            _log.info("Subject %d met advance criteria on substage %d → substage %d",
                      subject_id, substage_id, advance_target)
            return "advance"

    if fallback_criteria and fallback_target:
        if _meets(fallback_criteria, subject_id, substage_id, conn):
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
            "UPDATE subjects SET current_substage_id = %s WHERE id = %s",
            (new_substage_id, subject_id)
        )

    _log.info("Subject %d moved from substage %d → %d (%s)",
              subject_id, substage_id, new_substage_id, decision)
    return new_substage_id


# ---------------------------------------------------------------------------
# Criteria implementations
# ---------------------------------------------------------------------------

def _meets(criteria: dict, subject_id: int, substage_id: int, conn) -> bool:
    """Dispatch to the correct criteria check based on criteria['type']."""
    ctype = criteria.get("type")
    if ctype == "pct_correct":
        return _pct_correct(criteria, subject_id, substage_id, conn)
    _log.warning("Unknown criteria type '%s' — treating as not met", ctype)
    return False


def _pct_correct(criteria: dict, subject_id: int, substage_id: int, conn) -> bool:
    """
    Returns True if the last `window` trials for this subject on this substage
    have a correct rate >= threshold.

    Aborted trials are excluded — they don't count for or against the animal.
    Only 'correct' and 'wrong' outcomes are considered.
    """
    window    = int(criteria.get("window",    20))
    threshold = float(criteria.get("threshold", 0.80))

    with conn.cursor() as cur:
        cur.execute("""
            SELECT outcome
            FROM trial_results
            WHERE substage_id = %s
              AND session_id IN (
                  SELECT id FROM sessions WHERE subject_id = %s
              )
              AND outcome IN ('correct', 'wrong')
            ORDER BY completed_at DESC
            LIMIT %s
        """, (substage_id, subject_id, window))
        rows = cur.fetchall()

    if len(rows) < window:
        # Not enough trials yet to evaluate
        return False

    correct = sum(1 for r in rows if r[0] == "correct")
    pct = correct / len(rows)
    _log.info("Subject %d substage %d: %.0f%% correct over last %d trials (threshold %.0f%%)",
              subject_id, substage_id, pct * 100, len(rows), threshold * 100)
    return pct >= threshold
