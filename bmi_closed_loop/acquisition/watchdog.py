"""
Camera liveness watchdog. Polls the shared camera_stats dict every
WATCHDOG_INTERVAL_SECONDS and writes per-cage status to Valkey.

Valkey key: camera_status (HSET)
  field : cage_{id}
  value : "{status}|last_seen={t}|fps={n}|drops={n}|net_drops={n}|streaming={0/1}|recording={0/1}"
"""

import time
import threading

import config
from shared.logger import get_logger


class Watchdog:
    """Monitors camera liveness and writes per-cage status to Valkey."""

    def __init__(self, camera_stats: dict):
        self._stats   = camera_stats
        self._running = False
        self._thread  = None
        self._valkey  = None
        self._log     = get_logger("watchdog", config.LOGGING_DIR, config.LOGGING_LEVEL)
        self._prev_frames_written = {cage_id: 0 for cage_id in range(1, config.N_CAGES + 1)}

    def start(self) -> None:
        import valkey as valkey_client

        self._valkey  = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True, name="watchdog")
        self._thread.start()
        self._log.info("Watchdog started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        while self._running:
            now = time.time()
            for cage_id in range(1, config.N_CAGES + 1):
                stats              = self._stats[cage_id]
                last_seen          = stats["last_seen"]
                frames_written     = stats["frames_written"]
                drop_count         = stats["drop_count"]
                network_drop_count = stats["network_drop_count"]

                streaming             = self._valkey.get(f"cage:{cage_id}:streaming")
                intentionally_stopped = streaming == b"0"

                elapsed = now - last_seen if last_seen > 0 else float("inf")
                if elapsed < config.WATCHDOG_DEAD_THRESHOLD_SECONDS:
                    status = "alive"
                elif intentionally_stopped:
                    status = "stopped"
                else:
                    status = "dead"

                fps = frames_written - self._prev_frames_written[cage_id]
                self._prev_frames_written[cage_id] = frames_written

                recording      = self._valkey.get(f"cage:{cage_id}:recording")
                streaming_flag = "1" if streaming == b"1" else "0"
                recording_flag = "1" if recording  == b"1" else "0"
                self._valkey.hset(
                    "camera_status",
                    f"cage_{cage_id}",
                    f"{status}|last_seen={last_seen:.3f}|fps={fps}|drops={drop_count}|net_drops={network_drop_count}|streaming={streaming_flag}|recording={recording_flag}",
                )

                if status == "dead" and last_seen > 0:
                    self._log.warning("Cage %d silent for %.1fs (threshold: %ds)",
                                      cage_id, elapsed, config.WATCHDOG_DEAD_THRESHOLD_SECONDS)

            time.sleep(config.WATCHDOG_INTERVAL_SECONDS)
