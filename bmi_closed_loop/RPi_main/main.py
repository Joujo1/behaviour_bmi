"""
Entry point for the Pi-side trial controller.

Start-up sequence:
  1. Configure logging
  2. Set up GPIO pins
  3. Start the TCP receiver
  4. All further activity is event-driven (TCP commands, GPIO, timers)

TCP protocol (newline-terminated):
  PC → Pi   START_STREAMING\n   start camera + UDP stream to PC
  PC → Pi   STOP_STREAMING\n    stop camera + UDP stream
  PC → Pi   {trial JSON}\n      start a new trial
  PC → Pi   STOP_TRIAL\n        abort the running trial

  Pi → PC   ACK:ok\n            command accepted
  Pi → PC   ERROR:reason\n      command rejected
  Pi → PC   {"event": "trial_complete", "trial_id": "...", "events": [...]}\n
  Pi → PC   {"event": "trial_aborted",  "trial_id": "...", "events": [...]}\n
"""

import ctypes
import ctypes.util
import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
import sys

import gpio_handler
import actions as _actions
import emulator as _emulator
from engine import Engine
from tcp_command_receiver import TCPCommandReceiver
from streamer import CameraStreamer
from udp_sender_pi import UDPSender
from config import TCP_PORT, UDP_STREAM_PORT, FRAME_QUEUE_MAXSIZE, EMULATE, EMULATE_OUTCOMES


# ── Kernel tuning switches ────────────────────────────────────────────────────
# Set to True to disable that tuning; False (default) = tuning active.
_DISABLE_GIL      = False
_DISABLE_THROTTLE = False
_DISABLE_MLOCK    = False
_DISABLE_FIFO     = False
_DISABLE_AFFINITY = False

# Propagate FIFO/affinity flags to engine.py and gpio_handler.py, which read
# these via os.environ inside their thread start-up routines.
if _DISABLE_FIFO:
    os.environ["DISABLE_FIFO"] = "1"
    # Reset the process from SCHED_FIFO (applied by systemd CPUSchedulingPolicy=fifo)
    # back to SCHED_OTHER so all spawned threads inherit normal scheduling.
    try:
        class _SchedParam(ctypes.Structure):
            _fields_ = [("sched_priority", ctypes.c_int)]
        ctypes.CDLL(ctypes.util.find_library('c')).sched_setscheduler(
            0, 0, ctypes.byref(_SchedParam(0)))  # SCHED_OTHER=0
    except Exception:
        pass
if _DISABLE_AFFINITY:
    os.environ["DISABLE_AFFINITY"] = "1"

if not _DISABLE_GIL:
    # Reduce GIL check interval from default 5ms → 100µs so the gpiod monitor
    # thread acquires the GIL faster after a beam-break interrupt.
    sys.setswitchinterval(0.0001)

# Must actively write 950000 when disabled — sysctl.d/99-rt.conf already set -1
# at boot, so simply skipping the write would leave the throttle off regardless.
try:
    with open('/proc/sys/kernel/sched_rt_runtime_us', 'w') as _f:
        _f.write('-1\n' if not _DISABLE_THROTTLE else '950000\n')
except OSError:
    pass

if not _DISABLE_MLOCK:
    # Lock all current and future memory pages to prevent page-fault latency spikes
    # in the gpiod monitor and FSM threads. Requires root / CAP_IPC_LOCK.
    try:
        _libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
        if _libc.mlockall(ctypes.c_int(3)) != 0:  # MCL_CURRENT=1 | MCL_FUTURE=2
            raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
    except OSError:
        pass  # non-fatal; add LimitMEMLOCK=infinity to service file if needed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _get_ntp_status() -> dict:
    """Query chronyc tracking and return a sync_status event dict."""
    base = {"event": "sync_status", "synced": False,
            "offset_us": None, "esterror_us": None, "freq_ppm": None}
    try:
        out = subprocess.run(
            ["chronyc", "-n", "tracking"],
            capture_output=True, text=True, timeout=2,
        ).stdout
        m_sys  = re.search(r"System time\s*:\s*([\d.e+-]+)\s+seconds\s+(slow|fast)", out)
        m_rms  = re.search(r"RMS offset\s*:\s*([\d.e+-]+)\s+seconds", out)
        m_freq = re.search(r"Frequency\s*:\s*([\d.]+)\s+ppm\s+(slow|fast)", out)
        m_leap = re.search(r"Leap status\s*:\s*(.+)", out)

        synced = m_leap is not None and m_leap.group(1).strip() == "Normal"
        if m_sys:
            sign = 1 if m_sys.group(2) == "slow" else -1
            base["offset_us"] = round(sign * float(m_sys.group(1)) * 1e6, 1)
        if m_rms:
            base["esterror_us"] = round(float(m_rms.group(1)) * 1e6, 1)
        if m_freq:
            sign = 1 if m_freq.group(2) == "slow" else -1
            base["freq_ppm"] = round(sign * float(m_freq.group(1)), 3)
        base["synced"] = synced
    except Exception:
        pass
    return base


class _GPIOAdapter:
    """Translates gpio_handler.get_snapshot() into the flat dict CameraStreamer expects."""

    def get_current_state(self):
        snap = gpio_handler.get_snapshot()
        return {
            "led_center":  bool(snap.get("led_center_tracked",   0)),
            "led_left":    bool(snap.get("led_left_tracked",     0)),
            "led_right":   bool(snap.get("led_right_tracked",    0)),
            "valve_left":  bool(snap.get("valve_left_tracked",   0)),
            "valve_right": bool(snap.get("valve_right_tracked",  0)),
            "beam_left":   bool(snap.get("beam_left",            0)),
            "beam_right":  bool(snap.get("beam_right",           0)),
            "beam_center": bool(snap.get("beam_center",          0)),
        }


