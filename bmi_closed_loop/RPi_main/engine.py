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
from collections.abc import Callable

import gpio_handler
import actions
from config import TRIAL_WATCHDOG_S

logger = logging.getLogger(__name__)

# Busy-wait the last 300µs of every hold timer for sub-millisecond accuracy.
# The coarse sleep releases the CPU; the tail burns one core for ≤300µs per hold.
_HOLD_BUSY_TAIL_S = 0.0003


def _set_rt_priority(priority: int = 70) -> None:
    """Elevate the calling thread to SCHED_FIFO and pin it to the RT core."""
    class _Param(ctypes.Structure):
        _fields_ = [("sched_priority", ctypes.c_int)]
    _libc = ctypes.CDLL("libc.so.6")
    if os.environ.get("DISABLE_FIFO", "0") != "1":
        ret = _libc.sched_setscheduler(0, 1, ctypes.byref(_Param(priority)))  # SCHED_FIFO=1
        if ret != 0:
            logger.warning("SCHED_FIFO unavailable — run as root for best FSM timing")
    else:
        _libc.sched_setscheduler(0, 0, ctypes.byref(_Param(0)))  # SCHED_OTHER=0
    if os.environ.get("DISABLE_AFFINITY", "0") != "1":
        try:
            os.sched_setaffinity(0, {3})  # isolate RT threads on core 3 (isolcpus=3)
        except OSError:
            pass
    else:
        try:
            os.sched_setaffinity(0, set(range(os.cpu_count() or 4)))
        except OSError:
            pass


