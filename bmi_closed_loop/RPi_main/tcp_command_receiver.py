"""
TCP server that accepts a single persistent connection from the PC.

Protocol (newline-terminated UTF-8):
  PC → Pi   {trial JSON}\n          start a new trial
  PC → Pi   STOP_TRIAL\n            abort the running trial
  PC → Pi   START_STREAMING\n       start camera + UDP stream
  PC → Pi   STOP_STREAMING\n        stop camera + UDP stream

  Pi → PC   ACK:ok\n                command accepted
  Pi → PC   ERROR:reason\n          command rejected
  Pi → PC   {event JSON}\n          unsolicited push (e.g. trial_complete)
"""

import logging
import socket
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class TCPCommandReceiver:
    """TCP server running on the Pi. Accepts one persistent connection from the PC."""

    def __init__(self, port: int, command_handler: Callable[[str], tuple[bool, str]], on_connect: Callable[[str], None] | None = None):
        self._port            = port
        self._command_handler = command_handler
        self._on_connect      = on_connect
        self._server_socket   = None
        self._conn            = None
        self._conn_lock       = threading.Lock()
        self._running         = False
        self._thread          = None

    def start(self) -> None:
        """Bind the server socket and start the accept loop in a background thread."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind(("0.0.0.0", self._port))
        self._server_socket.listen(1)
        self._server_socket.settimeout(1.0)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="tcp-cmd-receiver")
        self._thread.start()
        logger.info("TCP receiver listening on port %d", self._port)

    def stop(self) -> None:
        """Stop the server and close all sockets."""
        self._running = False
        if self._server_socket:
            self._server_socket.close()
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
                logger.error("TCP push failed: %s", e)

    def _accept_loop(self) -> None:
        """Wait for a PC connection and handle it; loop back after disconnect."""
        while self._running:
            try:
                conn, addr = self._server_socket.accept()
                logger.info("PC connected from %s", addr[0])
                with self._conn_lock:
                    self._conn = conn
                if self._on_connect:
                    self._on_connect(addr[0])
                self._handle_connection(conn, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error("TCP accept error: %s", e)
            finally:
                with self._conn_lock:
                    self._conn = None

    def _handle_connection(self, conn: socket.socket, addr: tuple) -> None:
        """Read newline-terminated commands and dispatch each to the command handler."""
        buf = b""
        try:
            while self._running:
                chunk = conn.recv(4096)
                if not chunk:
                    logger.info("PC %s disconnected", addr[0])
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    command = line.decode("utf-8").strip()
                    if not command:
                        continue
                    logger.debug("Command received: %s", command[:80])
                    try:
                        ok, msg = self._command_handler(command)
                        response = f"ACK:{msg}\n" if ok else f"ERROR:{msg}\n"
                    except Exception as e:
                        response = f"ERROR:{e}\n"
                    conn.sendall(response.encode("utf-8"))
        except Exception as e:
            logger.error("TCP connection error: %s", e)
        finally:
            conn.close()
