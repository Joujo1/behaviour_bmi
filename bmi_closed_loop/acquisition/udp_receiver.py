import socket
import threading
import logging
import queue
import time

class UDPreceiver:
    """
    Handles UDP communication for receiving data from cages
    """

    def __init__(self, local_port, data_callback, on_drop=None):
        self.local_port = local_port
        self.callback = data_callback
        self._on_drop = on_drop
        self.is_running = False
        self.sock = None

        self.packet_queue = queue.Queue(maxsize=60)
        
        self.listen_thread = None
        self.worker_thread = None

    
    def start(self):
        """
        Start listening for UDP Data
        """
        if self.is_running:
            return
        
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8388608)
            self.sock.settimeout(1.0)
            self.sock.bind(("0.0.0.0", self.local_port))
            self.is_running = True
            
            self.listen_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.worker_thread = threading.Thread(target=self._process_loop, daemon=True)
            
            self.listen_thread.start()
            self.worker_thread.start()

            print(f"UDP Receiver started on port {self.local_port}")

        except Exception as e:
            self.is_running = False
            print(f"Failed to start UDP Receiver: {e}")

    
    def _receive_loop(self):
        while self.is_running:
            if self.sock is None:
                break
            try:
                data, (ip, port) = self.sock.recvfrom(65535)
                network_arrival_time = time.time()
                if data:
                    try:
                        self.packet_queue.put_nowait((data, ip, port, network_arrival_time))
                    except queue.Full:
                        print(f"Warning: UDP queue full on port {self.local_port} — frame dropped")
                        if self._on_drop:
                            self._on_drop()
                    
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    print(f"UDP Listen Error: {e}")
                break

    def _process_loop(self):
        while self.is_running:
            try:
                data, ip, port, network_arrival_time = self.packet_queue.get(timeout=0.5)
                self.callback(data, ip, port, network_arrival_time)
                self.packet_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"UDP Processing Error: {e}")

    def stop(self):
        self.is_running = False
        if self.listen_thread:
            self.listen_thread.join(timeout=1.0)
        if self.worker_thread:
            self.worker_thread.join(timeout=1.0)
            
        if self.sock:
            self.sock.close()
            self.sock = None
        print("UDP Receiver stopped")

    
    def is_active(self):
        return self.is_running

    def queue_size(self):
        return self.packet_queue.qsize()

    
    def __del__(self):
        self.stop()
            