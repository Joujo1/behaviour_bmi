import os
import signal
import sys
import time

import config
from acquisition.frame_writer import FrameWriter
from acquisition.packet_parser import parse_packet
from acquisition.udp_receiver import UDPreceiver
from acquisition.debug_monitor import DebugMonitor
from acquisition.watchdog import Watchdog
from shared.logger import get_logger

log = get_logger("acquisition", config.LOGGING_DIR, config.LOGGING_LEVEL)


def _make_stats() -> dict:
    return {
        cage_id: {"last_seen": 0.0, "frames_written": 0, "drop_count": 0, "network_drop_count": 0}
        for cage_id in range(1, config.N_CAGES + 1)
    }


def _make_callback(writer: FrameWriter, cage_id: int, stats: dict):
    last_frame_num = 0

    def callback(data: bytes, ip: str, _port: int, arrival_time: float):
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
                log.warning(f"Cage {cage_id}: {gap} frame(s) missing "
                            f"(expected {last_frame_num + 1}, got {frame.pi_seq})")
        last_frame_num = frame.pi_seq

        stats[cage_id]["last_seen"] = time.time()
        writer.write_frame(frame)
    return callback


def main():
    session_dir = os.path.join(config.NAS_BASE_PATH, sys.argv[1])

    camera_stats = _make_stats()

    writers = []
    listeners = []

    for cage_id in range(1, config.N_CAGES + 1):
        writer = FrameWriter(cage_id, camera_stats)
        writer.start(session_dir)
        writers.append(writer)

        port = config.UDP_BASE_PORT + cage_id
        listener = UDPreceiver(
            port,
            _make_callback(writer, cage_id, camera_stats),
            on_drop=lambda cid=cage_id: camera_stats[cid].__setitem__("drop_count", camera_stats[cid]["drop_count"] + 1),
        )
        listener.start()
        listeners.append(listener)
        log.info(f"Cage {cage_id} listening on UDP port {port}")

    watchdog = Watchdog(camera_stats)
    watchdog.start()

    debug_monitor = DebugMonitor(listeners, camera_stats)
    debug_monitor.start()

    log.info(f"Acquisition running — {config.N_CAGES} cages, session: {session_dir}")

    def shutdown(sig, frame):
        log.info("Shutting down acquisition...")
        for l in listeners:
            l.stop()
        for w in writers:
            w.stop()
        watchdog.stop()
        debug_monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