class Engine:
    """Loads a JSON trial definition and runs it via a dedicated FSM thread."""

    def __init__(self, on_complete: Callable[[str, str, list], None] | None = None):
        """
        Args:
            on_complete: Called as on_complete(trial_id, outcome, events) when the
                         trial finishes naturally or is killed by the watchdog.
                         Not called on external stop() (STOP_TRIAL command).
        """
        self._on_complete = on_complete

        self._states           = {}
        self._trial_id         = None
        self._initial_state    = None
        self._current_state_id = None

        self._timeout_timer  = None
        self._watchdog_timer = None
        self._hold_timers    = {}

        self._event_queue    = queue.Queue()
        self._fsm_thread     = None
        self._running        = False

        self._trial_start      = None
        self._trial_start_real = None
        self._event_buffer   = []   # drained each frame by pop_frame_events()
        self._trial_events   = []   # full log, sent at trial completion
        self._event_lock     = threading.Lock()
        self._clicks_active  = False


    # -- Public interface --

    @property
    def trial_start_us(self) -> int | None:
        return int(self._trial_start * 1_000_000) if self._trial_start is not None else None

    @property
    def trial_start_real(self) -> float | None:
        return self._trial_start_real

    def load(self, trial_json) -> None:
        """Parse a JSON trial definition and index all states by their id field."""
        if isinstance(trial_json, str):
            data = json.loads(trial_json)
        else:
            data = trial_json

        self._trial_id      = data.get("trial_id", "unknown")
        self._initial_state = data["initial_state"]
        self._states        = {s["id"]: s for s in data["states"]}
        logger.info("Trial '%s' loaded — %d states", self._trial_id, len(self._states))

    def start(self) -> None:
        """Launch the FSM thread, arm the watchdog, and start beam monitoring."""
        if not self._states:
            raise RuntimeError("call load() before start()")

        self._running = True

        self._watchdog_timer = threading.Timer(TRIAL_WATCHDOG_S, self._on_watchdog)
        self._watchdog_timer.daemon = True
        self._watchdog_timer.start()

        self._fsm_thread = threading.Thread(target=self._run, daemon=True, name="fsm")
        self._fsm_thread.start()

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
        gpio_handler.update_callbacks(None)
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

    # -- FSM thread --

    def _run(self) -> None:
        """FSM thread main loop. Sole consumer of _event_queue."""
        _set_rt_priority(70)
        # Capture _trial_start here — after the thread has reached RT priority —
        # so the first state's timeout deadline is measured from the same epoch.
        self._trial_start      = time.clock_gettime(time.CLOCK_MONOTONIC)
        self._trial_start_real = time.clock_gettime(time.CLOCK_REALTIME)
        gpio_handler.update_callbacks(self._on_beam_event)
        self._event_queue.put(('enter', self._initial_state))
        _last_temp_log = time.monotonic()
        while self._running:
            try:
                event = self._event_queue.get(timeout=0.1)
            except queue.Empty:
                if time.monotonic() - _last_temp_log >= 10.0:
                    try:
                        with open('/sys/class/thermal/thermal_zone0/temp') as _f:
                            _temp_c = int(_f.read()) / 1000.0
                        logger.info("CPU temperature: %.1f°C", _temp_c)
                    except OSError:
                        pass
                    _last_temp_log = time.monotonic()
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

    # -- External event sources --

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
        """Hold timer callback."""
        self._event_queue.put(('hold', target, next_state, expected_state))

    # -- FSM handlers --

    def _handle_beam(self, target: str, is_active: bool, t: float) -> None:
        """Process a beam sensor edge. t was captured at interrupt time."""
        logger.debug("Beam event  target=%-6s  active=%s", target, is_active)

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
                    logger.debug("Beam break on '%s' — starting hold timer %.0fms", target, hold_ms)
                    self._start_hold_timer(target, tr["next_state"], hold_ms)
                else:
                    self.transition_to(tr["next_state"])
                return  # first matching transition wins

        logger.debug("Beam break on '%s' — no transition in state '%s' (recorded only)",
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
                logger.debug("Timeout in state '%s' → '%s'", self._current_state_id, tr["next_state"])
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
                logger.debug("Clicks done in state '%s' → '%s'",
                            self._current_state_id, tr["next_state"])
                self.transition_to(tr["next_state"])
                return

        if self._clicks_active:
            self._log_output("clicks", False)
            self._clicks_active = False
        logger.debug("Clicks done in state '%s' — no clicks_done transition (ignoring)",
                    self._current_state_id)

    def _handle_watchdog(self) -> None:
        """Process watchdog expiry."""
        logger.warning("Watchdog fired — trial '%s' exceeded %ds limit",
                       self._trial_id, TRIAL_WATCHDOG_S)
        self._finish_trial_from_fsm("aborted")

    def _handle_hold_complete(self, target: str, next_state: str, expected_state: str) -> None:
        """Process hold timer expiry."""
        if self._current_state_id != expected_state:
            logger.debug("Hold complete for '%s' but state changed — ignoring", target)
            return
        self._hold_timers.pop(target, None)
        logger.debug("Hold complete for '%s' — transitioning to '%s'", target, next_state)
        self.transition_to(next_state)

    # -- State machine core --

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
        logger.debug("Entering state '%s'  (duration: %ss)",
                    state_id, duration if duration is not None else "none")

        for action in state.get("entry_actions", []):
            self._dispatch_action(action)

        if duration is not None:
            self._start_timeout_timer(duration)

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

        logger.debug("Transition  '%s' → '%s'", self._current_state_id, next_state_id)
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

    # -- Trial lifecycle --

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
        gpio_handler.update_callbacks(None)
        actions.safety_sweep()
        logger.info("Trial '%s' finished — outcome: %s", self._trial_id, outcome)
        if self._on_complete:
            with self._event_lock:
                events = list(self._trial_events)
            self._on_complete(self._trial_id, outcome=outcome, events=events)

    # -- Timer helpers --

    def _start_timeout_timer(self, duration: float) -> None:
        """RT-accurate state timeout — mirrors _start_hold_timer."""
        self._cancel_timeout()
        stop_ev  = threading.Event()
        deadline = time.clock_gettime(time.CLOCK_MONOTONIC) + duration

        def _run():
            _set_rt_priority(72)   # same level as hold timer, preempts FSM (70)
            sleep_for = deadline - time.clock_gettime(time.CLOCK_MONOTONIC) - _HOLD_BUSY_TAIL_S
            if sleep_for > 0:
                if stop_ev.wait(sleep_for):
                    return
            while not stop_ev.is_set():
                if time.clock_gettime(time.CLOCK_MONOTONIC) >= deadline:
                    break
            if not stop_ev.is_set():
                self._on_timeout()

        t = threading.Thread(target=_run, daemon=True, name="timeout")
        self._timeout_timer = (t, stop_ev)
        t.start()

    def _cancel_timeout(self) -> None:
        if self._timeout_timer is not None:
            _, stop_ev = self._timeout_timer
            stop_ev.set()
            self._timeout_timer = None

    def _cancel_watchdog(self) -> None:
        if self._watchdog_timer is not None:
            self._watchdog_timer.cancel()
            self._watchdog_timer = None

    def _start_hold_timer(self, target: str, next_state: str, hold_ms: float) -> None:
        self._cancel_hold_timer(target)
        stop_ev      = threading.Event()
        deadline     = time.clock_gettime(time.CLOCK_MONOTONIC) + hold_ms / 1000.0
        expect_state = self._current_state_id

        def _hold_run():
            # SCHED_FIFO 72 — preempts FSM (70) but not gpiod monitor (75).
            # Coarse sleep releases the CPU, busy-wait tail gives µs-level accuracy.
            _set_rt_priority(72)
            sleep_for = deadline - time.clock_gettime(time.CLOCK_MONOTONIC) - _HOLD_BUSY_TAIL_S
            if sleep_for > 0:
                if stop_ev.wait(sleep_for):   # returns True if cancelled
                    return
            while not stop_ev.is_set():
                if time.clock_gettime(time.CLOCK_MONOTONIC) >= deadline:
                    break
            if not stop_ev.is_set():
                self._on_hold_complete(target, next_state, expect_state)

        t = threading.Thread(target=_hold_run, daemon=True, name=f'hold-{target}')
        self._hold_timers[target] = (t, stop_ev)
        t.start()

    def _cancel_hold_timer(self, target: str) -> None:
        entry = self._hold_timers.pop(target, None)
        if entry is not None:
            _, stop_ev = entry
            stop_ev.set()
            logger.debug("Hold timer cancelled for sensor '%s'", target)

    def _cancel_all_hold_timers(self) -> None:
        for target in list(self._hold_timers):
            self._cancel_hold_timer(target)
