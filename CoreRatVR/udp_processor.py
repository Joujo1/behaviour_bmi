import struct
import cv2
import numpy as np
import base64
import json
from datetime import datetime

class DataProcessor:
    """
    Handles parsing and reassembly of cage data packets.
    """

    def __init__(self, callback_func = None):
        """
        :param callback_func: Final function to call once data is fully parsed
        """
        self.final_callback = callback_func
        self.chunk_buffers = {}

    def parse_dispatch_packet(self, raw_data, sender_ip, sender_port, network_arrival_time):
        try:
            if len(raw_data) < 18:
                return
            
            if len(raw_data) >= 7 and raw_data.startswith(b"STREAM_"):
                self.parse_text_packet(raw_data, sender_ip, sender_port, network_arrival_time)
                return

            if len(raw_data) >= 10 and raw_data.startswith(b"TRIAL_DATA"):
                self.parse_text_packet(raw_data, sender_ip, sender_port, network_arrival_time)
                return
            
            #Redundant method, not used anymore
            if len(raw_data) >= 10 and raw_data.startswith(b"CHNK"):
                total_chunks = struct.unpack('>H', raw_data[8:10])[0]
                
                if 0 < total_chunks < 1000:
                    #self.handle_chunked_packet(raw_data, sender_ip, sender_port)
                    return

            self.parse_binary_packet(raw_data, sender_ip, sender_port, network_arrival_time)
        
        except Exception as e:
            print(f"Error parsing UDP packet: {e}")
            if len(raw_data) >= 4:
                hex_head = raw_data[:4].hex(' ').upper()
                print(f"  First 4 bytes: {hex_head}")

        
    def parse_text_packet(self, raw_data, sender_ip, sender_port, network_arrival_time):
        """
        Parse text-based packet format
        Format: "STREAM_FRAME:WIDTH,HEIGHT,BASE64_JPEG"
        or "STREAM_GPIO:LED_C,LED_L,LED_R,SENS_L,SENS_R,SENS_C"
        """
        try:
            data_str = raw_data.decode('utf-8', errors='ignore')
            
            if ":" not in data_str:
                return
            
            data_type, payload = data_str.split(":", 1)
            data_type = data_type.strip()
            
            print(f"Received text packet: {data_type} (length={len(data_str)})")
            
            #Redundant method, not used anymore
            if data_type == 'STREAM_FRAME':
                parts = payload.split(',')
                if len(parts) >= 3:
                    width = int(parts[0])
                    height = int(parts[1])
                    base64_data = ",".join(parts[2:])
                    
                    jpeg_bytes = base64.b64decode(base64_data)
                    decoded_frame = self._decode_jpeg(jpeg_bytes)
                    
                    if decoded_frame is not None:
                        frame_data = {
                            'frame': decoded_frame,
                            'frame_number': 0,
                            'timestamp': datetime.now().isoformat(),
                            'gpio_state': {},
                            'type': 'STREAM_FRAME'
                        }
                        
                        if self.final_callback:
                            self.final_callback(frame_data, {"ip": "192.168.1.102", "port": 5005})
                        
                        print(f"Successfully decoded text-based frame: {width}x{height}")

            elif data_type == 'STREAM_GPIO':
                parts = payload.split(',')
                
                if len(parts) >= 6:
                    gpio_state = {
                        'led_center': float(parts[0]),
                        'led_left': float(parts[1]),
                        'led_right': float(parts[2]),
                        'sensor_left': float(parts[3]),
                        'sensor_right': float(parts[4]),
                        'sensor_center': float(parts[5])
                    }
                
                frame_data = {
                        'frame': None,
                        'gpio_state': gpio_state, # type: ignore
                        'type': 'STREAM_GPIO',
                        'network_arrival_time': network_arrival_time
                    }
                    
                if self.final_callback:
                    self.final_callback(frame_data, {"ip": sender_ip, "port": sender_port})

            elif data_type == 'TRIAL_DATA':
                try:
                    trial_data = json.loads(payload)
                    trial_data['network_arrival_time'] = network_arrival_time
                    if self.final_callback:
                        self.final_callback(trial_data, {"ip": sender_ip, "port": 5005, "dataType": "TRIAL_DATA"})
                    
                    event_count = len(trial_data.get('events', []))
                    print(f"Received trial {trial_data.get('trial_number')} data with {event_count} events")
                    
                except json.JSONDecodeError as e:
                    print(f"Failed to parse trial data JSON: {e}")

            else:
                print(f"Unknown text packet type: {data_type}")

        except Exception as e:
            print(f"Error parsing text packet: {e}")             


    def _decode_jpeg(self, jpeg_bytes):
        """
        Helper to decode JPEG bytes into an OpenCV image
        """
        nparr = np.frombuffer(jpeg_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img


    def parse_binary_packet(self, raw_data, sender_ip, sender_port, network_arrival_time):
        """
        NEW FORMAT: struct.pack('<IQIIBBBBBBB', frame_num, timestamp, jpeg_size, events_size,
        led_center, valve_left, valve_right, sensor_left, sensor_right, sensor_center, trial_state) 
        + JSON_EVENTS + JPEG
        Header: 27 bytes (4+8+4+4+7)
        """
        try:
            if len(raw_data) < 27:
                print("Packet too small for binary format (< 27 bytes)")
                return

            header_format = '<IQIIBBBBBBB'
            header_size = struct.calcsize(header_format)
            
            header_data = raw_data[:header_size]
            
            (frame_num, timestamp, jpeg_size, events_size,
             led_center, valve_left, valve_right, 
             sensor_left, sensor_right, sensor_center, 
             trial_state) = struct.unpack(header_format, header_data)

            # if frame_num % 30 == 0:
            #     print(f"Binary packet: frame={frame_num}, jpeg_size={jpeg_size}, events_size={events_size}, "
            #           f"LED_C={led_center}, V_L={valve_left}, V_R={valve_right}, "
            #           f"S_L={sensor_left}, S_R={sensor_right}, S_C={sensor_center}, "
            #           f"trial_state={trial_state}")
            #     print(f"Total Packet Size: {len(raw_data)} bytes")

            if not jpeg_size or jpeg_size <= 0 or jpeg_size > 10_000_000:
                print(f"Invalid jpeg_size in binary packet: {jpeg_size}")
                return
                
            expected_total_size = header_size + events_size + jpeg_size
            if len(raw_data) < expected_total_size:
                print(f"Incomplete binary frame {frame_num}")
                return

            events_data = []
            if events_size > 0:
                try:
                    json_bytes = raw_data[header_size : header_size + events_size]
                    events_data = json.loads(json_bytes.decode('utf-8'))
                except Exception as e:
                    print(f"Failed to decode FSM events JSON on frame {frame_num}: {e}")

            jpg_data = raw_data[header_size + events_size : expected_total_size]
            decoded_frame = self._decode_jpeg(jpg_data)

            if decoded_frame is None:
                print(f"Failed to decode JPEG (frame {frame_num}, size {jpeg_size})")
                return

            frame_data = {
                'frame': decoded_frame,
                'frame_number': frame_num,
                'timestamp': timestamp,
                'gpio_state': {
                    'led_center': led_center,
                    'valve_left': valve_left,
                    'valve_right': valve_right,
                    'sensor_left': sensor_left,
                    'sensor_right': sensor_right,
                    'sensor_center': sensor_center
                },
                'trial_state': trial_state,
                'events': events_data,
                'type': 'BINARY_FRAME',
                'network_arrival_time': network_arrival_time
            }

            if self.final_callback:
                self.final_callback(frame_data, {"ip": sender_ip, "port": 5005})

        except Exception as e:
            print(f"Error parsing binary packet: {e}")


    def parse_binary_packet_old(self, raw_data, sender_ip, sender_port):
        """
        Parse binary packet format from data_streaming_test.py
        NEW FORMAT: struct.pack('<IQIBBBBBBB', frame_num, timestamp, jpeg_size, 
        led_center, valve_left, valve_right, sensor_left, sensor_right, sensor_center, trial_state) + JPEG
        Header: 23 bytes (4+8+4+7)
        """
        try:
            if len(raw_data) < 23:
                print("Packet too small for binary format (< 23 bytes)")
                return

            header_format = '<IQIBBBBBBB'
            header_size = struct.calcsize(header_format)
            
            header_data = raw_data[:header_size]
            
            (frame_num, timestamp, jpeg_size, 
             led_center, valve_left, valve_right, 
             sensor_left, sensor_right, sensor_center, 
             trial_state) = struct.unpack(header_format, header_data)

            if frame_num % 30 == 0:
                print(f"Binary packet: frame={frame_num}, jpeg_size={jpeg_size}, "
                      f"LED_C={led_center}, V_L={valve_left}, V_R={valve_right}, "
                      f"S_L={sensor_left}, S_R={sensor_right}, S_C={sensor_center}, "
                      f"trial_state={trial_state}")
                print(f"Total Packet Size: {len(raw_data)} bytes")

            if not jpeg_size or jpeg_size <= 0 or jpeg_size > 10_000_000:
                print(f"Invalid jpeg_size in binary packet: {jpeg_size}")
                return

            if len(raw_data) < header_size + jpeg_size:
                print(f"Incomplete binary frame {frame_num}")
                return

            jpg_data = raw_data[header_size : header_size + jpeg_size]
            decoded_frame = self._decode_jpeg(jpg_data)

            if decoded_frame is None:
                print(f"Failed to decode JPEG (frame {frame_num}, size {jpeg_size})")
                return

            frame_data = {
                'frame': decoded_frame,
                'frame_number': frame_num,
                'timestamp': timestamp,
                'gpio_state': {
                    'led_center': led_center,
                    'valve_left': valve_left,
                    'valve_right': valve_right,
                    'sensor_left': sensor_left,
                    'sensor_right': sensor_right,
                    'sensor_center': sensor_center
                },
                'trial_state': trial_state,
                'type': 'BINARY_FRAME'
            }

            if self.final_callback:
                self.final_callback(frame_data, {"ip": sender_ip, "port": 5005})

        except Exception as e:
            print(f"Error parsing binary packet: {e}")


    """
            #Redundant method, not used anymore
    def handle_chunked_packet(self, raw_data, sender_ip, sender_port):
        try:
            if len(raw_data) < 10:
                print("Chunked packet too small")
                return

            header_bytes = raw_data[4:10]
            message_id, chunk_idx, total_chunks = struct.unpack('>HHH', header_bytes)
            
            chunk_data = raw_data[10:]

            if message_id not in self.chunk_buffers:
                self.chunk_buffers[message_id] = {
                    'total_chunks': total_chunks,
                    'chunks': [None] * total_chunks,
                    'count': 0
                }

            buffer = self.chunk_buffers[message_id]

            if buffer['chunks'][chunk_idx] is None:
                buffer['chunks'][chunk_idx] = chunk_data
                buffer['count'] += 1

            if buffer['count'] == total_chunks:
                print(f"All chunks received for message_id={message_id}, reassembling {total_chunks} chunks")
                
                full_data = b"".join(buffer['chunks'])
                
                del self.chunk_buffers[message_id]
                
                print(f"Reassembled message: {len(full_data)} bytes")
                
                self.parse_dispatch_packet(full_data, sender_ip, sender_port)

        except Exception as e:
            print(f"Error handling chunked packet: {e}")
    """