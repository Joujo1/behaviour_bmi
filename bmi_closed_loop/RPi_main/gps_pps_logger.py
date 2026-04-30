"""
GPS PPS logger — captures PPS pulses by parsing ppstest output.

Why subprocess instead of direct ioctl: this Python build returns ENOTTY
on every PPS ioctl (PPS_GETCAP, PPS_FETCH, etc.) despite the same numbers
working from ppstest on the same /dev/pps0 fd. Rather than chase that, we
shell out to ppstest, whose output already contains exactly what we need.

ppstest emits one line per pulse:
  source 0 - assert 1777492762.004053621, sequence: 14155 - clear ...

The assert timestamp is CLOCK_REALTIME, captured inside the GPIO IRQ handler
with sub-µs jitter — better than anything achievable from userspace after a
syscall wakeup.

Time-domain handling:
  CLOCK_REALTIME and CLOCK_MONOTONIC on Linux are two views over the same
  hardware counter, related by a constant offset *as long as nothing slews
  CLOCK_REALTIME*. NTP daemons (timesyncd, chrony, ntpd) slew it; manual
  `date -s` steps it. To stay immune to that, we capture the realtime↔
  monotonic offset on every row, right after parsing the ppstest line.
  Each row's mono_ns is then valid even if NTP is quietly slewing in the
  background. This adds ~1 µs of userspace jitter to mono_ns, which
  averages out in any drift fit over a session.

CSV columns:
  seq           kernel rising-edge counter; gaps = dropped pulses
  realtime_ns   kernel-recorded CLOCK_REALTIME at the IRQ, ns since epoch
                (sub-µs precise — preferred y-axis for drift fits if NTP
                is genuinely off for the session)
  mono_ns       userspace CLOCK_MONOTONIC at parse time, derived per-row
                from realtime_ns + (mono - realtime) measured at that
                instant; rig-domain timestamp, NTP-immune

For drift characterization, prefer:
  - mono_ns if you cannot guarantee NTP is off
  - realtime_ns (with `sudo systemctl stop systemd-timesyncd` before the
    session) if you want maximum per-pulse precision
"""

import csv
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone

from config import GPS_PPS_DEV, GPS_LOG_DIR


# Matches: "...assert 1777492762.004053621, sequence: 14155..."
_PPS_LINE = re.compile(r'assert\s+(\d+)\.(\d+),\s*sequence:\s*(\d+)')


class GPSPPSLogger:
    def __init__(self):
        os.makedirs(GPS_LOG_DIR, exist_ok=True)
        stamp           = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_path  = os.path.join(GPS_LOG_DIR, f"gps_pps_{stamp}.csv")
        self._running   = False
        self._thread    = None
        self._proc      = None
        self._file      = None
        self._writer    = None

    def start(self):
        utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        self._file = open(self._log_path, 'w', newline='')
        self._file.write(f"# session_start_utc={utc_now}\n")
        self._writer = csv.writer(self._file)
        self._writer.writerow(['seq', 'realtime_ns', 'mono_ns'])
        self._file.flush()

        # `stdbuf -oL` forces line buffering on ppstest's stdout. Without it
        # libc switches to 4 KiB block buffering when stdout is a pipe and
        # we'd get pulses in chunks instead of as they arrive.
        try:
            self._proc = subprocess.Popen(
                ['stdbuf', '-oL', 'ppstest', GPS_PPS_DEV],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except FileNotFoundError as e:
            print(f"GPS PPS: cannot start ppstest: {e}")
            print("  → sudo apt install pps-tools coreutils")
            self._file.close()
            return

        self._running = True
        self._thread  = threading.Thread(target=self._pps_loop,
                                         daemon=True, name='gps-pps')
        self._thread.start()
        print(f"GPS PPS logger started → {self._log_path}  (UTC: {utc_now})")

    def stop(self):
        self._running = False
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=1.0)
        if self._thread:
            self._thread.join(timeout=4.0)
        if self._file:
            self._file.close()
        print("GPS PPS logger stopped")

    def _pps_loop(self):
        try:
            for line in self._proc.stdout:
                if not self._running:
                    break

                m = _PPS_LINE.search(line)
                if not m:
                    continue   # banner, "Connection timed out", etc.

                # Capture the realtime↔monotonic offset at this moment so any
                # NTP slewing between session start and now is factored out
                # per-row instead of being baked into a stale offset. Both
                # samples come from the same hardware counter and drift
                # together; the difference is what we want.
                rt_ns_now   = time.clock_gettime_ns(time.CLOCK_REALTIME)
                mono_ns_now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
                offset_ns   = mono_ns_now - rt_ns_now

                sec, nsec, seq = m.groups()
                realtime_ns = int(sec) * 1_000_000_000 + int(nsec)
                mono_ns     = realtime_ns + offset_ns

                self._writer.writerow([seq, realtime_ns, mono_ns])
                self._file.flush()
        except Exception as e:
            print(f"GPS PPS: reader thread error: {e}")