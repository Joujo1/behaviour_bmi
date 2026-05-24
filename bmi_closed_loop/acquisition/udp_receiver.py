"""
UDP receiver with a two-thread pipeline: a listener that enqueues raw datagrams
and a worker that drains the queue and dispatches to the frame callback.

The separate threads decouple network I/O from processing so that a slow write
to disk or Valkey cannot cause packet loss at the socket buffer level.
"""

import logging
import queue
import socket
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class UDPreceiver:
    """Dual-threaded UDP receiver: listener enqueues packets, worker dispatches them."""

    def __init__(self, local_port: int, data_callback: Callable[[bytes, str, int, float], None], on_drop: Callable[[], None] | None = None):
        self._port          = local_port
        self._callback      = data_callback
        self._on_drop       = on_drop
        self._running       = False
        self._socket        = None
        self._packet_queue  = queue.Queue(maxsize=60)
        self._listen_thread = None
        self._worker_thread = None

    def start(self) -> None:
        if self._running:
            return
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8388608)  # 8 MB kernel buffer
            self._socket.settimeout(1.0)
            self._socket.bind(("0.0.0.0", self._port))
            self._running = True
            self._listen_thread = threading.Thread(target=self._receive_loop, daemon=True, name=f"udp-listen-{self._port}")
            self._worker_thread = threading.Thread(target=self._process_loop, daemon=True, name=f"udp-work-{self._port}")
            self._listen_thread.start()
            self._worker_thread.start()
            logger.info("UDP receiver started on port %d", self._port)
        except Exception as e:
            self._running = False
            logger.error("Failed to start UDP receiver on port %d: %s", self._port, e)

    def stop(self) -> None:
        self._running = False
        if self._listen_thread:
            self._listen_thread.join(timeout=1.0)
        if self._worker_thread:
            self._worker_thread.join(timeout=1.0)
        if self._socket:
            self._socket.close()
            self._socket = None
        logger.info("UDP receiver stopped on port %d", self._port)

    def is_active(self) -> bool:
        return self._running

    def queue_size(self) -> int:
        return self._packet_queue.qsize()

    def _receive_loop(self) -> None:
        while self._running:
            if self._socket is None:
                break
            try:
                data, (ip, port) = self._socket.recvfrom(65535)
                arrival_time = time.time()
                if data:
                    try:
                        self._packet_queue.put_nowait((data, ip, port, arrival_time))
                    except queue.Full:
                        logger.warning("UDP queue full on port %d — frame dropped", self._port)
                        if self._on_drop:
                            self._on_drop()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error("UDP receive error on port %d: %s", self._port, e)
                break

    def _process_loop(self) -> None:
        while self._running:
            try:
                data, ip, port, arrival_time = self._packet_queue.get(timeout=0.5)
                self._callback(data, ip, port, arrival_time)
                self._packet_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error("UDP processing error on port %d: %s", self._port, e)
