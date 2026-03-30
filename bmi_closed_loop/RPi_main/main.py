"""
Entry point for the Pi-side trial controller.

Start-up sequence:
  1. Configure logging
  2. Set up GPIO pins
  3. Start the TCP receiver
  4. Wait — all further activity is event-driven (TCP commands, GPIO, timers)

TCP protocol (newline-terminated):
  PC → Pi   START_STREAMING\n   start camera + UDP stream to PC
  PC → Pi   STOP_STREAMING\n    stop camera + UDP stream
  PC → Pi   {trial JSON}\n      start a new trial
  PC → Pi   STOP_TRIAL\n        abort the running trial

  Pi → PC   ACK:ok\n            command accepted
  Pi → PC   ERROR:reason\n      command rejected
  Pi → PC   {"event": "trial_complete", "trial_id": "..."}\n
  Pi → PC   {"event": "trial_aborted",  "trial_id": "..."}\n
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

TCP_PORT        = 6000
UDP_STREAM_PORT = 5005

logging.basicConfig( 
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# TODO (GPIO state → frames):
#   Replace _GPIOAdapter with a real implementation that calls
#   gpio_handler.get_snapshot() and maps the key names to what
#   UDPSender._pack_and_send expects:
#     gpio_handler key          →  UDPSender key
#     "led_center_tracked"      →  "led_center"
#     "valve_left_tracked"      →  "valve_left"
#     "valve_right_tracked"     →  "valve_right"
#     "ir_left"                 →  "sensor_left"
#     "ir_right"                →  "sensor_right"
#     "ir_center"               →  "sensor_center"
#   Once this is done, delete _GPIOAdapter entirely and pass the real
#   adapter to CameraStreamer in handle_command("START_STREAMING").
class _GPIOAdapter:
    """Minimal adapter so CameraStreamer compiles; returns empty state for now."""

    def get_current_state(self):
        """Return a zeroed hardware state dict until snapshot integration is done."""
        return {
            "led_center":    False,
            "valve_left":    False,
            "valve_right":   False,
            "sensor_left":   False,
            "sensor_right":  False,
            "sensor_center": False,
        }


def main():
    gpio_handler.setup()
    logger.info("GPIO ready")

    # Mutable state — modified inside nested callbacks via nonlocal
    current_engine: Engine          = None
    frame_queue:    queue.Queue     = None
    sender:         UDPSender       = None
    camera:         CameraStreamer  = None
    is_streaming:   bool            = False
    pc_ip:          str             = None

    receiver: TCPCommandReceiver = None
    gpio_adapter = _GPIOAdapter()

    # ------------------------------------------------------------------
    # Trial completion callback
    # ------------------------------------------------------------------

    def on_trial_complete(trial_id: str, aborted: bool) -> None:
        """Push a trial_complete or trial_aborted event back to the PC over TCP."""
        event = "trial_aborted" if aborted else "trial_complete"
        payload = json.dumps({"event": event, "trial_id": trial_id})
        logger.info("Trial finished: event=%s  trial_id=%s", event, trial_id)
        receiver.push(payload)

    # ------------------------------------------------------------------
    # TCP command handler
    # ------------------------------------------------------------------

    def handle_command(command: str):
        """Dispatch a single newline-terminated command from the PC."""
        nonlocal current_engine, frame_queue, sender, camera, is_streaming

        # ---- Streaming ----

        if command == "START_STREAMING":
            if is_streaming:
                return False, "already streaming"
            if pc_ip is None:
                return False, "PC IP not known yet"
            frame_queue = queue.Queue(maxsize=2)
            sender = UDPSender(target_ip=pc_ip, target_port=UDP_STREAM_PORT,
                               data_queue=frame_queue)
            sender.start()
            # TODO (event data → frames):
            #   Replace fsm_data_cb=None with a real callback once the engine
            #   exposes an event buffer. The callback must return:
            #     (current_state_id: int/str, recent_events: list[dict])
            #   The engine's pop_frame_events() (to be added) should drain a
            #   thread-safe buffer of all events since the last frame.
            #   See engine.py TODO for the buffer implementation.
            camera = CameraStreamer(data_queue=frame_queue,
                                    gpio_controller=gpio_adapter,
                                    fsm_data_cb=None)
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

        # ---- Trial control ----

        if command == "STOP_TRIAL":
            if current_engine is None:
                return False, "no trial running"
            current_engine.stop()
            current_engine = None
            return True, "trial stopped"

        # ---- JSON trial definition ----

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

    # ------------------------------------------------------------------
    # PC connect callback — capture IP for UDP
    # ------------------------------------------------------------------

    def on_connect(ip: str) -> None:
        """Record the PC's IP address so the UDP stream knows where to send frames."""
        nonlocal pc_ip
        pc_ip = ip
        logger.info("PC IP set to %s", ip)

    # ------------------------------------------------------------------
    # Start receiver and block
    # ------------------------------------------------------------------

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
