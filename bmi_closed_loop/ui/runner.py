"""
N-repetition trial runner.

Runs a trial config N times on a cage, waiting for the Pi's trial_complete
or trial_aborted event between each repetition. Completion events are
delivered by the TCP reader thread via on_trial_complete().
"""
import copy
import json
import logging
import threading

from ui.click_generator import generate_clicks

_log = logging.getLogger("runner")

# cage_id → {"thread": Thread, "event": Event, "last_result": dict, "stop": bool}
_state: dict = {}
_state_lock = threading.Lock()

TRIAL_TIMEOUT_S = 330  # Pi watchdog is 300s; add 30s margin


def start_run(cage_id: int, trial_definition: dict, n_reps: int, sender,
              base_iti_s: float = 5.0, fail_iti_s: float = 15.0) -> tuple:
    """
    Start an N-rep run for a cage. Returns (ok, msg).

    base_iti_s: seconds to wait between trials after a successful completion.
    fail_iti_s: seconds to wait between trials after an aborted/failed trial.
    """
    with _state_lock:
        existing = _state.get(cage_id)
        if existing and existing["thread"].is_alive():
            return False, "run already in progress"

        ev = threading.Event()
        _state[cage_id] = {"thread": None, "event": ev, "last_result": None, "stop": False}

        t = threading.Thread(
            target=_run_loop,
            args=(cage_id, trial_definition, n_reps, sender, ev, base_iti_s, fail_iti_s),
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
    """Called from _on_pi_event when a trial_complete or trial_aborted arrives."""
    with _state_lock:
        s = _state.get(cage_id)
    if s:
        s["last_result"] = event
        s["event"].set()


def is_running(cage_id: int) -> bool:
    with _state_lock:
        s = _state.get(cage_id)
    return bool(s and s["thread"].is_alive())


def _expand_clicks(trial_definition: dict) -> dict:
    """
    Deep-copy the trial definition and replace any play_clicks action that
    carries rate parameters (left_rate, right_rate, click_duration) with
    pre-generated left_clicks / right_clicks arrays.

    Actions that already contain left_clicks / right_clicks are passed through unchanged
    """
    trial = copy.deepcopy(trial_definition)
    for state in trial.get("states", []):
        for phase in ("entry_actions", "exit_actions"):
            for action in state.get(phase, []):
                if action.get("type") != "play_clicks":
                    continue
                if "left_clicks" in action or "right_clicks" in action:
                    continue  # already expanded
                left_rate  = action.pop("left_rate",       0)
                right_rate = action.pop("right_rate",      0)
                duration   = action.pop("click_duration",  1.0)
                clicks = generate_clicks(left_rate, right_rate, duration)
                action["left_clicks"]  = clicks["left_clicks"]
                action["right_clicks"] = clicks["right_clicks"]
    return trial


def _run_loop(cage_id, trial_definition, n_reps, sender, ev, base_iti_s, fail_iti_s):
    _log.info("Cage %d: starting %d-rep run (iti=%.1fs fail_iti=%.1fs)",
              cage_id, n_reps, base_iti_s, fail_iti_s)

    for i in range(n_reps):
        with _state_lock:
            if _state[cage_id]["stop"]:
                _log.info("Cage %d: stop requested before rep %d", cage_id, i + 1)
                break

        _log.info("Cage %d: rep %d/%d — sending trial", cage_id, i + 1, n_reps)
        ev.clear()

        trial_to_send = _expand_clicks(trial_definition)
        ok, msg = sender.send(json.dumps(trial_to_send))
        if not ok:
            _log.error("Cage %d: failed to send trial: %s", cage_id, msg)
            break

        completed = ev.wait(timeout=TRIAL_TIMEOUT_S)
        if not completed:
            _log.error("Cage %d: timed out waiting for trial completion on rep %d", cage_id, i + 1)
            break

        with _state_lock:
            result  = _state[cage_id].get("last_result") or {}
            stopped = _state[cage_id]["stop"]

        if stopped:
            _log.info("Cage %d: run stopped after rep %d", cage_id, i + 1)
            break

        failed = result.get("aborted", False)
        iti    = fail_iti_s if failed else base_iti_s
        _log.info("Cage %d: rep %d/%d done (aborted=%s) — ITI %.1fs",
                  cage_id, i + 1, n_reps, failed, iti)

        # ITI — skip on the last rep
        if i < n_reps - 1:
            ev.clear()
            # Reuse the event as a stop-signal during ITI so stop_run() interrupts the wait
            interrupted = ev.wait(timeout=iti)
            if interrupted:
                with _state_lock:
                    if _state[cage_id]["stop"]:
                        _log.info("Cage %d: run stopped during ITI after rep %d", cage_id, i + 1)
                        break

    _log.info("Cage %d: run finished", cage_id)
