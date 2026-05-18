"""
Per-cage trial runner.

One CageRunner instance lives for the lifetime of the application (created at
startup in ui_main.py). start() launches a background thread that sends trials continuously;
stop() signals it to finish after the current trial.

Completion events are delivered by the TCP reader thread via on_trial_complete().
"""

import copy
import json
import logging
import random
import threading
import time

import psycopg2

import config
from ui.click_generator import generate_clicks

_log = logging.getLogger("runner")


class CageRunner:
    """Manages the continuous trial loop for one cage."""

    def __init__(self, cage_id: int) -> None:
        self.cage_id = cage_id

        self._thread: threading.Thread | None = None
        self._event  = threading.Event()
        self._lock   = threading.Lock()

        self._stop:              bool        = False
        self._last_result:       dict | None = None
        self._pending_switch:    dict | None = None
        self.session_id:         int  | None = None
        self.substage_id:        int  | None = None
        self.subject_id:         int  | None = None
        self._started_at:        float| None = None
        self._correct_side:      str  | None = None
        self._click_seed:        int  | None = None
        self._last_click_ratio:  float| None = None   # high/low click ratio of the most recently sent trial

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, trial_definition: dict, sender,
              base_iti_s: float, fail_iti_s: float,
              session_id: int | None = None,
              substage_id: int | None = None,
              subject_id: int | None = None) -> tuple[bool, str]:
        """Launch the continuous run loop in a background thread."""
        with self._lock:
            if self.is_running:
                return False, "run already in progress"
            self._stop           = False
            self._last_result    = None
            self._pending_switch = None
            self.session_id      = session_id
            self.substage_id     = substage_id
            self.subject_id      = subject_id
            self._started_at     = time.time()
            self._event.clear()
            self._thread = threading.Thread(target=self._run_loop, args=(trial_definition, sender, base_iti_s, fail_iti_s),
                                            daemon=True, name=f"runner-cage{self.cage_id}",)
            self._thread.start()
        return True, "run started"

    def stop(self) -> tuple[bool, str]:
        """Signal the run loop to stop after the current trial finishes."""
        if not self.is_running:
            return False, "no run in progress"
        with self._lock:
            self._stop = True
        self._event.set()
        return True, "stop requested"

    def on_trial_complete(self, event: dict) -> None:
        """Called from the TCP reader thread when trial_complete/trial_aborted arrives."""
        with self._lock:
            self._last_result = event
        self._event.set()

    def switch_substage(self, trial_definition: dict, substage_id: int) -> bool:
        """Swap the trial definition mid-session after advancement/fallback."""
        if not self.is_running:
            return False
        with self._lock:
            self._pending_switch = {
                "trial_definition": trial_definition,
                "substage_id":      substage_id,
                "base_iti_s":       max(0.0, float(trial_definition.get("base_iti_s", 5.0))),
                "fail_iti_s":       max(0.0, float(trial_definition.get("fail_iti_s", 15.0))),
            }
            self.substage_id = substage_id
        return True

    def get_context(self) -> dict:
        """Return {session_id, substage_id, correct_side, click_seed} for the active run."""
        with self._lock:
            return {
                "session_id":   self.session_id,
                "substage_id":  self.substage_id,
                "correct_side": self._correct_side,
                "click_seed":   self._click_seed,
            }

    def get_status(self) -> dict:
        """Return {running, substage_id, started_at}."""
        if not self.is_running:
            return {"running": False, "substage_id": None, "started_at": None}
        with self._lock:
            return {
                "running":     True,
                "substage_id": self.substage_id,
                "started_at":  self._started_at,
            }

    def _run_loop(self, trial_definition: dict, sender,
                  base_iti_s: float, fail_iti_s: float) -> None:
        _log.info("Cage %d: starting continuous run (iti=%.1fs fail_iti=%.1fs)",
                  self.cage_id, base_iti_s, fail_iti_s)
        trial_count = 0

        # Pre-compute the first trial before the loop so every iteration
        # only needs a TCP send when the ITI expires (not resolve+expand+send).
        resolved, correct_side = _resolve_sides(trial_definition)
        click_seed = random.randrange(2**32)
        trial_to_send = _expand_clicks(resolved, seed=click_seed)
        with self._lock:
            self._correct_side = correct_side
            self._click_seed   = click_seed

        while True:
            with self._lock:
                if self._stop:
                    _log.info("Cage %d: stop requested — run ending after %d trial(s)",
                              self.cage_id, trial_count)
                    break
                switch = self._pending_switch
                self._pending_switch = None

            if switch:
                trial_definition = switch["trial_definition"]
                base_iti_s       = switch["base_iti_s"]
                fail_iti_s       = switch["fail_iti_s"]
                _log.info("Cage %d: switched to substage %d (iti=%.1fs fail_iti=%.1fs)",
                          self.cage_id, switch["substage_id"], base_iti_s, fail_iti_s)
                # Re-compute trial immediately after a substage switch
                resolved, correct_side = _resolve_sides(trial_definition)
                click_seed = random.randrange(2**32)
                trial_to_send = _expand_clicks(resolved, seed=click_seed)
                with self._lock:
                    self._correct_side = correct_side
                    self._click_seed   = click_seed

            trial_count += 1
            with self._lock:
                last_click_ratio = self._last_click_ratio

            trial_for_resolve = (
                _apply_bias(trial_definition, self.subject_id,
                            last_click_ratio=last_click_ratio)
                if self.subject_id is not None else trial_definition
            )
            resolved, correct_side = _resolve_sides(trial_for_resolve)
            click_seed = random.randrange(2**32)
            trial_to_send = _expand_clicks(resolved, seed=click_seed)
            with self._lock:
                self._correct_side     = correct_side
                self._click_seed       = click_seed
                self._last_click_ratio = _get_click_ratio(trial_to_send)
            _log.info("Cage %d: trial %d — sending (correct_side=%s)",
                      self.cage_id, trial_count, correct_side)
            self._event.clear()

            ok, msg = sender.send(json.dumps(trial_to_send))
            if not ok:
                _log.error("Cage %d: failed to send trial: %s", self.cage_id, msg)
                break

            completed = self._event.wait(timeout=config.TRIAL_TIMEOUT_S)
            if not completed:
                _log.error("Cage %d: timed out waiting for trial completion (trial %d)",
                           self.cage_id, trial_count)
                break

            with self._lock:
                result  = self._last_result or {}
                stopped = self._stop

            if stopped:
                _log.info("Cage %d: run stopped after trial %d", self.cage_id, trial_count)
                break

            outcome = result.get("outcome", "correct")
            failed  = outcome != "correct"
            iti     = fail_iti_s if failed else base_iti_s
            _log.info("Cage %d: trial %d done (outcome=%s) — ITI %.1fs",
                      self.cage_id, trial_count, outcome, iti)

            # Pre-compute next trial during the ITI so it's ready to send immediately.
            resolved, correct_side = _resolve_sides(trial_definition)
            click_seed = random.randrange(2**32)
            trial_to_send = _expand_clicks(resolved, seed=click_seed)
            with self._lock:
                self._correct_side = correct_side
                self._click_seed   = click_seed

            # ITI — interruptible by stop()
            self._event.clear()
            interrupted = self._event.wait(timeout=iti)
            if interrupted:
                with self._lock:
                    if self._stop:
                        _log.info("Cage %d: run stopped during ITI after trial %d",
                                  self.cage_id, trial_count)
                        break

        _log.info("Cage %d: run finished (%d trial(s) completed)",
                  self.cage_id, trial_count)


