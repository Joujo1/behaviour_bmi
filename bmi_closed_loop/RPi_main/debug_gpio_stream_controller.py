import queue
import sys
import time
import threading
import traceback

from streamer import CameraStreamer
from udp_sender_pi import UDPSender
from trial_parameters import TrialParametersParser
from trial_state_machine import TrialStateMachine
from tcp_command_receiver import TCPCommandReceiver


class MockGPIO:
    def get_current_state(self):
        return {
            'led_center': False, 'valve_left': False, 'valve_right': False,
            'beam_left': False, 'beam_right': False, 'beam_center': True
        }
    def led_center_on(self):             print("[MockGPIO] LED Center ON")
    def led_center_off(self):            print("[MockGPIO] LED Center OFF")
    def start_camera_logging(self):      print("[MockGPIO] Camera Logging Started")
    def stop_camera_logging(self):       print("[MockGPIO] Camera Logging Stopped")
    def cleanup_trial(self):             print("[MockGPIO] Trial Cleanup")
    def deliver_reward_async_left(self): print("[MockGPIO] Reward Left Dispensed!")
    def deliver_reward_async_right(self):print("[MockGPIO] Reward Right Dispensed!")
    def is_central_poke_active(self):    return True
    def is_left_port_active(self):       return False
    def is_right_port_active(self):      return False


class MockAudio:
    def play_click_left(self):  pass
    def play_click_right(self): pass


def run_test_server(tcp_port=6000, stream_port=5005):
    mock_gpio = MockGPIO()
    mock_audio = MockAudio()

    # Mutable state shared between TCP callbacks and the main loop
    frame_queue = None
    sender = None
    camera = None
    is_streaming = False
    current_trial = None
    trial_thread = None
    pc_ip = None

    def get_live_fsm_data():
        if current_trial and current_trial.running:
            return current_trial.current_state.value, current_trial.pop_frame_events()
        return 0, []

    def fsm_update_loop(trial_instance):
        print("[FSM] Update thread started")
        while trial_instance.running and not trial_instance.completed:
            trial_instance.update()
            time.sleep(0.001)
        print("[FSM] Update thread ended")

    def handle_command(command):
        nonlocal frame_queue, sender, camera, is_streaming
        nonlocal current_trial, trial_thread

        if command == "START_STREAMING":
            if is_streaming:
                return False, "already streaming"
            if pc_ip is None:
                return False, "no PC IP known"
            frame_queue = queue.Queue(maxsize=2)
            sender = UDPSender(target_ip=pc_ip, target_port=stream_port, data_queue=frame_queue)
            sender.start()
            camera = CameraStreamer(data_queue=frame_queue, gpio_controller=mock_gpio, fsm_data_cb=get_live_fsm_data)
            camera.start()
            is_streaming = True
            print("Streaming started")
            return True, "ok"

        elif command == "STOP_STREAMING":
            if not is_streaming:
                return False, "not streaming"
            if camera: camera.stop()
            if sender:  sender.stop()
            is_streaming = False
            print("Streaming stopped")
            return True, "ok"

        elif command.startswith("START_TRIAL:"):
            if current_trial and current_trial.running:
                print("Stopping previous trial...")
                current_trial.stop()
                time.sleep(0.1)

            params = TrialParametersParser.parse(command)
            if not params:
                return False, "JSON parsing failed"

            is_valid, msg = TrialParametersParser.validate_parameters(params)
            if not is_valid:
                return False, f"invalid parameters: {msg}"

            current_trial = TrialStateMachine(mock_gpio, mock_audio, params)
            current_trial.start()
            trial_thread = threading.Thread(target=fsm_update_loop, args=(current_trial,), daemon=True)
            trial_thread.start()
            print("Trial started")
            return True, "ok"

        elif command == "STOP_TRIAL":
            if current_trial and current_trial.running:
                current_trial.stop()
                print("Trial stopped")
                return True, "ok"
            return False, "no trial running"

        return False, f"unknown command: {command}"

    def on_connect(ip):
        nonlocal pc_ip
        pc_ip = ip
        print(f"PC IP set to {pc_ip}")

    receiver = TCPCommandReceiver(port=tcp_port, command_handler=handle_command, on_connect=on_connect)

    try:
        receiver.start()
        print(f"Debug controller ready — TCP commands on port {tcp_port}, UDP stream on port {stream_port}")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
    finally:
        receiver.stop()
        if current_trial and current_trial.running:
            current_trial.stop()
        if is_streaming:
            if camera: camera.stop()
            if sender:  sender.stop()
        print("Shutdown complete")
        sys.exit(0)


if __name__ == "__main__":
    run_test_server()
