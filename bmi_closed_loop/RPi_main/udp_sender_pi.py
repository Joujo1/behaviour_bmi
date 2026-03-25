import socket
import struct
import threading
import queue
import json

class UDPSender:
    """
    Consumer Thread that pulls frames from Queue and sends them over UDP
    """
    def __init__(self, target_ip, target_port, data_queue):
        self.target_ip = target_ip
        self.target_port = target_port
        self.data_queue = data_queue
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = False
        self.thread = None
        
        self.message_id = 0 
        self.frame_counter = 0

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._send_loop, daemon=True)
        self.thread.start()
        print("UDP Sender started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        self.sock.close()
        print("UDP Sender stopped")

    def _send_loop(self):
        """
        Continuous background loop to send UDP packages
        """
        while self.running:
            try:
                bundle = self.data_queue.get(timeout = 1.0)
                frame_bytes = bundle['frame']
                gpio = bundle['gpio']
                timestamp = bundle['timestamp']
                trial_state = bundle.get('state', 0)
                events = bundle.get('events', [])
                self._pack_and_send(frame_bytes, gpio, timestamp, trial_state, events)
                self.data_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"UDP Sender Error: {e}")

    
    def _pack_and_send(self, frame_bytes, gpio, timestamp, trial_state, events):
        self.frame_counter += 1
        jpeg_size = len(frame_bytes)

        events_json_bytes = json.dumps(events).encode('utf-8')
        events_size = len(events_json_bytes)
        
        header = struct.pack(
            '<IQIIBBBBBBB', # Format: < I(frame) Q(time) I(jpeg_size) I(events_size) Bx7(gpio+state)
            self.frame_counter,
            timestamp,
            jpeg_size,
            events_size,
            1 if gpio.get('led_center', False) else 0,
            1 if gpio.get('valve_left', False) else 0,
            1 if gpio.get('valve_right', False) else 0,
            1 if gpio.get('sensor_left', False) else 0,
            1 if gpio.get('sensor_right', False) else 0,
            1 if gpio.get('sensor_center', False) else 0,
            trial_state
        )
        
        full_data = header + events_json_bytes + frame_bytes
        
        if len(full_data) > 65507:
            print(f"Dropped frame: {len(full_data)} bytes")
            return

        try:
            self.sock.sendto(full_data, (self.target_ip, self.target_port))
        except OSError as e:
            print(f"OS edging {e}")