"""
PC-side TCP client for a single cage Pi.

Maintains a persistent connection to the Pi. A background reader thread
continuously reads from the socket and classifies each line:
  - ACK:/ERROR: lines are responses to commands → placed on _response_queue
  - everything else is an unsolicited Pi event (e.g. trial_complete) →
    dispatched to on_event(cage_id, event_dict)
"""

import json
import logging
import queue
import socket
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class TCPCommandSender:
    """PC-side TCP client for one cage."""

    def __init__(self, cage_id: int, host: str, port: int, on_event: Callable[[int, dict], None] | None = None):
        self._cage_id       = cage_id
        self._host          = host
        self._port          = port
        self._on_event      = on_event

        self._socket         = None
        self._lock           = threading.Lock()
        self._response_queue = queue.Queue()
        self._reader_thread  = None
        self._running        = False

    def send(self, command: str) -> tuple[bool, str]:
        """Send a command, block until ACK/ERROR, return (ok, message)."""
        with self._lock:
            if self._socket is None:
                connected, err = self._connect()
                if not connected:
                    return False, err
            try:
                self._socket.sendall((command + "\n").encode("utf-8"))
                response = self._response_queue.get(timeout=5.0)
                if response.startswith("ACK:"):
                    logger.info("Cage %d: ACK [%s]", self._cage_id, command[:40])
                    return True, response[4:]
                if response.startswith("ERROR:"):
                    logger.warning("Cage %d: ERROR [%s] → %s", self._cage_id, command[:40], response[6:])
                    return False, response[6:]
                logger.warning("Cage %d: unexpected response: %s", self._cage_id, response)
                return False, f"unexpected response: {response}"
            except queue.Empty:
                logger.error("Cage %d: timeout waiting for response to [%s]", self._cage_id, command[:40])
                return False, "timeout waiting for response"
            except Exception as e:
                logger.error("Cage %d: send failed [%s] → %s", self._cage_id, command[:40], e)
                self._socket = None
                return False, f"send failed: {e}"

    def disconnect(self) -> None:
        self._running = False
        with self._lock:
            if self._socket:
                self._socket.close()
                self._socket = None

    def _connect(self) -> tuple[bool, str]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect((self._host, self._port))
            sock.settimeout(None)
            self._socket = sock
            self._running = True
            self._reader_thread = threading.Thread(
                target=self._read_loop, daemon=True,
                name=f"tcp-reader-cage{self._cage_id}",
            )
            self._reader_thread.start()
            # Drain any stale responses left over from a previous connection
            while not self._response_queue.empty():
                self._response_queue.get_nowait()
            return True, ""
        except Exception as e:
            self._socket = None
            return False, f"cannot connect to cage {self._cage_id} ({self._host}:{self._port}): {e}"

    def _read_loop(self) -> None:
        """Background thread: read lines from socket and classify them."""
        buf = b""
        while self._running and self._socket:
            try:
                chunk = self._socket.recv(4096)
                if not chunk:
                    logger.warning("Cage %d: Pi disconnected", self._cage_id)
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._dispatch(line.decode("utf-8").strip())
            except Exception as e:
                if self._running:
                    logger.error("Cage %d: reader error: %s", self._cage_id, e)
                break
        self._running = False
        self._socket = None

    def _dispatch(self, line: str) -> None:
        """Route a received line to the response queue or the event callback."""
        if not line:
            return
        if line.startswith("ACK:") or line.startswith("ERROR:"):
            self._response_queue.put(line)
        elif self._on_event:
            try:
                self._on_event(self._cage_id, json.loads(line))
            except Exception as e:
                logger.warning("Cage %d: failed to parse event %r: %s", self._cage_id, line, e)