def main():
    gpio_handler.setup()
    if not EMULATE:
        gpio_handler.start_monitoring()
    else:
        logger.info("EMULATE=True — beam monitoring disabled, synthetic events active")
    logger.info("GPIO ready")

    current_engine  = None
    _outcome_iter   = iter(EMULATE_OUTCOMES) if EMULATE else iter([])
    frame_queue    = None
    sender         = None
    camera         = None
    is_streaming   = False
    pc_ip          = None

    receiver     = None
    gpio_adapter = _GPIOAdapter()

    def on_trial_complete(trial_id: str, outcome: str, events: list) -> None:
        """Push a trial_complete or trial_aborted event back to the PC over TCP."""
        nonlocal current_engine
        trial_start_us   = current_engine.trial_start_us   if current_engine else None
        trial_start_real = current_engine.trial_start_real if current_engine else None
        current_engine = None
        event = "trial_aborted" if outcome == "aborted" else "trial_complete"
        payload = json.dumps({"event": event, "trial_id": trial_id, "outcome": outcome,
                              "events": events, "trial_start_us": trial_start_us,
                              "trial_start_real": trial_start_real})
        logger.info("Trial finished: event=%s  outcome=%s  trial_id=%s  n_events=%d",
                    event, outcome, trial_id, len(events))
        receiver.push(payload)

    def handle_command(command: str):
        """Dispatch a single newline-terminated command from the PC."""
        nonlocal current_engine, frame_queue, sender, camera, is_streaming

        if command == "START_STREAMING":
            if is_streaming:
                return False, "already streaming"
            if pc_ip is None:
                return False, "PC IP not known yet"
            frame_queue = queue.Queue(maxsize=FRAME_QUEUE_MAXSIZE)
            sender = UDPSender(target_ip=pc_ip, target_port=UDP_STREAM_PORT,
                               data_queue=frame_queue)
            sender.start()
            camera = CameraStreamer(data_queue=frame_queue,
                                    gpio_controller=gpio_adapter,
                                    fsm_data_cb=lambda ts: current_engine.pop_frame_events(ts)
                                                           if current_engine else (0, []))
            camera.start()
            is_streaming = True
            logger.info("Streaming started → %s:%d", pc_ip, UDP_STREAM_PORT)
            return True, "ok"

        if command == "STOP_STREAMING":
            if not is_streaming:
                return False, "not streaming"
            if camera: camera.stop()
            if sender:  sender.stop()
            camera, sender, frame_queue = None, None, None
            is_streaming = False
            logger.info("Streaming stopped")
            return True, "ok"

        if command == "STOP_TRIAL":
            if current_engine is None:
                return False, "no trial running"
            current_engine.stop()
            current_engine = None
            return True, "trial stopped"

        if command == "FAN_ON":
            gpio_handler.set_fan(True)
            return True, "fan on"
        if command == "FAN_OFF":
            gpio_handler.set_fan(False)
            return True, "fan off"
        if command.startswith("FAN_PWM:"):
            try:
                duty = float(command.split(":", 1)[1])
                gpio_handler.set_fan_pwm(duty)
                return True, f"fan pwm {duty:.0f}%"
            except (ValueError, IndexError) as e:
                return False, f"invalid duty: {e}"
        if command == "STRIP_ON":
            gpio_handler.set_strip(True)
            return True, "strip on"
        if command == "STRIP_OFF":
            gpio_handler.set_strip(False)
            return True, "strip off"

        try:
            trial_data = json.loads(command)
        except json.JSONDecodeError as e:
            return False, f"JSON parse error: {e}"

        if current_engine is not None:
            logger.warning("New trial received while one is running — stopping current trial")
            current_engine.stop()

        current_engine = Engine(on_complete=on_trial_complete)
        try:
            current_engine.load(trial_data)
        except (KeyError, ValueError) as e:
            current_engine = None
            return False, f"invalid trial definition: {e}"

        current_engine.start()

        if EMULATE:
            outcome = next(_outcome_iter, "correct")
            _emulator.run_trial(trial_data, outcome)

        return True, "ok"

    def on_connect(ip: str) -> None:
        """Record the PC's IP address so the UDP stream knows where to send frames."""
        nonlocal pc_ip
        pc_ip = ip
        logger.info("PC IP set to %s", ip)

    receiver = TCPCommandReceiver(
        port=TCP_PORT,
        command_handler=handle_command,
        on_connect=on_connect,
    )

    try:
        receiver.start()
        logger.info("Ready — TCP port %d  UDP stream port %d", TCP_PORT, UDP_STREAM_PORT)

        def _ntp_reporter():
            while True:
                time.sleep(5)
                try:
                    receiver.push(json.dumps(_get_ntp_status()))
                except Exception:
                    pass

        threading.Thread(target=_ntp_reporter, daemon=True, name="ntp-reporter").start()

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Interrupted — shutting down")
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
    finally:
        if current_engine is not None:
            current_engine.stop()
        if is_streaming:
            if camera: camera.stop()
            if sender:  sender.stop()
        receiver.stop()
        gpio_handler.cleanup()
        logger.info("Shutdown complete")
        sys.exit(0)


if __name__ == "__main__":
    main()
