"""
Beam-break emulator for load-testing and validation runs.

Enabled by setting EMULATE = True in config.py.  When active, main.py
skips gpio_handler.start_monitoring() and calls run_trial() after each
engine.start() instead.

run_trial() inspects the trial FSM to find which beam-break sequence
produces the desired outcome, then fires synthetic gpio_handler events
on a background thread — no GPIO hardware required.

Outcome sequence is controlled by EMULATE_OUTCOMES in config.py.
"""

import logging
import threading
import time

import gpio_handler
from config import EMULATE_PRE_BEAM_DELAY_S, EMULATE_BEAM_HOLD_S

logger = logging.getLogger(__name__)


def _fire(target: str, active: bool) -> None:
    """Inject a synthetic beam event directly into the active trial callback."""
    t  = time.clock_gettime(time.CLOCK_MONOTONIC)
    fn = gpio_handler._on_event_fn   # snapshot — GIL-atomic read
    if fn is not None:
        fn(target, active, t)
    else:
        logger.debug("Emulator: _on_event_fn is None — trial may have ended already")


def _beam_sequence(trial_data: dict, outcome: str) -> list[str]:
    """
    Walk the trial FSM and return the ordered list of beam targets to break
    in order to reach the desired outcome.

    Heuristic for "correct" vs "wrong" at a multi-beam state: whichever
    beam_break transition leads to a state with a valve_open action (or
    directly to __correct__) is the correct side.

    Returns [] for "aborted" (no beams — trial times out via watchdog).
    """
    if outcome == "aborted":
        return []

    states  = {s["id"]: s for s in trial_data.get("states", [])}
    current = trial_data.get("initial_state")
    visited: set[str] = set()
    seq: list[str]    = []

    while current and current not in visited and not current.startswith("__"):
        visited.add(current)
        state = states.get(current)
        if state is None:
            break

        beam_trs = [t for t in state.get("transitions", [])
                    if t.get("trigger") == "beam_break"]

        if not beam_trs:
            # No beam break here — follow timeout to next state
            timeout_tr = next(
                (t for t in state.get("transitions", []) if t.get("trigger") == "timeout"),
                None,
            )
            current = timeout_tr["next_state"] if timeout_tr else None
            continue

        if len(beam_trs) == 1:
            chosen = beam_trs[0]
        else:
            # Multiple beam options — determine which leads to reward
            def _leads_to_reward(tr: dict) -> bool:
                ns = tr.get("next_state", "")
                if ns == "__correct__":
                    return True
                ns_state = states.get(ns, {})
                return any(
                    a.get("type") == "valve_open"
                    for a in ns_state.get("entry_actions", [])
                )

            correct_trs = [t for t in beam_trs if _leads_to_reward(t)]
            wrong_trs   = [t for t in beam_trs if not _leads_to_reward(t)]

            if outcome == "correct" and correct_trs:
                chosen = correct_trs[0]
            elif outcome == "wrong" and wrong_trs:
                chosen = wrong_trs[0]
            else:
                chosen = beam_trs[0]

        seq.append(chosen["target"])
        current = chosen.get("next_state")

    return seq


def run_trial(trial_data: dict, outcome: str) -> None:
    """
    Kick off a background thread that fires synthetic beam events to
    produce `outcome` for the current trial.

    outcome: "correct" | "wrong" | "aborted"
    """
    seq = _beam_sequence(trial_data, outcome)
    logger.info("Emulator: outcome=%s  beams=%s", outcome, seq)

    if not seq:
        # Aborted — let the engine watchdog time the trial out naturally
        return

    def _play() -> None:
        for beam in seq:
            time.sleep(EMULATE_PRE_BEAM_DELAY_S)
            _fire(beam, True)
            time.sleep(EMULATE_BEAM_HOLD_S)
            _fire(beam, False)

    threading.Thread(target=_play, daemon=True, name="emulator").start()
