import socket
import queue
import time
import sys
import traceback
from streamer import CameraStreamer
from udp_sender_pi import UDPSender

class MockGPIO:
    def get_current_state(self):
        return {
            'led_center': False, 'valve_left': False, 'valve_right': False,
            'sensor_left': False, 'sensor_right': False, 'sensor_center': True
        }



def run_test_server(listen_port=5006, stream_port=5005):
    control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    control_socket.bind(('0.0.0.0', listen_port))
    print(f"Controller listening for commands on port {listen_port}...")

    frame_queue = None
    sender = None
    camera = None
    is_streaming = False
    mock_gpio = MockGPIO()

    try:
        while True:
            data, addr = control_socket.recvfrom(1024)
            pc_ip = addr[0]
            command = data.decode('utf-8').strip()
            print(f"Received command: '{command}' from {pc_ip}")

            if command == "START_STREAMING" and not is_streaming:
                frame_queue = queue.Queue(maxsize=2)
                sender = UDPSender(target_ip=pc_ip, target_port=stream_port, data_queue=frame_queue)
                sender.start()
                camera = CameraStreamer(data_queue=frame_queue, gpio_controller=mock_gpio)
                camera.start()
                
                is_streaming = True
                print("Streaming started")

            elif command == "STOP_STREAMING" and is_streaming:
                print("Stopping streaming...")
                if camera: 
                    camera.stop()
                if sender: 
                    sender.stop()
                is_streaming = False

    except Exception as e:
        traceback.print_exc() 
    finally:
        if is_streaming:
            if camera: camera.stop()
            if sender: sender.stop()
        control_socket.close()
        sys.exit(0)
    

if __name__ == "__main__":
    run_test_server()