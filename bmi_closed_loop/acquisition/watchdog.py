import time
import threading

import config
from shared.logger import get_logger


class Watchdog:
    """
    Monitors camera liveness and writes status to Valkey.

    Reads from the shared camera_stats dict (written by listener/writer threads).
    Writes only to Valkey — no DB, no NAS.

    Valkey key: camera_status (HSET)
      field: cage_{id}
      value: "alive|dead" + last_seen + rolling_fps + drop_count
    """

    def __init__(self, camera_stats: dict):
        self._stats = camera_stats
        self._running = False
        self._thread = None
        self._valkey = None
        self._log = get_logger("watchdog", config.LOGGING_DIR, config.LOGGING_LEVEL)
        self._prev_frame_counts = {i: 0 for i in range(config.N_CAGES)}

    def start(self):
        import valkey as valkey_client

        self._valkey = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="watchdog")
        self._thread.start()
        self._log.info("Watchdog started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self):
        while self._running:
            now = time.time()
            for cage_id in range(config.N_CAGES):
                stats = self._stats[cage_id]
                last_seen = stats["last_seen"]
                frame_count = stats["frame_count"]
                drop_count = stats["drop_count"]

                elapsed = now - last_seen if last_seen > 0 else float("inf")
                status = "alive" if elapsed < config.WATCHDOG_DEAD_THRESHOLD_SECONDS else "dead"

                fps = frame_count - self._prev_frame_counts[cage_id]
                self._prev_frame_counts[cage_id] = frame_count

                self._valkey.hset(
                    "camera_status",
                    f"cage_{cage_id}",
                    f"{status}|last_seen={last_seen:.3f}|fps={fps}|drops={drop_count}",
                )

                if status == "dead" and last_seen > 0:
                    self._log.warning(
                        f"Cage {cage_id} silent for {elapsed:.1f}s (threshold: {config.WATCHDOG_DEAD_THRESHOLD_SECONDS}s)"
                    )

            time.sleep(config.WATCHDOG_INTERVAL_SECONDS)