runners: dict[int, CageRunner] = {}

def _resolve_sides(trial_definition: dict) -> tuple:
    """
    Resolve click-side assignment for one trial.

    side_mode = "random" (default):
        Fair coin-flip each trial. high_rate goes to the winning side,
        low_rate to the other. high_click_side / low_click_side aliases
        are replaced with the concrete side string.

    side_mode = "fixed":
        Rates stay exactly as written (left_rate → left speaker, right_rate →
        right speaker). Aliases are resolved by checking which side has the
        higher rate. correct_side is None.

    side_mode = "weighted":
        Biased coin-flip using left_probability (0–1) from the trial definition.
        Useful for correcting side bias: set left_probability > 0.5 to push
        more trials to the left side. Alias resolution identical to "random".

    Returns (resolved_trial_dict, correct_side_str).
    correct_side is None when side_mode is "fixed".
    """
    side_mode = trial_definition.get("side_mode", "random")
    trial = copy.deepcopy(trial_definition)

    if side_mode == "fixed":
        # Pass 1 — determine high/low side from the play_clicks action.
        high_side = None
        low_side  = None
        for state in trial.get("states", []):
            for phase in ("entry_actions", "exit_actions"):
                for action in state.get(phase, []):
                    if action.get("type") == "play_clicks":
                        lr = action.get("left_rate",  0) or 0
                        rr = action.get("right_rate", 0) or 0
                        high_side = "left" if lr >= rr else "right"
                        low_side  = "right" if high_side == "left" else "left"

        # Pass 2 — resolve aliases everywhere.
        for state in trial.get("states", []):
            for phase in ("entry_actions", "exit_actions"):
                for action in state.get(phase, []):
                    if action.get("type") != "play_clicks":
                        tgt = action.get("target")
                        if tgt == "high_click_side":
                            action["target"] = high_side
                        elif tgt == "low_click_side":
                            action["target"] = low_side
            for transition in state.get("transitions", []):
                if transition.get("trigger") == "beam_break":
                    tgt = transition.get("target")
                    if tgt == "high_click_side":
                        transition["target"] = high_side
                    elif tgt == "low_click_side":
                        transition["target"] = low_side
        return trial, high_side

    # Random and weighted modes — coin flip only if the trial uses
    # side-dependent logic (play_clicks present, or aliases used).
    SIDE_ALIASES = {"high_click_side", "low_click_side"}
    def _uses_sides(t):
        for state in t.get("states", []):
            for phase in ("entry_actions", "exit_actions"):
                for action in state.get(phase, []):
                    if action.get("type") == "play_clicks":
                        return True
                    if action.get("target") in SIDE_ALIASES:
                        return True
            for transition in state.get("transitions", []):
                if transition.get("target") in SIDE_ALIASES:
                    return True
        return False

    if not _uses_sides(trial):
        return trial, None

    if side_mode == "weighted":
        left_prob    = max(0.0, min(1.0, float(trial_definition.get("left_probability", 0.5))))
        correct_side = "left" if random.random() < left_prob else "right"
    else:
        correct_side = random.choice(["left", "right"])
    wrong_side = "right" if correct_side == "left" else "left"

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


