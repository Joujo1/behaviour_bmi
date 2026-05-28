"""
Per-cage trial runner.

One CageRunner instance lives for the lifetime of the application (created at
startup in ui_main.py). start() launches a background thread that sends trials
continuously; stop() signals it to finish after the current trial.

Completion events are delivered by the TCP reader thread via on_trial_complete().
"""

import copy
import json
import logging
import random
import threading
import uuid
import time

import psycopg2

import config
from ui.bias_algorithms import REGISTRY as _BIAS_REGISTRY
from ui.click_generator import generate_clicks

logger = logging.getLogger(__name__)


class CageRunner:
    """Manages the continuous trial loop for one cage."""

    def __init__(self, cage_id: int) -> None:
        self._cage_id = cage_id

        self._thread = None
        self._event  = threading.Event()
        self._lock   = threading.Lock()

        self._stop             = False
        self._last_result      = None
        self._pending_switch   = None
        self._session_id       = None
        self._substage_id      = None
        self._subject_id       = None
        self._started_at       = None
        self._correct_side     = None
        self._click_seed       = None
        self._last_click_ratio = None   # high/low click ratio of the most recently sent trial

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
            self._session_id     = session_id
            self._substage_id    = substage_id
            self._subject_id     = subject_id
            self._started_at     = time.time()
            self._event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                args=(trial_definition, sender, base_iti_s, fail_iti_s),
                daemon=True,
                name=f"runner-cage{self._cage_id}",
            )
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
            self._substage_id = substage_id
        return True

    def get_context(self) -> dict:
        """Return {session_id, substage_id, correct_side, click_seed} for the active run."""
        with self._lock:
            return {
                "session_id":   self._session_id,
                "substage_id":  self._substage_id,
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
                "substage_id": self._substage_id,
                "started_at":  self._started_at,
            }

    def _run_loop(self, trial_definition: dict, sender,
                  base_iti_s: float, fail_iti_s: float) -> None:
        logger.info("Cage %d: starting continuous run (iti=%.1fs fail_iti=%.1fs)",
                    self._cage_id, base_iti_s, fail_iti_s)
        trial_count = 0

        # Pre-compute the first trial with bias applied (last_click_ratio=None:
        # no previous trial yet). Every subsequent trial is pre-computed during
        # the ITI so the send path never blocks on generation.
        trial_for_resolve = (
            _apply_bias(trial_definition, self._subject_id, last_click_ratio=None)
            if self._subject_id is not None else trial_definition
        )
        resolved, correct_side = _resolve_sides(trial_for_resolve)
        click_seed = random.randrange(2**32)
        trial_to_send = _expand_clicks(resolved, seed=click_seed)
        with self._lock:
            self._correct_side     = correct_side
            self._click_seed       = click_seed
            self._last_click_ratio = _get_click_ratio(trial_to_send)

        while True:
            with self._lock:
                if self._stop:
                    logger.info("Cage %d: stop requested — run ending after %d trial(s)",
                                self._cage_id, trial_count)
                    break
                switch = self._pending_switch
                self._pending_switch = None

            if switch:
                trial_definition = switch["trial_definition"]
                base_iti_s       = switch["base_iti_s"]
                fail_iti_s       = switch["fail_iti_s"]
                logger.info("Cage %d: switched to substage %d (iti=%.1fs fail_iti=%.1fs)",
                            self._cage_id, switch["substage_id"], base_iti_s, fail_iti_s)
                # Discard the ITI-pre-computed trial; recompute with the new definition.
                # self._last_click_ratio was not updated during ITI pre-computation so
                # it still holds the ratio of the last completed trial — correct input
                # for bias on the first trial of the new substage.
                with self._lock:
                    last_click_ratio = self._last_click_ratio
                trial_for_resolve = (
                    _apply_bias(trial_definition, self._subject_id,
                                last_click_ratio=last_click_ratio)
                    if self._subject_id is not None else trial_definition
                )
                resolved, correct_side = _resolve_sides(trial_for_resolve)
                click_seed = random.randrange(2**32)
                trial_to_send = _expand_clicks(resolved, seed=click_seed)
                with self._lock:
                    self._correct_side = correct_side
                    self._click_seed   = click_seed

            trial_count += 1
            # Record the ratio of the trial we are about to send so it is
            # available as bias input during the next ITI pre-computation.
            with self._lock:
                self._last_click_ratio = _get_click_ratio(trial_to_send)
            logger.debug("Cage %d: trial %d — sending (correct_side=%s)",
                         self._cage_id, trial_count, correct_side)
            self._event.clear()

            trial_to_send["trial_id"] = str(uuid.uuid4())
            ok, msg = sender.send(json.dumps(trial_to_send))
            if not ok:
                logger.error("Cage %d: failed to send trial: %s", self._cage_id, msg)
                break

            completed = self._event.wait(timeout=config.TRIAL_TIMEOUT_S)
            if not completed:
                logger.error("Cage %d: timed out waiting for trial completion (trial %d)",
                             self._cage_id, trial_count)
                break

            with self._lock:
                result  = self._last_result or {}
                stopped = self._stop

            if stopped:
                logger.info("Cage %d: run stopped after trial %d", self._cage_id, trial_count)
                break

            outcome = result.get("outcome", "correct")
            failed  = outcome != "correct"
            iti     = fail_iti_s if failed else base_iti_s
            logger.debug("Cage %d: trial %d done (outcome=%s) — ITI %.1fs",
                         self._cage_id, trial_count, outcome, iti)

            # Pre-compute the next trial during the ITI with bias applied.
            # self._last_click_ratio holds the ratio of the trial just completed —
            # exactly what the bias algorithms need. We intentionally do NOT update
            # self._last_click_ratio here: the switch block above must still be able
            # to read the last-completed ratio if a substage switch arrives mid-ITI.
            with self._lock:
                last_click_ratio = self._last_click_ratio
            trial_for_resolve = (
                _apply_bias(trial_definition, self._subject_id,
                            last_click_ratio=last_click_ratio)
                if self._subject_id is not None else trial_definition
            )
            resolved, correct_side = _resolve_sides(trial_for_resolve)
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
                        logger.info("Cage %d: run stopped during ITI after trial %d",
                                    self._cage_id, trial_count)
                        break

        logger.info("Cage %d: run finished (%d trial(s) completed)",
                    self._cage_id, trial_count)


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
        logger.exception("bias_alg lookup failed for subject %d", subject_id)
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
        logger.exception("recent trial query failed for subject %d", subject_id)
        return []
    finally:
        conn.close()


def _apply_bias(trial_definition: dict, subject_id: int,
                last_click_ratio: float | None = None) -> dict:
    """Return a (possibly modified) trial dict with left_probability set by the bias algorithm.

    Returns the original dict unchanged when bias does not apply.
    Add new algorithms in ui/bias_algorithms.py.

    last_click_ratio: high_clicks / low_clicks of the most recently completed trial.
        Passed through to the algorithm; used by IBL to gate on easy trials only.
    """
    if trial_definition.get("side_mode") not in ("random", "weighted"):
        return trial_definition  # fixed side: no intervention

    alg = _get_subject_bias_alg(subject_id)
    if alg == "none" or alg not in _BIAS_REGISTRY:
        return trial_definition

    spec = _BIAS_REGISTRY[alg]
    recent = _query_recent_trials(subject_id, window=spec.window)
    left_prob = spec.fn(recent, trial_definition, last_click_ratio)

    if left_prob is None:
        return trial_definition
    return {**trial_definition, "side_mode": "weighted", "left_probability": left_prob}
