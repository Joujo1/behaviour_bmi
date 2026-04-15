"""
stress_logger.py — polls /cameras/status every second and writes to a CSV.

Usage:
    python debug/stress_logger.py [output_file.csv]

Default output: debug/stress_log_<timestamp>.csv
Ctrl-C to stop.
"""

import csv
import sys
import time
import signal
import os
import urllib.request
import json

FLASK_URL = "http://localhost:5000"
POLL_INTERVAL = 1.0  # seconds


def poll_status(url: str) -> dict:
    with urllib.request.urlopen(f"{url}/cameras/status", timeout=2) as r:
        return json.loads(r.read())


def main():
    if len(sys.argv) > 1:
        out_path = sys.argv[1]
    else:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(os.path.dirname(__file__), f"stress_log_{ts}.csv")

    print(f"Logging to: {out_path}")
    print("Ctrl-C to stop.\n")

    stop = False

    def _sig(s, f):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["pc_time", "cage", "status", "fps", "queue_drops", "net_drops", "last_seen_ago_s"])

        t0 = time.time()
        while not stop:
            loop_start = time.time()
            pc_time = loop_start

            try:
                data = poll_status(FLASK_URL)
                for key, val in sorted(data.items()):
                    cage = int(key.replace("cage_", ""))
                    parts = val.split("|")
                    status = parts[0] if parts else "unknown"

                    def _field(prefix):
                        for p in parts:
                            if p.startswith(prefix + "="):
                                return p.split("=", 1)[1]
                        return ""

                    fps        = _field("fps")
                    drops      = _field("drops")
                    net_drops  = _field("net_drops")
                    last_seen  = _field("last_seen")
                    ago = round(pc_time - float(last_seen), 2) if last_seen else ""

                    writer.writerow([
                        round(pc_time, 3), cage, status,
                        fps, drops, net_drops, ago,
                    ])

                f.flush()
                elapsed = round(pc_time - t0, 0)
                print(f"\r  {int(elapsed // 3600):02d}h{int((elapsed % 3600) // 60):02d}m elapsed — "
                      f"last poll ok", end="", flush=True)

            except Exception as e:
                print(f"\n  Poll failed: {e}")

            # sleep remainder of interval
            sleep_for = POLL_INTERVAL - (time.time() - loop_start)
            if sleep_for > 0:
                time.sleep(sleep_for)

    print(f"\nDone. Wrote {out_path}")


if __name__ == "__main__":
    main()