def _get_click_ratio(expanded_trial: dict) -> float | None:
    """Return high_clicks / low_clicks for the play_clicks action, or None if absent."""
    for state in expanded_trial.get("states", []):
        for phase in ("entry_actions", "exit_actions"):
            for action in state.get(phase, []):
                if action.get("type") == "play_clicks":
                    n_r = len(action.get("right_clicks", []))
                    n_l = len(action.get("left_clicks",  []))
                    n_hi, n_lo = (n_r, n_l) if n_r >= n_l else (n_l, n_r)
                    return n_hi / max(n_lo, 1)
    return None


def _expand_clicks(trial_definition: dict, seed: int | None = None) -> dict:
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
                min_ici    = action.pop("min_ici", None)   # None → generator default (click width)
                kw = {} if min_ici is None else {"min_ici": min_ici}
                clicks = generate_clicks(left_rate, right_rate, duration, seed=seed, **kw)
                action["left_clicks"]  = clicks["left_clicks"]
                action["right_clicks"] = clicks["right_clicks"]
    return trial


def _get_subject_bias_alg(subject_id: int) -> str:
    conn = psycopg2.connect(config.POSTGRES_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT side_bias_alg FROM subjects WHERE id = %s", (subject_id,))
            row = cur.fetchone()
        return (row[0] or "none") if row else "none"
    except Exception:
        _log.exception("bias_alg lookup failed for subject %d", subject_id)
        return "none"
    finally:
        conn.close()


def _query_recent_trials(subject_id: int, window: int = 20) -> list[dict]:
    conn = psycopg2.connect(config.POSTGRES_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT correct_side, outcome
                FROM trial_results
                WHERE session_id IN (SELECT id FROM sessions WHERE subject_id = %s)
                  AND outcome IN ('correct', 'wrong')
                ORDER BY completed_at DESC
                LIMIT %s
            """, (subject_id, window))
            rows = cur.fetchall()
        return [{"correct_side": r[0], "outcome": r[1]} for r in rows]
    except Exception:
        _log.exception("recent trial query failed for subject %d", subject_id)
        return []
    finally:
        conn.close()


def _apply_bias(trial_definition: dict, subject_id: int,
                last_click_ratio: float | None = None) -> dict:
    """
    Return a (possibly modified) trial dict with side_mode='weighted' and
    left_probability adjusted by the subject's bias algorithm.
    Returns the original dict unchanged when bias does not apply.

    last_click_ratio: high_clicks / low_clicks ratio of the most recently completed trial.
        Used by the IBL algorithm to gate on easy trials only.  Pass None (default) to
        skip the difficulty check (original behaviour).
    """
    if trial_definition.get("side_mode") not in ("random", "weighted"):
        return trial_definition  # fixed mode: no intervention

    alg = _get_subject_bias_alg(subject_id)
    if alg == "none":
        return trial_definition

    recent = _query_recent_trials(subject_id, window=20)
    left_prob = None

    if alg == "brody":
        left_hits  = [t["outcome"] == "correct" for t in recent if t["correct_side"] == "left"]
        right_hits = [t["outcome"] == "correct" for t in recent if t["correct_side"] == "right"]
        if left_hits and right_hits:
            fc_l  = sum(left_hits) / len(left_hits)
            fc_r  = sum(right_hits) / len(right_hits)
            total = fc_l + fc_r
            left_prob = (fc_r / total) if total > 0 else 0.5
            _log.info("Brody bias: fc_l=%.2f fc_r=%.2f → P(left)=%.2f", fc_l, fc_r, left_prob)

    elif alg == "ibl":
        if recent and recent[0]["outcome"] == "wrong":
            # Easy-trial gate: only act when the last trial had a clear click majority.
            # Threshold is read from the trial definition so it can be set per substage
            # (add "ibl_easy_min_ratio": 2.0 to the substage task_config).
            # Falls back to None (gate disabled) when the key is absent.
            easy_min_ratio = trial_definition.get("ibl_easy_min_ratio", 2.5)
            if (easy_min_ratio is not None
                    and last_click_ratio is not None
                    and last_click_ratio < easy_min_ratio):
                _log.debug("IBL debias skipped: last trial ratio %.2f < threshold %.2f",
                           last_click_ratio, easy_min_ratio)
            else:
                responded = []
                for t in recent[:10]:
                    cs = t["correct_side"]
                    if cs is None:
                        continue
                    resp = cs if t["outcome"] == "correct" else ("right" if cs == "left" else "left")
                    responded.append(resp)
                if responded:
                    avg_right = sum(1 for s in responded if s == "right") / len(responded)
                    left_prob = 1.0 - avg_right
                    _log.info("IBL debias triggered: ratio=%.2f avg_right=%.2f → P(left)=%.2f",
                              last_click_ratio or -1, avg_right, left_prob)

    if left_prob is None:
        return trial_definition

    return {**trial_definition, "side_mode": "weighted", "left_probability": left_prob}
