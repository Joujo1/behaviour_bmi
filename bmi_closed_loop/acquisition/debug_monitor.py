import csv
import os
import threading
import time


class DebugMonitor:
    """
    Periodically samples UDP receive queue depth for each cage
    and appends one row per cage per interval to a CSV file.

    CSV columns:
        timestamp         - wall clock (seconds since epoch)
        cage_id
        udp_queue         - packets waiting in UDPreceiver.packet_queue
        udp_queue_max     - queue capacity (constant, for reference)
        frames_written    - total frames written so far for this cage
        drop_count        - total frames dropped so far for this cage
        network_drop_count
    """

    def __init__(self, listeners, camera_stats, interval_seconds=1.0, output_path="/home/sentinel/new_vr/bmi_closed_loop/logs/debug_queues.csv"):
        self._listeners = listeners      # list of UDPreceiver, indexed by cage_id
        self._stats = camera_stats       # shared stats dict from acquisition_main
        self._interval = interval_seconds
        self._output_path = output_path
        self._running = False
        self._thread = None

    def start(self):
        os.makedirs(os.path.dirname(self._output_path), exist_ok=True)
        write_header = not os.path.exists(self._output_path)
        self._file = open(self._output_path, "a", newline="")
        self._csv = csv.writer(self._file)
        if write_header:
            self._csv.writerow([
                "timestamp", "cage_id",
                "udp_queue", "udp_queue_max",
                "frames_written", "drop_count", "network_drop_count",
            ])
            self._file.flush()

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="debug-monitor")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._file:
            self._file.close()

    def _loop(self):
        while self._running:
            ts = time.time()
            for cage_id, listener in enumerate(self._listeners, start=1):
                stats = self._stats[cage_id]
                self._csv.writerow([
                    f"{ts:.3f}",
                    cage_id,
                    listener.queue_size(),
                    listener.packet_queue.maxsize,
                    stats["frames_written"],
                    stats["drop_count"],
                    stats["network_drop_count"],
                ])
            self._file.flush()
            time.sleep(self._interval)
