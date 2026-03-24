import os
import queue
import struct
import threading
from typing import Optional

import config
from acquisition.packet_parser import HEADER_SIZE, ParsedFrame
from shared.logger import get_logger


class FrameWriter:
    """
    Writer thread for one cage.

    Three writes per frame (in order):
      1. NAS  — 4-byte length prefix + full raw UDP packet (header + events + jpeg)
      2. Valkey — SET cage:{id}:latest_frame = jpeg_bytes (TTL self-cleaning)
      3. Postgres — batched INSERT every DB_CHUNK_SIZE frames (one recordings row per chunk)
    """

    def __init__(self, cage_id: int, camera_stats: dict):
        self.cage_id = cage_id
        self._stats = camera_stats  # shared dict, written by listener/writer, read by watchdog
        self._write_queue: queue.Queue = queue.Queue(maxsize=config.FRAME_QUEUE_MAXSIZE)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._log = get_logger(f"writer.cage{cage_id}", config.LOGGING_DIR, config.LOGGING_LEVEL)

        self._file = None
        self._valkey = None
        self._db_conn = None
        self._db_cursor = None

        self._chunk_frame_count = 0
        self._chunk_start_frame: Optional[int] = None
        self._chunk_start_ts: Optional[int] = None
        self._chunk_byte_offset: int = 0
        self._current_byte_offset: int = 0

    def start(self, session_dir: str):
        import valkey as valkey_client
        import psycopg2

        os.makedirs(session_dir, exist_ok=True)
        filepath = os.path.join(session_dir, f"cage_{self.cage_id}.bin")
        self._file = open(filepath, "ab")
        self._current_byte_offset = self._file.tell()

        self._valkey = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)
        self._db_conn = psycopg2.connect(config.POSTGRES_DSN)
        self._db_cursor = self._db_conn.cursor()

        self._running = True
        self._thread = threading.Thread(
            target=self._write_loop,
            daemon=True,
            name=f"writer-cage-{self.cage_id}",
        )
        self._thread.start()
        self._log.info(f"Writer started → {filepath}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        self._flush_chunk()
        if self._db_conn:
            self._db_conn.commit()
            self._db_conn.close()
        if self._file:
            self._file.close()
        self._log.info(f"Writer stopped (cage {self.cage_id})")

    def push(self, frame: ParsedFrame):
        try:
            self._write_queue.put_nowait(frame)
        except queue.Full:
            self._stats[self.cage_id]["drop_count"] += 1
            self._log.warning("Write queue full — frame dropped")

    # ------------------------------------------------------------------ #

    def _write_loop(self):
        while self._running:
            try:
                frame = self._write_queue.get(timeout=0.5)
                self._write_nas(frame)
                self._write_valkey(frame)
                self._write_postgres(frame)
                self._write_queue.task_done()
                self._stats[self.cage_id]["frame_count"] += 1
            except queue.Empty:
                continue

    def _write_nas(self, frame: ParsedFrame):
        # Store full raw packet so nothing is lost if Postgres is unavailable
        packet = frame.raw_packet
        self._file.write(struct.pack("<I", len(packet)))
        self._file.write(packet)
        self._current_byte_offset += 4 + len(packet)

    def _write_valkey(self, frame: ParsedFrame):
        key = f"cage:{self.cage_id}:latest_frame"
        jpeg = frame.raw_packet[HEADER_SIZE + frame.events_size:]
        self._valkey.set(key, jpeg, ex=config.VALKEY_FRAME_TTL_SECONDS)

    def _write_postgres(self, frame: ParsedFrame):
        if self._chunk_frame_count == 0:
            self._chunk_start_frame = frame.frame_num
            self._chunk_start_ts = frame.timestamp
            self._chunk_byte_offset = self._current_byte_offset

        self._chunk_frame_count += 1

        if self._chunk_frame_count >= config.DB_CHUNK_SIZE:
            self._flush_chunk(end_frame=frame.frame_num, end_ts=frame.timestamp)

    def _flush_chunk(self, end_frame: int = None, end_ts: int = None):
        if self._chunk_frame_count == 0 or self._chunk_start_frame is None:
            return
        try:
            self._db_cursor.execute(
                """
                INSERT INTO recordings
                    (cage_id, chunk_start_frame, chunk_end_frame,
                     chunk_start_ts, chunk_end_ts,
                     chunk_byte_offset, chunk_frame_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    self.cage_id,
                    self._chunk_start_frame,
                    end_frame,
                    self._chunk_start_ts,
                    end_ts,
                    self._chunk_byte_offset,
                    self._chunk_frame_count,
                ),
            )
            self._db_conn.commit()
        except Exception as e:
            self._log.error(f"Postgres flush failed: {e}")
        finally:
            self._chunk_frame_count = 0
            self._chunk_start_frame = None
            self._chunk_start_ts = None
