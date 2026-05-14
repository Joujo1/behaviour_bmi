"""
Trial state machine engine.

Interprets a JSON trial definition and drives hardware via actions.py and
gpio_handler. All transitions are event-driven (GPIO interrupts + timers).

Architecture
------------
The Engine owns a single dedicated FSM thread (_run). Every external source
that wants to trigger a transition posts a tuple to _event_queue and returns
immediately:

    GPIO interrupt thread  →  _on_beam_event()    →  queue.put(('beam', ...))
    threading.Timer        →  _on_timeout()        →  queue.put(('timeout',))
    threading.Timer        →  _on_watchdog()       →  queue.put(('watchdog',))
    threading.Timer        →  _on_hold_complete()  →  queue.put(('hold', ...))
    click-player thread    →  _on_clicks_done()    →  queue.put(('clicks_done',))

The FSM thread is the sole consumer. State transitions, hardware writes, and
event logging all happen exclusively in that thread, so no lock is needed on
_current_state_id or the transition logic.

_event_lock is still used for _event_buffer / _trial_events because
pop_frame_events() is called from the picamera2 encoder thread.

Timestamp policy
----------------
- Sensor inputs  : stamped from the kernel GPIO interrupt timestamp
                   (ev.timestamp_ns / 1e9) passed into _on_beam_event() by the
                   gpiod monitor thread. Reflects the exact moment the
                   hardware interrupt fired, not when Python ran the callback.
- Hardware outputs: stamped in _dispatch_action() *after* actions.dispatch()
                   returns, so t reflects when the GPIO pin actually changed.
- State transitions: stamped in transition_to() at decision time (FSM thread).

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
                { "trigger": "timeout",                        "next_state": "iti" }
            ]
        }
    ]
}
"""

import ctypes
import json
import logging
import os
import queue
import threading
import time

import gpio_handler
import actions
from config import TRIAL_WATCHDOG_S

logger = logging.getLogger(__name__)


def _set_rt_priority(priority: int = 70) -> None:
    """Elevate the calling thread to SCHED_FIFO and pin it to the RT core."""
    SCHED_FIFO = 1
    class _Param(ctypes.Structure):
        _fields_ = [("sched_priority", ctypes.c_int)]
    ret = ctypes.CDLL("libc.so.6").sched_setscheduler(0, SCHED_FIFO, ctypes.byref(_Param(priority)))
    if ret != 0:
        logger.warning("SCHED_FIFO unavailable — run as root for best FSM timing")
    try:
        os.sched_setaffinity(0, {3})  # isolate RT threads on core 3 (isolcpus=3)
    except OSError:
        pass


