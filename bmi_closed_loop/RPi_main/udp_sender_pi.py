"""
UDP sender that drains a frame queue and transmits each bundle to the PC.

Each UDP packet contains a fixed binary header followed by the events JSON
and the H264 frame bytes. Packet layout (little-endian):

  Offset  Size  Field
  ------  ----  -----
  0       4     frame_counter (uint32)
  4       8     timestamp_us  (uint64, CLOCK_MONOTONIC µs)
  12      4     jpeg_size     (uint32)
  16      4     events_size   (uint32)
  20      1     led_center    (uint8, 0/1)
  21      1     led_left      (uint8, 0/1)
  22      1     led_right     (uint8, 0/1)
  23      1     valve_left    (uint8, 0/1)
  24      1     valve_right   (uint8, 0/1)
  25      1     beam_left     (uint8, 0/1)
  26      1     beam_right    (uint8, 0/1)
  27      1     beam_center   (uint8, 0/1)
  28      1     trial_state   (uint8)
  29      N     events JSON   (UTF-8)
  29+N    M     H264 frame    (bytes)
"""

import json
import logging
import queue
import socket
import struct
import threading

logger = logging.getLogger(__name__)


class UDPSender:
    """Consumer thread that drains a frame queue and sends each bundle over UDP."""

    def __init__(self, target_ip: str, target_port: int, data_queue: queue.Queue):
        self._target_ip    = target_ip
        self._target_port  = target_port
        self._data_queue   = data_queue
        self._socket       = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._running      = False
        self._send_thread  = None
        self._frame_counter = 0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True, name="udp-sender")
        self._send_thread.start()
        logger.info("UDP sender started → %s:%d", self._target_ip, self._target_port)

    def stop(self) -> None:
        self._running = False
        if self._send_thread:
            self._send_thread.join(timeout=1.0)
        self._socket.close()
        logger.info("UDP sender stopped")

    def _send_loop(self) -> None:
        """Drain the frame queue and transmit each bundle until stopped."""
        while self._running:
            try:
                bundle = self._data_queue.get(timeout=1.0)
                self._pack_and_send(
                    bundle['frame'], bundle['gpio'], bundle['timestamp'],
                    bundle.get('state', 0), bundle.get('events', []),
                )
                self._data_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error("UDP send error: %s", e)

    def _pack_and_send(self, frame_bytes: bytes, gpio: dict, timestamp: int, trial_state: int, events: list) -> None:
        """Pack a frame bundle into a binary UDP packet and transmit it."""
        self._frame_counter += 1
        events_json = json.dumps(events).encode('utf-8')

        header = struct.pack(
            '<IQIIBBBBBBBBB',
            self._frame_counter,
            timestamp,
            len(frame_bytes),
            len(events_json),
            1 if gpio.get('led_center',  False) else 0,
            1 if gpio.get('led_left',    False) else 0,
            1 if gpio.get('led_right',   False) else 0,
            1 if gpio.get('valve_left',  False) else 0,
            1 if gpio.get('valve_right', False) else 0,
            1 if gpio.get('beam_left',   False) else 0,
            1 if gpio.get('beam_right',  False) else 0,
            1 if gpio.get('beam_center', False) else 0,
            trial_state,
        )

        packet = header + events_json + frame_bytes

        if len(packet) > 65507:
            logger.warning("Dropped oversized frame: %d bytes", len(packet))
            return

        try:
            self._socket.sendto(packet, (self._target_ip, self._target_port))
        except OSError as e:
            logger.error("UDP sendto error: %s", e)
