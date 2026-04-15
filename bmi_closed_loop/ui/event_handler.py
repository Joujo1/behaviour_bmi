"""
TCP event handler for trial completion events pushed by the Pi.

Called from TCPCommandSender's reader thread when a
trial_complete or trial_aborted event arrives.  Writes the result to
Postgres, evaluates advancement criteria, optionally swaps the
runner's substage, and writes a UI notification to Valkey.
"""

import json
import logging
import time

import psycopg2
import psycopg2.extras
import valkey as valkey_client

import config
from ui.cage_runner import runners
from ui import advancement

_valkey = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)
_log = logging.getLogger("event_handler")


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


def handle_trial_event(cage_id: int, event: dict) -> None:
    """
    Called by the TCP reader thread when the Pi pushes a trial_complete or
    trial_aborted event. Writes the result to Postgres and unblocks the runner.
    """
    event_type = event.get("event")
    if event_type not in ("trial_complete", "trial_aborted"):
        return

    trial_id = event.get("trial_id", "unknown")
    outcome  = event.get("outcome", "aborted" if event_type == "trial_aborted" else "correct")
    events   = event.get("events", [])

    _log.info("Cage %d: %s  outcome=%s  trial_id=%s  n_events=%d",
              cage_id, event_type, outcome, trial_id, len(events))

    runner = runners.get(cage_id)
    if runner:
        runner.on_trial_complete(event)

    ctx = runner.get_context() if runner else {}
    session_id  = ctx.get("session_id")
    substage_id = ctx.get("substage_id")

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trial_results
                        (cage_id, trial_id, outcome, events, session_id, substage_id, completed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (cage_id, trial_id, outcome, psycopg2.extras.Json(events),
                     session_id, substage_id),
                )

        if session_id is not None and substage_id is not None:
            with conn.cursor() as cur:
                cur.execute("SELECT subject_id FROM sessions WHERE id = %s", (session_id,))
                row = cur.fetchone()
            subject_id = row[0] if row else None

            if subject_id is not None:
                decision = advancement.evaluate(subject_id, substage_id, conn)
                if decision != "stay":
                    with conn:
                        new_substage = advancement.apply(subject_id, substage_id, decision, conn)
                    if new_substage and runner and runner.is_running:
                        # Fetch new task_config and swap the runner
                        with conn.cursor() as cur:
                            cur.execute("SELECT task_config FROM training_substages WHERE id = %s",
                                        (new_substage,))
                            tc_row = cur.fetchone()
                        if tc_row and tc_row[0].get("base_iti_s") is not None:
                            switched = runner.switch_substage(tc_row[0], new_substage)
                            if switched:
                                _log.info("Cage %d: auto-switched substage — subject %d %s to substage %d",
                                          cage_id, subject_id, decision, new_substage)
                            else:
                                _log.warning("Cage %d: switch_substage failed, stopping instead", cage_id)
                                runner.stop()
                        else:
                            _log.warning("Cage %d: new substage %d has no ITI — stopping runner",
                                         cage_id, new_substage)
                            runner.stop()

                    # Write UI notification to Valkey (expires after 20 seconds)
                    try:
                        with conn.cursor() as cur:
                            cur.execute("SELECT label FROM training_substages WHERE id = %s",
                                        (new_substage,))
                            lrow = cur.fetchone()
                        new_label = lrow[0] if lrow else f"substage {new_substage}"
                        _valkey.set(
                            f"cage:{cage_id}:advancement",
                            json.dumps({
                                "decision":  decision,
                                "new_id":    new_substage,
                                "new_label": new_label,
                                "ts":        time.time(),
                            }),
                            ex=20,
                        )
                    except Exception as ve:
                        _log.warning("Cage %d: could not write advancement notification: %s",
                                     cage_id, ve)

    except Exception as e:
        _log.error("Cage %d: failed to write trial result: %s", cage_id, e)
    finally:
        conn.close()
