import socket
import threading


class TCPCommandReceiver:
    """
    TCP server running on the Pi. Accepts one persistent connection from the PC.

    The PC sends newline-terminated messages:
        {trial JSON}\n          — start a new trial
        STOP_TRIAL\n            — abort the running trial

    The Pi replies to each command with either:
        ACK:ok\n
        ERROR:reason\n

    The Pi can also push unsolicited events at any time via push():
        {"event": "trial_complete", "trial_id": "..."}\n

    command_handler must be callable(command: str) -> (ok: bool, message: str)
    """

    def __init__(self, port: int, command_handler, on_connect=None):
        self._port = port
        self._handler = command_handler
        self._on_connect = on_connect
        self._server_sock = None
        self._conn = None
        self._conn_lock = threading.Lock()
        self._running = False
        self._thread = None

    def start(self):
        """Bind the server socket and start the accept loop in a background thread."""
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(("0.0.0.0", self._port))
        self._server_sock.listen(1)
        self._server_sock.settimeout(1.0)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="tcp-cmd-receiver")
        self._thread.start()
        print(f"TCP receiver listening on port {self._port}")

    def stop(self):
        """Stop the server and close all sockets."""
        self._running = False
        if self._server_sock:
            self._server_sock.close()
        if self._thread:
            self._thread.join(timeout=2.0)

    def push(self, message: str) -> None:
        """Send an unsolicited message to the connected PC (e.g. trial_complete event)."""
        with self._conn_lock:
            if self._conn is None:
                return
            try:
                self._conn.sendall((message + "\n").encode("utf-8"))
            except Exception as e:
                print(f"TCP push failed: {e}")

    def _accept_loop(self):
        """Wait for a PC connection and handle it; loop back after disconnect."""
        while self._running:
            try:
                conn, addr = self._server_sock.accept()
                print(f"PC connected from {addr[0]}")
                with self._conn_lock:
                    self._conn = conn
                if self._on_connect:
                    self._on_connect(addr[0])
                self._handle_connection(conn, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print(f"TCP accept error: {e}")
            finally:
                with self._conn_lock:
                    self._conn = None

    def _handle_connection(self, conn, addr):
        """Read newline-terminated commands and dispatch each to the command handler."""
        buf = b""
        try:
            while self._running:
                chunk = conn.recv(4096)
                if not chunk:
                    print(f"PC {addr[0]} disconnected")
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    command = line.decode("utf-8").strip()
                    if not command:
                        continue
                    print(f"Command received: {command[:80]}")
                    try:
                        ok, msg = self._handler(command)
                        response = f"ACK:{msg}\n" if ok else f"ERROR:{msg}\n"
                    except Exception as e:
                        response = f"ERROR:{e}\n"
                    conn.sendall(response.encode("utf-8"))
        except Exception as e:
            print(f"TCP connection error: {e}")
        finally:
            conn.close()
