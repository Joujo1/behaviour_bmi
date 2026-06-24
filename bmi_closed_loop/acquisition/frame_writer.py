"""
Per-cage frame writer. Called synchronously from UDPreceiver's worker thread.

Three writes per frame (in order):
  1. NAS      — 4-byte length prefix + full raw UDP packet (header + events + frame)
  2. Valkey   — SET cage:{id}:latest_frame = jpeg_bytes (TTL self-cleaning)
               OR PUBLISH cage:{id}:h264_stream = meta + h264_bytes
  3. Postgres — batched INSERT every DB_CHUNK_SIZE frames (one recordings row per chunk)
"""

import os
import struct
import time

import config
from acquisition.packet_parser import HEADER_SIZE, ParsedFrame
from shared.logger import get_logger


class FrameWriter:
    """Per-cage writer. Called synchronously from UDPreceiver's worker thread."""

    def __init__(self, cage_id: int, camera_stats: dict):
        self._cage_id = cage_id
        self._stats   = camera_stats
        self._log     = get_logger(f"writer.cage{cage_id}", config.LOGGING_DIR, config.LOGGING_LEVEL)

        self._file      = None
        self._valkey    = None
        self._db_conn   = None
        self._db_cursor = None

        self._chunk_frame_count  = 0
        self._chunk_start_frame  = None
        self._chunk_start_ts     = None
        self._chunk_byte_offset  = 0
        self._current_byte_offset = 0

        self._recording            = False
        self._recording_checked_at = 0.0

    def start(self, session_dir: str) -> None:
        import valkey as valkey_client
        import psycopg2

        os.makedirs(session_dir, exist_ok=True)
        filepath = os.path.join(session_dir, f"cage_{self._cage_id}.bin")
        self._file = open(filepath, "ab")
        self._current_byte_offset = self._file.tell()

        self._valkey    = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)
        self._db_conn   = psycopg2.connect(config.POSTGRES_DSN)
        self._db_cursor = self._db_conn.cursor()

        self._log.info("Writer started → %s", filepath)

    def stop(self) -> None:
        self._flush_chunk()
        if self._db_conn:
            self._db_conn.commit()
            self._db_conn.close()
        if self._file:
            self._file.close()
        self._log.info("Writer stopped (cage %d)", self._cage_id)

    def write_frame(self, frame: ParsedFrame) -> None:
        self._write_valkey(frame)

        now = time.time()
        if now - self._recording_checked_at >= config.RECORDING_CHECK_INTERVAL_S:
            was = self._recording
            self._recording = self._valkey.get(f"cage:{self._cage_id}:recording") == b"1"
            self._recording_checked_at = now
            if was and not self._recording:
                self._flush_chunk()

        if self._recording:
            self._write_nas(frame)
            self._write_postgres(frame)

        self._stats[self._cage_id]["frames_written"] += 1

    def _write_nas(self, frame: ParsedFrame) -> None:
        # Store full raw packet so nothing is lost if Postgres is unavailable
        packet = frame.raw_packet
        self._file.write(struct.pack("<I", len(packet)))
        self._file.write(packet)
        self._current_byte_offset += 4 + len(packet)

    def _write_valkey(self, frame: ParsedFrame) -> None:
        img_bytes = frame.raw_packet[HEADER_SIZE + frame.events_size:]
        if img_bytes[:2] == b'\xff\xd8':
            # MJPEG: store for legacy polling endpoint
            self._valkey.set(f"cage:{self._cage_id}:latest_frame", img_bytes, ex=config.VALKEY_FRAME_TTL_SECONDS)
        elif img_bytes[:4] == b'\x00\x00\x00\x01':
            # H264 Annex-B: publish for WebSocket streaming.
            # SPS NAL (type 7) is the first NAL in every keyframe group.
            is_key = len(img_bytes) > 4 and (img_bytes[4] & 0x1F) == 7
            meta = bytes([1 if is_key else 0]) + frame.timestamp.to_bytes(8, 'little')
            self._valkey.publish(f"cage:{self._cage_id}:h264_stream", meta + img_bytes)

    def _write_postgres(self, frame: ParsedFrame) -> None:
        if self._chunk_frame_count == 0:
            self._chunk_start_frame  = frame.pi_seq
            self._chunk_start_ts     = frame.timestamp
            self._chunk_byte_offset  = self._current_byte_offset

        self._chunk_frame_count += 1

        if self._chunk_frame_count >= config.DB_CHUNK_SIZE:
            self._flush_chunk(end_frame=frame.pi_seq, end_ts=frame.timestamp)

    def _flush_chunk(self, end_frame: int | None = None, end_ts: int | None = None) -> None:
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
                (self._cage_id, self._chunk_start_frame, end_frame,
                 self._chunk_start_ts, end_ts,
                 self._chunk_byte_offset, self._chunk_frame_count),
            )
            self._db_conn.commit()
        except Exception as e:
            self._log.error("Postgres flush failed: %s", e)
        finally:
            self._chunk_frame_count = 0
            self._chunk_start_frame = None
            self._chunk_start_ts    = None
