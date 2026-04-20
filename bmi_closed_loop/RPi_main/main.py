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

import json
import logging
import queue
import time
import sys

import gpio_handler
from engine import Engine
from tcp_command_receiver import TCPCommandReceiver
from streamer import CameraStreamer
from udp_sender_pi import UDPSender
from config import TCP_PORT, UDP_STREAM_PORT, FRAME_QUEUE_MAXSIZE


logging.basicConfig( 
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


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
    logger.info("GPIO ready")

    current_engine: Engine = None
    frame_queue: queue.Queue = None
    sender: UDPSender = None
    camera: CameraStreamer = None
    is_streaming: bool = False
    pc_ip: str = None

    receiver: TCPCommandReceiver = None
    gpio_adapter = _GPIOAdapter()


    def on_trial_complete(trial_id: str, outcome: str, events: list) -> None:
        """Push a trial_complete or trial_aborted event back to the PC over TCP."""
        nonlocal current_engine
        trial_start_us = current_engine.trial_start_us if current_engine else None
        current_engine = None
        event = "trial_aborted" if outcome == "aborted" else "trial_complete"
        payload = json.dumps({"event": event, "trial_id": trial_id, "outcome": outcome,
                              "events": events, "trial_start_us": trial_start_us})
        logger.info("Trial finished: event=%s  outcome=%s  trial_id=%s  n_events=%d", event, outcome, trial_id, len(events))
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
                                    fsm_data_cb=lambda: current_engine.pop_frame_events()
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