class Engine:
    """Loads a JSON trial definition and runs it via a dedicated FSM thread."""

    def __init__(self, on_complete=None):
        """
        Args:
            on_complete: callable(trial_id, outcome, events) fired when the
                         trial finishes naturally or is killed by the watchdog.
                         Not called on external stop() (STOP_TRIAL command).
        """
        self._on_complete = on_complete

        self._states: dict          = {}
        self._trial_id: str         = None
        self._initial_state: str    = None
        self._current_state_id: str = None

        self._timeout_timer:  threading.Timer = None
        self._watchdog_timer: threading.Timer = None
        self._hold_timers:    dict            = {}

        # FSM thread and its event queue
        self._event_queue: queue.Queue    = queue.Queue()
        self._fsm_thread:  threading.Thread = None
        self._running:     bool           = False

        self._trial_start:  float = None
        self._event_buffer: list  = []   # drained each frame by pop_frame_events()
        self._trial_events: list  = []   # full log, sent at trial completion
        self._event_lock = threading.Lock()
        self._clicks_active = False

        # Fast-reaction table: (state_id, beam_target) → list of action dicts
        # for zero-hold beam_break transitions. Populated in _build_fast_table().
        self._fast_table: dict = {}

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    @property
    def trial_start_us(self) -> int | None:
        return int(self._trial_start * 1_000_000) if self._trial_start is not None else None

    def load(self, trial_json) -> None:
        """Parse a JSON trial definition and index all states by their id field."""
        if isinstance(trial_json, str):
            data = json.loads(trial_json)
        else:
            data = trial_json

        self._trial_id      = data.get("trial_id", "unknown")
        self._initial_state = data["initial_state"]
        self._states        = {s["id"]: s for s in data["states"]}
        self._build_fast_table()
        logger.info("Trial '%s' loaded — %d states, %d fast-path reactions",
                    self._trial_id, len(self._states), len(self._fast_table))

    def start(self) -> None:
        """Launch the FSM thread, arm the watchdog, and start beam monitoring."""
        if not self._states:
            raise RuntimeError("call load() before start()")

        self._trial_start = time.clock_gettime(time.CLOCK_MONOTONIC)
        self._running     = True

        self._fsm_thread = threading.Thread(target=self._run, daemon=True, name="fsm")
        self._fsm_thread.start()

        self._watchdog_timer = threading.Timer(TRIAL_WATCHDOG_S, self._on_watchdog)
        self._watchdog_timer.daemon = True
        self._watchdog_timer.start()

        gpio_handler.start_monitoring(
            self._on_beam_event,
            fast_reaction=self._fast_reaction if self._fast_table else None,
        )
        self._event_queue.put(('enter', self._initial_state))

    def stop(self) -> None:
        """Abort the trial from an external thread (e.g. the TCP command thread).

        Cancels all timers and stops GPIO monitoring immediately, then waits
        for the FSM thread to finish its current event before sweeping all
        hardware outputs low. This ordering guarantees that no action runs
        after safety_sweep().
        """
        self._running = False
        self._event_queue.put(('stop',))   # wake the FSM thread immediately
        self._cancel_timeout()
        self._cancel_watchdog()
        self._cancel_all_hold_timers()
        actions.stop_clicks()
        gpio_handler.stop_monitoring()
        if self._fsm_thread and self._fsm_thread.is_alive():
            self._fsm_thread.join(timeout=1.0)
        actions.safety_sweep()
        logger.info("Trial '%s' aborted", self._trial_id)

    def pop_frame_events(self, frame_ts_us: int = None) -> tuple:
        """Return events whose timestamp <= frame_ts_us; hold the rest for future frames.

        Called from the picamera2 encoder thread. _event_lock protects the
        shared buffer against concurrent writes from the FSM thread.
        Pass frame_ts_us=None to drain everything (e.g. no trial active).
        """
        with self._event_lock:
            if frame_ts_us is None or self._trial_start is None:
                events, self._event_buffer = self._event_buffer, []
            else:
                cutoff_t = frame_ts_us / 1_000_000 - self._trial_start
                events             = [e for e in self._event_buffer if e["t"] <= cutoff_t]
                self._event_buffer = [e for e in self._event_buffer if e["t"] >  cutoff_t]
        return self._current_state_id, events

    # ------------------------------------------------------------------ #
    # FSM thread                                                           #
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        """FSM thread main loop. Sole consumer of _event_queue."""
        _set_rt_priority(70)
        while self._running:
            try:
                event = self._event_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            kind = event[0]
            if kind == 'stop':
                break
            elif kind == 'enter':
                self.enter_state(event[1])
            elif kind == 'beam':
                self._handle_beam(event[1], event[2], event[3])
            elif kind == 'timeout':
                self._handle_timeout()
            elif kind == 'hold':
                self._handle_hold_complete(event[1], event[2], event[3])
            elif kind == 'clicks_done':
                self._handle_clicks_done()
            elif kind == 'watchdog':
                self._handle_watchdog()

    # ------------------------------------------------------------------ #
    # External event sources — post to queue, return immediately          #
    # ------------------------------------------------------------------ #

    def _on_beam_event(self, target: str, is_active: bool, t_mono: float) -> None:
        """GPIO interrupt callback. t_mono is CLOCK_MONOTONIC seconds from the
        kernel hardware interrupt timestamp, recorded at the moment the edge fired."""
        t = t_mono - self._trial_start
        self._event_queue.put(('beam', target, is_active, t))

    def _on_timeout(self) -> None:
        """State timeout timer callback."""
        self._event_queue.put(('timeout',))

    def _on_clicks_done(self) -> None:
        """Click-player thread callback — fires when audio finishes naturally."""
        self._event_queue.put(('clicks_done',))

    def _on_watchdog(self) -> None:
        """Watchdog timer callback."""
        self._event_queue.put(('watchdog',))

    def _on_hold_complete(self, target: str, next_state: str, expected_state: str) -> None:
        """Hold timer callback. Fire LED/valve writes immediately before queuing."""
        if self._current_state_id == expected_state:
            self._fast_execute_transition(expected_state, next_state)
        self._event_queue.put(('hold', target, next_state, expected_state))

    # ------------------------------------------------------------------ #
    # Fast-path reaction — runs in the gpiod monitor thread (prio 75)    #
    # ----------------------------------------------------------------- #

    def _build_fast_table(self) -> None:
        """Precompute (state_id, beam_target) → [action_dicts] for immediate
        beam_break transitions (hold_ms == 0).  Called once per load().

        Only LED and valve actions are included — they are idempotent and safe
        to call from the callback thread.  play_clicks is excluded (needs its
        own thread).  hold_ms > 0 transitions are excluded (must wait for hold).
        """
        _FAST_TYPES = frozenset(('led_on', 'led_off', 'valve_open', 'valve_close'))
        table = {}
        for state_id, state in self._states.items():
            for tr in state.get('transitions', []):
                if tr.get('trigger') != 'beam_break':
                    continue
                if tr.get('hold_ms', 0):
                    continue
                tgt = tr.get('target')
                fast_acts = [a for a in state.get('exit_actions', [])
                             if a.get('type') in _FAST_TYPES]
                next_state = self._states.get(tr.get('next_state', ''))
                if next_state:
                    fast_acts += [a for a in next_state.get('entry_actions', [])
                                  if a.get('type') in _FAST_TYPES]
                if fast_acts:
                    table[(state_id, tgt)] = fast_acts
        self._fast_table = table

    def _fast_reaction(self, target: str, is_active: bool) -> None:
        """Execute LED/valve writes immediately in the gpiod monitor thread.

        Called before the beam event is posted to the FSM queue, eliminating
        the ~1.5–2ms queue-to-FSM-thread hop for the critical output path.
        The FSM thread re-executes the same writes later (idempotent).
        """
        if not is_active:
            return
        state_id = self._current_state_id   # GIL-atomic read in CPython
        if state_id is None:
            return
        fast_acts = self._fast_table.get((state_id, target))
        if fast_acts:
            self._fast_execute(fast_acts)

    def _fast_execute_transition(self, from_state_id: str, to_state_id: str) -> None:
        """Execute LED/valve exit_actions + entry_actions for a transition immediately.

        Called from timer callbacks (hold, timeout) to fire output writes without
        waiting for the FSM thread to dequeue the event.
        """
        _FAST_TYPES = frozenset(('led_on', 'led_off', 'valve_open', 'valve_close'))
        fast_acts = []
        from_state = self._states.get(from_state_id)
        if from_state:
            fast_acts += [a for a in from_state.get('exit_actions', [])
                          if a.get('type') in _FAST_TYPES]
        to_state = self._states.get(to_state_id)
        if to_state:
            fast_acts += [a for a in to_state.get('entry_actions', [])
                          if a.get('type') in _FAST_TYPES]
        self._fast_execute(fast_acts)

    def _fast_execute(self, actions_list: list) -> None:
        """Drive GPIO pins for a precomputed list of LED/valve action dicts."""
        for act in actions_list:
            atype = act['type']
            tgt   = act.get('target')
            if   atype == 'led_on':      gpio_handler.set_led(tgt, True)
            elif atype == 'led_off':     gpio_handler.set_led(tgt, False)
            elif atype == 'valve_open':  gpio_handler.set_valve(tgt, True)
            elif atype == 'valve_close': gpio_handler.set_valve(tgt, False)

    # ------------------------------------------------------------------ #
    # FSM handlers — run exclusively in the FSM thread                    #
    # ------------------------------------------------------------------ #

    def _handle_beam(self, target: str, is_active: bool, t: float) -> None:
        """Process a beam sensor edge. t was captured at interrupt time."""
        logger.info("Beam event  target=%-6s  active=%s", target, is_active)

        if self._current_state_id is None:
            return

        state = self._states.get(self._current_state_id)
        if state is None:
            return

        with self._event_lock:
            entry = {"t": t, "sensor": target, "active": is_active}
            self._event_buffer.append(entry)
            self._trial_events.append(entry)

        if not is_active:
            self._cancel_hold_timer(target)
            return

        for tr in state.get("transitions", []):
            if tr.get("trigger") == "beam_break" and tr.get("target") == target:
                hold_ms = tr.get("hold_ms", 0) or 0
                if hold_ms > 0:
                    logger.info("Beam break on '%s' — starting hold timer %.0fms", target, hold_ms)
                    self._start_hold_timer(target, tr["next_state"], hold_ms)
                else:
                    self.transition_to(tr["next_state"])
                return  # first matching transition wins

        logger.info("Beam break on '%s' — no transition in state '%s' (recorded only)",
                    target, self._current_state_id)

    def _handle_timeout(self) -> None:
        """Process a state timeout."""
        if self._current_state_id is None:
            return

        state = self._states.get(self._current_state_id)
        if state is None:
            return

        for tr in state.get("transitions", []):
            if tr.get("trigger") == "timeout":
                logger.info("Timeout in state '%s' → '%s'", self._current_state_id, tr["next_state"])
                self.transition_to(tr["next_state"])
                return

        logger.warning("Timeout in state '%s' but no timeout transition defined — aborting",
                       self._current_state_id)
        self._finish_trial_from_fsm("aborted")

    def _handle_clicks_done(self) -> None:
        """Process click train completion."""
        if self._current_state_id is None:
            return

        state = self._states.get(self._current_state_id)
        if state is None:
            return

        for tr in state.get("transitions", []):
            if tr.get("trigger") == "clicks_done":
                logger.info("Clicks done in state '%s' → '%s'",
                            self._current_state_id, tr["next_state"])
                self.transition_to(tr["next_state"])
                return

        if self._clicks_active:
            self._log_output("clicks", False)
            self._clicks_active = False
        logger.info("Clicks done in state '%s' — no clicks_done transition (ignoring)",
                    self._current_state_id)

    def _handle_watchdog(self) -> None:
        """Process watchdog expiry."""
        logger.warning("Watchdog fired — trial '%s' exceeded %ds limit",
                       self._trial_id, TRIAL_WATCHDOG_S)
        self._finish_trial_from_fsm("aborted")

    def _handle_hold_complete(self, target: str, next_state: str, expected_state: str) -> None:
        """Process hold timer expiry."""
        if self._current_state_id != expected_state:
            logger.info("Hold complete for '%s' but state changed — ignoring", target)
            return
        self._hold_timers.pop(target, None)
        logger.info("Hold complete for '%s' — transitioning to '%s'", target, next_state)
        self.transition_to(next_state)

    # ------------------------------------------------------------------ #
    # State machine core — run in FSM thread                              #
    # ------------------------------------------------------------------ #

    def enter_state(self, state_id: str) -> None:
        """Run entry_actions for the new state and arm its timeout timer."""
        if state_id in ("__end__", "__correct__", "__wrong__"):
            outcome_map = {"__correct__": "correct", "__wrong__": "wrong", "__end__": "correct"}
            self._finish_trial_from_fsm(outcome=outcome_map[state_id])
            return

        state = self._states.get(state_id)
        if state is None:
            logger.error("Unknown state '%s' — aborting trial", state_id)
            self._finish_trial_from_fsm("aborted")
            return

        self._current_state_id = state_id
        duration = state.get("duration")
        logger.info("Entering state '%s'  (duration: %ss)",
                    state_id, duration if duration is not None else "none")

        for action in state.get("entry_actions", []):
            self._dispatch_action(action)

        if duration is not None:
            self._timeout_timer = threading.Timer(duration, self._on_timeout)
            self._timeout_timer.daemon = True
            self._timeout_timer.start()

    def transition_to(self, next_state_id: str) -> None:
        """Cancel the running timer, run exit_actions, log the transition, enter next state."""
        self._cancel_timeout()
        self._cancel_all_hold_timers()
        if self._clicks_active:
            self._log_output("clicks", False)
            self._clicks_active = False
        actions.stop_clicks()

        current = self._states.get(self._current_state_id)
        if current is not None:
            for action in current.get("exit_actions", []):
                self._dispatch_action(action)

        logger.info("Transition  '%s' → '%s'", self._current_state_id, next_state_id)
        with self._event_lock:
            entry = {
                "t":    time.clock_gettime(time.CLOCK_MONOTONIC) - self._trial_start,
                "from": self._current_state_id,
                "to":   next_state_id,
            }
            self._event_buffer.append(entry)
            self._trial_events.append(entry)
        self.enter_state(next_state_id)

    def _dispatch_action(self, action: dict) -> None:
        """Dispatch a hardware action and stamp output events after the write."""
        atype = action.get("type")
        if atype == "play_clicks":
            self._clicks_active = True
        actions.dispatch(action, on_complete=self._on_clicks_done,
                         log_cb=self._log_output if atype == "play_clicks" else None)
        # Stamp after dispatch so t reflects when the hardware actually changed
        if atype == "led_on":
            self._log_output(f"led_{action.get('target', '?')}", True)
        elif atype == "led_off":
            self._log_output(f"led_{action.get('target', '?')}", False)
        elif atype == "valve_open":
            self._log_output(f"valve_{action.get('target', '?')}", True)
        elif atype == "valve_close":
            self._log_output(f"valve_{action.get('target', '?')}", False)

    def _log_output(self, name: str, active: bool) -> None:
        """Append a hardware output event to both the frame buffer and trial log."""
        with self._event_lock:
            entry = {
                "t":      time.clock_gettime(time.CLOCK_MONOTONIC) - self._trial_start,
                "output": name,
                "active": active,
            }
            self._event_buffer.append(entry)
            self._trial_events.append(entry)

    # ------------------------------------------------------------------ #
    # Trial lifecycle                                                      #
    # ------------------------------------------------------------------ #

    def _finish_trial_from_fsm(self, outcome: str) -> None:
        """Clean up and notify the caller. Must only be called from the FSM thread.

        Sets _running=False so the _run loop exits after this event completes.
        Does not join the FSM thread (that would deadlock).
        """
        self._running = False
        self._cancel_timeout()
        self._cancel_watchdog()
        self._cancel_all_hold_timers()
        actions.stop_clicks()
        gpio_handler.stop_monitoring()
        actions.safety_sweep()
        logger.info("Trial '%s' finished — outcome: %s", self._trial_id, outcome)
        if self._on_complete:
            with self._event_lock:
                events = list(self._trial_events)
            self._on_complete(self._trial_id, outcome=outcome, events=events)

    # ------------------------------------------------------------------ #
    # Timer helpers                                                        #
    # ------------------------------------------------------------------ #

    def _cancel_timeout(self) -> None:
        if self._timeout_timer is not None:
            self._timeout_timer.cancel()
            self._timeout_timer = None

    def _cancel_watchdog(self) -> None:
        if self._watchdog_timer is not None:
            self._watchdog_timer.cancel()
            self._watchdog_timer = None

    def _start_hold_timer(self, target: str, next_state: str, hold_ms: float) -> None:
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
        timer = self._hold_timers.pop(target, None)
        if timer is not None:
            timer.cancel()
            logger.info("Hold timer cancelled for sensor '%s'", target)

    def _cancel_all_hold_timers(self) -> None:
        for target in list(self._hold_timers):
            self._cancel_hold_timer(target)
