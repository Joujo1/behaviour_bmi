"""
PC-side acquisition entry point.

Starts one UDPreceiver + FrameWriter pair per cage and a shared Watchdog.
Runs until SIGINT or SIGTERM.
"""

import csv
import os
import signal
import sys
import threading
import time
from collections.abc import Callable

import config
from acquisition.frame_writer import FrameWriter
from acquisition.packet_parser import ParsedFrame, parse_packet
from acquisition.udp_receiver import UDPreceiver
from acquisition.watchdog import Watchdog
from shared.logger import get_logger

log = get_logger("acquisition", config.LOGGING_DIR, config.LOGGING_LEVEL)


_STATS_INTERVAL_S = 5   # how often to snapshot frame stats to CSV


def _make_stats() -> dict:
    return {
        cage_id: {"last_seen": 0.0, "frames_written": 0, "drop_count": 0, "network_drop_count": 0}
        for cage_id in range(1, config.N_CAGES + 1)
    }


def _start_stats_logger(camera_stats: dict, session_dir: str,
                         stop_event: threading.Event) -> threading.Thread:
    """
    Background thread: every _STATS_INTERVAL_S seconds append a row per cage
    to <session_dir>/frame_stats.csv with columns:
        timestamp_s, cage_id, fps, drop_count, network_drop_count
    fps is the rolling rate over the last interval based on frames_written delta.
    """
    csv_path = os.path.join(session_dir, "frame_stats.csv")
    prev_frames = {cid: 0 for cid in camera_stats}

    def _run() -> None:
        nonlocal prev_frames
        write_header = not os.path.exists(csv_path)
        while not stop_event.wait(_STATS_INTERVAL_S):
            now = time.time()
            rows = []
            for cid, st in camera_stats.items():
                written   = st["frames_written"]
                delta     = written - prev_frames[cid]
                fps       = delta / _STATS_INTERVAL_S
                prev_frames[cid] = written
                rows.append({
                    "timestamp_s":        round(now, 3),
                    "cage_id":            cid,
                    "fps":                round(fps, 2),
                    "drop_count":         st["drop_count"],
                    "network_drop_count": st["network_drop_count"],
                })
            with open(csv_path, "a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                if write_header:
                    w.writeheader()
                    write_header = False
                w.writerows(rows)

    t = threading.Thread(target=_run, daemon=True, name="stats-logger")
    t.start()
    return t


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

    watchdog    = Watchdog(camera_stats)
    watchdog.start()

    stats_stop  = threading.Event()
    _start_stats_logger(camera_stats, session_dir, stats_stop)
    log.info("Frame stats logger started → %s/frame_stats.csv", session_dir)

    log.info("Acquisition running — %d cages, session: %s", config.N_CAGES, session_dir)

    def shutdown(sig: int, frame) -> None:
        log.info("Shutting down acquisition...")
        stats_stop.set()
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
