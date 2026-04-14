"""
Continuous trial runner.

Sends trials to a cage one after another indefinitely, waiting for the Pi's
trial_complete or trial_aborted event between each. Stops when:
  - stop_run() is called by the researcher
  - stop_run() is called by the advancement evaluator after criteria are met

Completion events are delivered by the TCP reader thread via on_trial_complete().
"""
import copy
import json
import logging
import random
import threading
import time

from ui.click_generator import generate_clicks

_log = logging.getLogger("runner")

# cage_id → {"thread": Thread, "event": Event, "last_result": dict, "stop": bool,
#             "session_id": int|None, "substage_id": int|None}
_state: dict = {}
_state_lock = threading.Lock()

TRIAL_TIMEOUT_S = 330


def start_run(cage_id: int, trial_definition: dict, sender,
              base_iti_s: float = 5.0, fail_iti_s: float = 15.0,
              session_id: int = None, substage_id: int = None) -> tuple:
    """
    base_iti_s:  seconds to wait between trials after a correct outcome.
    fail_iti_s:  seconds to wait between trials after a wrong/aborted outcome.
    session_id:  DB sessions.id — stamped on every trial_results row.
    substage_id: DB training_substages.id — stamped on every trial_results row.
    """
    with _state_lock:
        existing = _state.get(cage_id)
        if existing and existing["thread"].is_alive():
            return False, "run already in progress"

        ev = threading.Event()
        _state[cage_id] = {
            "thread": None, "event": ev, "last_result": None, "stop": False,
            "session_id": session_id, "substage_id": substage_id,
            "pending_switch": None, "started_at": time.time(),
        }

        t = threading.Thread(
            target=_run_loop,
            args=(cage_id, trial_definition, sender, ev, base_iti_s, fail_iti_s),
            daemon=True,
            name=f"runner-cage{cage_id}",
        )
        _state[cage_id]["thread"] = t
        t.start()
    return True, "run started"


def stop_run(cage_id: int) -> tuple:
    """Signal the runner to stop after the current trial finishes."""
    with _state_lock:
        s = _state.get(cage_id)
    if not s or not s["thread"].is_alive():
        return False, "no run in progress"
    s["stop"] = True
    s["event"].set()
    return True, "stop requested"


def on_trial_complete(cage_id: int, event: dict) -> None:
    """Called from handle_trial_event when a trial_complete or trial_aborted arrives."""
    with _state_lock:
        s = _state.get(cage_id)
    if s:
        s["last_result"] = event
        s["event"].set()


def is_running(cage_id: int) -> bool:
    with _state_lock:
        s = _state.get(cage_id)
    return bool(s and s["thread"].is_alive())


def switch_substage(cage_id: int, trial_definition: dict, substage_id: int) -> bool:
    """
    Swap the trial definition mid-session after an advancement/fallback.
    The runner picks up the new config at the start of the next trial.
    """
    with _state_lock:
        s = _state.get(cage_id)
        if not s or not s["thread"].is_alive():
            return False
        s["pending_switch"] = {
            "trial_definition": trial_definition,
            "substage_id":      substage_id,
            "base_iti_s":       max(0.0, float(trial_definition.get("base_iti_s", 5.0))),
            "fail_iti_s":       max(0.0, float(trial_definition.get("fail_iti_s", 15.0))),
        }
        s["substage_id"] = substage_id  # update context immediately
    return True


def get_run_context(cage_id: int) -> dict:
    """Return {session_id, substage_id} for the active run, or empty dict if none."""
    with _state_lock:
        s = _state.get(cage_id)
    if not s:
        return {}
    return {"session_id": s.get("session_id"), "substage_id": s.get("substage_id")}


def get_run_status(cage_id: int) -> dict:
    """Return {running, substage_id, started_at} for a cage."""
    with _state_lock:
        s = _state.get(cage_id)
    if not s or not s["thread"].is_alive():
        return {"running": False, "substage_id": None, "started_at": None}
    return {
        "running":    True,
        "substage_id": s.get("substage_id"),
        "started_at": s.get("started_at"),
    }


