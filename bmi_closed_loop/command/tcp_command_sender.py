import socket
import threading


class TCPCommandSender:
    """
    PC-side TCP client for one cage.

    Maintains a persistent connection to the Pi. If the Pi is offline or the
    connection drops, the next send() attempt will reconnect automatically.

    All public methods are thread-safe (Flask serves requests on multiple threads).

    Usage:
        sender = TCPCommandSender(cage_id=0, host="192.168.1.101", port=6000)
        ok, msg = sender.send("START_STREAMING")
        ok, msg = sender.send("START_TRIAL:{...}")
    """

    def __init__(self, cage_id: int, host: str, port: int):
        self._cage_id = cage_id
        self._host = host
        self._port = port
        self._sock = None
        self._lock = threading.Lock()

    def send(self, command: str):
        """Send command, return (ok: bool, message: str)."""
        with self._lock:
            if self._sock is None:
                connected, err = self._connect()
                if not connected:
                    return False, err
            try:
                self._sock.sendall((command + "\n").encode("utf-8"))
                response = self._recv_line()
                if response.startswith("ACK:"):
                    return True, response[4:]
                if response.startswith("ERROR:"):
                    return False, response[6:]
                return False, f"unexpected response: {response}"
            except Exception as e:
                self._sock = None
                return False, f"send failed: {e}"

    def disconnect(self):
        with self._lock:
            if self._sock:
                self._sock.close()
                self._sock = None

    # ------------------------------------------------------------------ #

    def _connect(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect((self._host, self._port))
            sock.settimeout(5.0)  # response timeout for individual commands
            self._sock = sock
            return True, ""
        except Exception as e:
            self._sock = None
            return False, f"cannot connect to cage {self._cage_id} ({self._host}:{self._port}): {e}"

    def _recv_line(self):
        buf = b""
        while b"\n" not in buf:
            chunk = self._sock.recv(256)
            if not chunk:
                raise ConnectionError(f"cage {self._cage_id} disconnected mid-response")
            buf += chunk
        return buf.split(b"\n")[0].decode("utf-8").strip()
