import json
import logging
import queue
import socket
import threading

_log = logging.getLogger("tcp_cmd")


class TCPCommandSender:
    """
    PC-side TCP client for one cage.

    Maintains a persistent connection to the Pi. A background reader thread
    continuously reads from the socket and classifies each line:
      - ACK:/ERROR: lines are responses to commands → placed on _response_queue
      - everything else is an unsolicited Pi event (e.g. trial_complete) →
        dispatched to on_event(cage_id, event_dict)
    """

    def __init__(self, cage_id: int, host: str, port: int, on_event=None):
        self._cage_id = cage_id
        self._host = host
        self._port = port
        self._on_event = on_event  # callable(cage_id: int, event: dict)

        self._sock = None
        self._lock = threading.Lock()
        self._response_queue: queue.Queue = queue.Queue()
        self._reader_thread: threading.Thread = None
        self._running = False

    def send(self, command: str):
        """Send command, block until ACK/ERROR, return (ok: bool, message: str)."""
        with self._lock:
            if self._sock is None:
                connected, err = self._connect()
                if not connected:
                    return False, err
            try:
                self._sock.sendall((command + "\n").encode("utf-8"))
                response = self._response_queue.get(timeout=5.0)
                if response.startswith("ACK:"):
                    _log.info(f"Cage {self._cage_id}: ACK [{command[:40]}]")
                    return True, response[4:]
                if response.startswith("ERROR:"):
                    _log.warning(f"Cage {self._cage_id}: ERROR [{command[:40]}] → {response[6:]}")
                    return False, response[6:]
                _log.warning(f"Cage {self._cage_id}: unexpected response: {response}")
                return False, f"unexpected response: {response}"
            except queue.Empty:
                _log.error(f"Cage {self._cage_id}: timeout waiting for response to [{command[:40]}]")
                return False, "timeout waiting for response"
            except Exception as e:
                _log.error(f"Cage {self._cage_id}: send failed [{command[:40]}] → {e}")
                self._sock = None
                return False, f"send failed: {e}"

    def disconnect(self):
        self._running = False
        with self._lock:
            if self._sock:
                self._sock.close()
                self._sock = None

    def _connect(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect((self._host, self._port))
            sock.settimeout(None)
            self._sock = sock
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
            self._sock = None
            return False, f"cannot connect to cage {self._cage_id} ({self._host}:{self._port}): {e}"

    def _read_loop(self):
        """Background thread: read lines from socket and classify them."""
        buf = b""
        while self._running and self._sock:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    _log.warning(f"Cage {self._cage_id}: Pi disconnected")
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._dispatch(line.decode("utf-8").strip())
            except Exception as e:
                if self._running:
                    _log.error(f"Cage {self._cage_id}: reader error: {e}")
                break
        self._running = False
        self._sock = None

    def _dispatch(self, line: str):
        """Route a received line to the response queue or the event callback."""
        if not line:
            return
        if line.startswith("ACK:") or line.startswith("ERROR:"):
            self._response_queue.put(line)
        elif self._on_event:
            try:
                self._on_event(self._cage_id, json.loads(line))
            except Exception as e:
                _log.warning(f"Cage {self._cage_id}: failed to parse event {line!r}: {e}")
