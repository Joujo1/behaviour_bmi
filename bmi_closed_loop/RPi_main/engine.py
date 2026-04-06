"""
Trial state machine engine.

Interprets a JSON trial definition and drives hardware via actions.py and
gpio_handler. All transitions are event-driven (GPIO interrupts + timers).

Expected JSON format:
{
    "trial_id": "example",
    "initial_state": "cue_center",
    "states": [
        {
            "id": "cue_center",
            "duration": 10.0,
            "entry_actions": [{ "type": "led_on", "target": "center" }],
            "exit_actions":  [{ "type": "led_off", "target": "center" }],
            "transitions": [
                { "trigger": "beam_break", "target": "center", "next_state": "reward" },
                { "trigger": "timeout",                       "next_state": "iti" }
            ]
        }
    ]
}
"""

import json
import logging
import threading
import time

import gpio_handler
import actions
from config import TRIAL_WATCHDOG_S

logger = logging.getLogger(__name__)


class Engine:
    """Loads a JSON trial definition and runs it as an interrupt-driven state machine."""

    def __init__(self, on_complete=None):
        """
        Args:
            on_complete: callable(trial_id, aborted, events) fired when the trial finishes
                         or is killed by the watchdog.
        """
        self._on_complete = on_complete

        self._states: dict        = {}
        self._trial_id: str       = None
        self._initial_state: str  = None
        self._current_state_id: str = None

        self._timeout_timer:  threading.Timer = None
        self._watchdog_timer: threading.Timer = None

        self._lock = threading.Lock()

        self._trial_start:  float = None
        self._event_buffer: list  = []   # drained every frame by pop_frame_events()
        self._trial_events: list  = []   # full trial log, sent at completion
        self._event_lock = threading.Lock()

        # Per-sensor hold timers: sensor_target → threading.Timer
        # A hold timer is armed on beam-break and cancelled on beam-restore.
        # The transition only fires after the beam has been held for hold_ms.
        self._hold_timers: dict = {}


    def load(self, trial_json) -> None:
        """Parse a JSON trial definition and index all states by their id field."""
        if isinstance(trial_json, str):
            data = json.loads(trial_json)
        else:
            data = trial_json

        self._trial_id     = data.get("trial_id", "unknown")
        self._initial_state = data["initial_state"]
        self._states       = {s["id"]: s for s in data["states"]}
        logger.info("Trial '%s' loaded — %d states", self._trial_id, len(self._states))

    def start(self) -> None:
        """Arm the watchdog, start beam monitoring, and enter the initial state."""
        if not self._states:
            raise RuntimeError("call load() before start()")

        self._trial_start = time.time()

        self._watchdog_timer = threading.Timer(TRIAL_WATCHDOG_S, self._on_watchdog)
        self._watchdog_timer.daemon = True
        self._watchdog_timer.start()

        gpio_handler.start_monitoring(self._on_beam_event)
        self.enter_state(self._initial_state)

    def stop(self) -> None:
        """Abort the trial immediately: cancel all timers, sweep outputs, stop monitoring."""
        self._cancel_timeout()
        self._cancel_watchdog()
        self._cancel_all_hold_timers()
        actions.stop_clicks()
        gpio_handler.stop_monitoring()
        actions.safety_sweep()
        logger.info("Trial '%s' aborted", self._trial_id)

    def pop_frame_events(self) -> tuple:
        """Drain the event buffer and return (current_state_id, events) for the current frame."""
        with self._event_lock:
            events, self._event_buffer = self._event_buffer, []
        return self._current_state_id, events


    def enter_state(self, state_id: str) -> None:
        """Run entry_actions for the new state and arm its timeout timer if duration is set."""
        if state_id in ("__end__", "__correct__", "__wrong__"):
            outcome_map = {"__correct__": "correct", "__wrong__": "wrong", "__end__": "correct"}
            self._end_trial(outcome=outcome_map[state_id])
            return

        state = self._states.get(state_id)
        if state is None:
            logger.error("Unknown state '%s' — aborting trial", state_id)
            self.stop()
            return

        self._current_state_id = state_id
        duration = state.get("duration")
        logger.info("Entering state '%s'  (duration: %ss)",
                    state_id, duration if duration is not None else "none")

        for action in state.get("entry_actions", []):
            if action.get("type") == "play_clicks":
                actions.dispatch(action, on_complete=self._on_clicks_done)
            else:
                actions.dispatch(action)

        if duration is not None:
            self._timeout_timer = threading.Timer(duration, self._on_timeout)
            self._timeout_timer.daemon = True
            self._timeout_timer.start()

    def transition_to(self, next_state_id: str) -> None:
        """Cancel the running timer, run exit_actions of current state, enter the next state."""
        self._cancel_timeout()
        self._cancel_all_hold_timers()
        actions.stop_clicks()

        current = self._states.get(self._current_state_id)
        if current is not None:
            for action in current.get("exit_actions", []):
                actions.dispatch(action)

        logger.info("Transition  '%s' → '%s'", self._current_state_id, next_state_id)
        with self._event_lock:
            entry = {
                "t":    time.time() - self._trial_start,
                "from": self._current_state_id,
                "to":   next_state_id,
            }
            self._event_buffer.append(entry)
            self._trial_events.append(entry)
        self.enter_state(next_state_id)
        

    def _on_beam_event(self, target: str, is_active: bool) -> None:
        """
        Fired by gpio_handler on any beam sensor edge (both entry and exit).

        All events are logged regardless of the current state. A transition is
        only triggered on beam-break (is_active=True) if the current state has
        a matching beam_break transition for this target.
        """
        logger.info("Beam event  target=%-6s  active=%s", target, is_active)

        with self._lock:
            if self._current_state_id is None:
                return

            state = self._states.get(self._current_state_id)
            if state is None:
                return

            with self._event_lock:
                entry = {
                    "t":      time.time() - self._trial_start,
                    "sensor": target,
                    "active": is_active,
                }
                self._event_buffer.append(entry)
                self._trial_events.append(entry)

            # Beam restore: cancel any pending hold timer for this sensor
            if not is_active:
                self._cancel_hold_timer(target)
                return

            for t in state.get("transitions", []):
                if t.get("trigger") == "beam_break" and t.get("target") == target:
                    hold_ms = t.get("hold_ms", 0) or 0
                    if hold_ms > 0:
                        logger.info("Beam break on '%s' — starting hold timer %.0fms", target, hold_ms)
                        self._start_hold_timer(target, t["next_state"], hold_ms)
                    else:
                        self.transition_to(t["next_state"])
                    return  # first matching transition wins

            logger.info("Beam break on '%s' — no transition defined in state '%s' (recorded only)",
                        target, self._current_state_id)

    def _on_timeout(self) -> None:
        """Fire when the current state's duration expires and execute its timeout transition."""
        with self._lock:
            if self._current_state_id is None:
                return

            state = self._states.get(self._current_state_id)
            if state is None:
                return

            for t in state.get("transitions", []):
                if t.get("trigger") == "timeout":
                    logger.info("Timeout in state '%s' → '%s'", self._current_state_id, t["next_state"])
                    self.transition_to(t["next_state"])
                    return

            logger.warning(
                "Timeout in state '%s' but no timeout transition defined — aborting",
                self._current_state_id,
            )
            self.stop()

    def _on_clicks_done(self) -> None:
        """
        Fired by the click-watcher thread when both click trains finish naturally.
        Executes the 'clicks_done' transition of the current state, if one exists.
        """
        with self._lock:
            if self._current_state_id is None:
                return

            state = self._states.get(self._current_state_id)
            if state is None:
                return

            for t in state.get("transitions", []):
                if t.get("trigger") == "clicks_done":
                    logger.info("Clicks done in state '%s' → '%s'",
                                self._current_state_id, t["next_state"])
                    self.transition_to(t["next_state"])
                    return

            logger.info("Clicks done in state '%s' — no clicks_done transition (ignoring)",
                        self._current_state_id)

    def _on_watchdog(self) -> None:
        """Fire if the total trial duration exceeds TRIAL_WATCHDOG_S; aborts and notifies caller."""
        logger.warning(
            "Watchdog fired — trial '%s' exceeded %ds limit",
            self._trial_id, TRIAL_WATCHDOG_S,
        )
        with self._lock:
            self.stop()

        if self._on_complete:
            with self._event_lock:
                events = list(self._trial_events)
            self._on_complete(self._trial_id, outcome="aborted", events=events)

    def _end_trial(self, outcome: str = "correct") -> None:
        """Shut down cleanly and notify the caller of the trial outcome."""
        self._cancel_watchdog()
        gpio_handler.stop_monitoring()
        actions.safety_sweep()
        logger.info("Trial '%s' complete — outcome: %s", self._trial_id, outcome)
        if self._on_complete:
            with self._event_lock:
                events = list(self._trial_events)
            self._on_complete(self._trial_id, outcome=outcome, events=events)

    def _cancel_timeout(self) -> None:
        """Cancel the per-state timeout timer if one is armed."""
        if self._timeout_timer is not None:
            self._timeout_timer.cancel()
            self._timeout_timer = None

    def _cancel_watchdog(self) -> None:
        """Cancel the global trial watchdog timer."""
        if self._watchdog_timer is not None:
            self._watchdog_timer.cancel()
            self._watchdog_timer = None

    def _start_hold_timer(self, target: str, next_state: str, hold_ms: float) -> None:
        """Arm a hold timer for a sensor. Cancels any existing timer for that sensor first."""
        self._cancel_hold_timer(target)
        timer = threading.Timer(
            hold_ms / 1000.0,
            self._on_hold_complete,
            args=(target, next_state, self._current_state_id),
        )
        timer.daemon = True
        self._hold_timers[target] = timer
        timer.start()

    def _cancel_hold_timer(self, target: str) -> None:
        """Cancel the hold timer for a specific sensor if one is armed."""
        timer = self._hold_timers.pop(target, None)
        if timer is not None:
            timer.cancel()
            logger.info("Hold timer cancelled for sensor '%s'", target)

    def _cancel_all_hold_timers(self) -> None:
        """Cancel all pending hold timers (called on state transition or abort)."""
        for target in list(self._hold_timers):
            self._cancel_hold_timer(target)

    def _on_hold_complete(self, target: str, next_state: str, expected_state: str) -> None:
        """
        Fired when a sensor has been held for the required hold_ms duration.
        Checks we are still in the same state before triggering the transition.
        """
        with self._lock:
            if self._current_state_id != expected_state:
                logger.info("Hold complete for '%s' but state changed — ignoring", target)
                return
            self._hold_timers.pop(target, None)
            logger.info("Hold complete for '%s' — transitioning to '%s'", target, next_state)
            self.transition_to(next_state)
