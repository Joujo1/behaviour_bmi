"""
PC-side acquisition entry point.

Starts one UDPreceiver + FrameWriter pair per cage and a shared Watchdog.
Runs until SIGINT or SIGTERM.
"""

import os
import signal
import sys
import time
from collections.abc import Callable

import config
from acquisition.frame_writer import FrameWriter
from acquisition.packet_parser import ParsedFrame, parse_packet
from acquisition.udp_receiver import UDPreceiver
from acquisition.watchdog import Watchdog
from shared.logger import get_logger

log = get_logger("acquisition", config.LOGGING_DIR, config.LOGGING_LEVEL)


def _make_stats() -> dict:
    return {
        cage_id: {"last_seen": 0.0, "frames_written": 0, "drop_count": 0, "network_drop_count": 0}
        for cage_id in range(1, config.N_CAGES + 1)
    }


def _make_drop_callback(cage_id: int, stats: dict) -> Callable[[], None]:
    def on_drop() -> None:
        stats[cage_id]["drop_count"] += 1
    return on_drop


def _make_frame_callback(writer: FrameWriter, cage_id: int, stats: dict) -> Callable[[bytes, str, int, float], None]:
    last_frame_num = 0

    def callback(data: bytes, ip: str, _port: int, arrival_time: float) -> None:
        nonlocal last_frame_num
        frame = parse_packet(data, ip, arrival_time)
        if frame is None:
            return

        # Detect gaps in the Pi's frame counter (network-level drops)
        if last_frame_num > 0 and frame.pi_seq > last_frame_num + 1:
            gap = frame.pi_seq - last_frame_num - 1
            # Large gap likely means Pi restarted — don't count as drops
            if gap < 10000:
                stats[cage_id]["network_drop_count"] += gap
                log.warning("Cage %d: %d frame(s) missing (expected %d, got %d)",
                            cage_id, gap, last_frame_num + 1, frame.pi_seq)
        last_frame_num = frame.pi_seq

        stats[cage_id]["last_seen"] = time.time()
        writer.write_frame(frame)

    return callback


def main() -> None:
    session_dir = os.path.join(config.NAS_BASE_PATH, sys.argv[1])

    camera_stats = _make_stats()
    writers   = []
    listeners = []

    for cage_id in range(1, config.N_CAGES + 1):
        writer = FrameWriter(cage_id, camera_stats)
        writer.start(session_dir)
        writers.append(writer)

        port = config.UDP_BASE_PORT + cage_id
        listener = UDPreceiver(port, _make_frame_callback(writer, cage_id, camera_stats),
                               on_drop=_make_drop_callback(cage_id, camera_stats))
        listener.start()
        listeners.append(listener)
        log.info("Cage %d listening on UDP port %d", cage_id, port)

    watchdog = Watchdog(camera_stats)
    watchdog.start()

    log.info("Acquisition running — %d cages, session: %s", config.N_CAGES, session_dir)

    def shutdown(sig: int, frame) -> None:
        log.info("Shutting down acquisition...")
        for listener in listeners:
            listener.stop()
        for writer in writers:
            writer.stop()
        watchdog.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