def _resolve_sides(trial_definition: dict) -> tuple:
    """
    Resolve click-side assignment for one trial.

    side_mode values:
      "random" (default) — coin flip each trial.
          high_rate = max(left_rate, right_rate) goes to correct_side;
          low_rate  = min(...)                   goes to the other side.
          'high_click_side' / 'low_click_side' aliases in transitions and
          actions are replaced with the concrete side string.
      "fixed" — rates are used exactly as written (left_rate → left speaker,
          right_rate → right speaker). No alias resolution. The trial
          definition already has hardcoded left/right targets.

    Returns (resolved_trial_dict, correct_side_str).
    correct_side is None when side_mode is "fixed".
    """
    side_mode = trial_definition.get("side_mode", "random")

    if side_mode != "random":
        # Fixed mode: pass through unchanged, no coin flip needed.
        return copy.deepcopy(trial_definition), None

    correct_side = random.choice(["left", "right"])
    wrong_side   = "right" if correct_side == "left" else "left"

    trial = copy.deepcopy(trial_definition)

    for state in trial.get("states", []):
        for phase in ("entry_actions", "exit_actions"):
            for action in state.get(phase, []):
                if action.get("type") == "play_clicks":
                    lr        = action.get("left_rate",  0) or 0
                    rr        = action.get("right_rate", 0) or 0
                    high_rate = max(lr, rr)
                    low_rate  = min(lr, rr)
                    action["left_rate"]  = high_rate if correct_side == "left" else low_rate
                    action["right_rate"] = low_rate  if correct_side == "left" else high_rate
                else:
                    tgt = action.get("target")
                    if tgt == "high_click_side":
                        action["target"] = correct_side
                    elif tgt == "low_click_side":
                        action["target"] = wrong_side

        for transition in state.get("transitions", []):
            if transition.get("trigger") == "beam_break":
                tgt = transition.get("target")
                if tgt == "high_click_side":
                    transition["target"] = correct_side
                elif tgt == "low_click_side":
                    transition["target"] = wrong_side

    return trial, correct_side


def _expand_clicks(trial_definition: dict) -> dict:
    """
    Deep-copy the trial definition and replace any play_clicks action that
    carries rate parameters (left_rate, right_rate, click_duration) with
    pre-generated left_clicks / right_clicks arrays.
    """
    trial = copy.deepcopy(trial_definition)
    for state in trial.get("states", []):
        for phase in ("entry_actions", "exit_actions"):
            for action in state.get(phase, []):
                if action.get("type") != "play_clicks":
                    continue
                if "left_clicks" in action or "right_clicks" in action:
                    continue  # already expanded
                left_rate  = action.pop("left_rate",      0)
                right_rate = action.pop("right_rate",     0)
                duration   = action.pop("click_duration", 1.0)
                clicks = generate_clicks(left_rate, right_rate, duration)
                action["left_clicks"]  = clicks["left_clicks"]
                action["right_clicks"] = clicks["right_clicks"]
    return trial


def _run_loop(cage_id, trial_definition, sender, ev, base_iti_s, fail_iti_s):
    _log.info("Cage %d: starting continuous run (iti=%.1fs fail_iti=%.1fs)",
              cage_id, base_iti_s, fail_iti_s)
    trial_count = 0

    while True:
        with _state_lock:
            if _state[cage_id]["stop"]:
                _log.info("Cage %d: stop requested — run ending after %d trial(s)",
                          cage_id, trial_count)
                break
            switch = _state[cage_id].pop("pending_switch", None)

        if switch:
            trial_definition = switch["trial_definition"]
            base_iti_s       = switch["base_iti_s"]
            fail_iti_s       = switch["fail_iti_s"]
            _log.info("Cage %d: switched to substage %d (iti=%.1fs fail_iti=%.1fs)",
                      cage_id, switch["substage_id"], base_iti_s, fail_iti_s)

        trial_count += 1
        _log.info("Cage %d: trial %d — sending", cage_id, trial_count)
        ev.clear()

        resolved, correct_side = _resolve_sides(trial_definition)
        trial_to_send = _expand_clicks(resolved)
        _log.info("Cage %d: trial %d — correct_side=%s", cage_id, trial_count, correct_side)
        ok, msg = sender.send(json.dumps(trial_to_send))
        if not ok:
            _log.error("Cage %d: failed to send trial: %s", cage_id, msg)
            break

        completed = ev.wait(timeout=TRIAL_TIMEOUT_S)
        if not completed:
            _log.error("Cage %d: timed out waiting for trial completion (trial %d)",
                       cage_id, trial_count)
            break

        with _state_lock:
            result  = _state[cage_id].get("last_result") or {}
            stopped = _state[cage_id]["stop"]

        if stopped:
            _log.info("Cage %d: run stopped after trial %d", cage_id, trial_count)
            break

        outcome = result.get("outcome", "correct")
        failed  = outcome != "correct"
        iti     = fail_iti_s if failed else base_iti_s
        _log.info("Cage %d: trial %d done (outcome=%s) — ITI %.1fs",
                  cage_id, trial_count, outcome, iti)

        # ITI — interruptible by stop_run()
        ev.clear()
        interrupted = ev.wait(timeout=iti)
        if interrupted:
            with _state_lock:
                if _state[cage_id]["stop"]:
                    _log.info("Cage %d: run stopped during ITI after trial %d",
                              cage_id, trial_count)
                    break

    _log.info("Cage %d: run finished (%d trial(s) completed)", cage_id, trial_count)
