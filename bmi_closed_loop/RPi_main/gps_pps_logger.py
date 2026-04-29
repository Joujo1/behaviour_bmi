"""
GPS PPS logger — records CLOCK_MONOTONIC timestamps of each PPS pulse for
post-session clock-drift correction.

How it works:
  The pps-gpio kernel driver implements both an ioctl API and standard poll/read
  vfs operations. We use select() + read() instead of the PPS_FETCH ioctl because
  on 64-bit kernels with a 32-bit Python process, the ioctl compat path returns
  ENOTTY (pps_core does not register a compat_ioctl handler). select() and read()
  are not affected by this — they go through a separate vfs path.

  select.select() blocks on /dev/pps0 until the fd becomes readable, which the
  kernel marks at the moment the GPIO interrupt fires. We sample CLOCK_MONOTONIC
  immediately after select() returns. Scheduling latency (typically < 100 µs) is
  small, constant, and irrelevant for characterising ~100 ppm crystal drift.

  Post-processing: fit a line through (pulse_idx, monotonic_us) with
  numpy.polyfit. The slope gives the true oscillator period (should be very
  close to 1 000 000 µs/pulse). Use it to correct any stored timestamp for
  cumulative drift over a 2-hour session.

CSV columns:
  pulse_idx     — 0-based index of the PPS rising edge
  monotonic_us  — CLOCK_MONOTONIC sampled immediately after select() returns

The session-start UTC is written once as a comment on line 1 of the CSV so the
pulse stream can be anchored to wall-clock time without NMEA parsing.

Wiring (Adafruit Ultimate GPS breakout):
  GPS PPS → Pi GPIO18  (physical pin 12)
  GPS VIN → 3.3 V
  GPS GND → GND

Pi one-time setup:
  1. raspi-config → Interface Options → Serial Port
       → login shell over serial: No
       → serial port hardware enabled: Yes
  2. Add to /boot/firmware/config.txt:
       dtoverlay=pps-gpio,gpiopin=18
  3. Add pps-gpio to /etc/modules:
       echo 'pps-gpio' | sudo tee -a /etc/modules
  4. udev rule for /dev/pps0:
       echo 'KERNEL=="pps0", GROUP="dialout", MODE="0660"' | sudo tee /etc/udev/rules.d/99-pps.rules
       sudo udevadm control --reload-rules && sudo udevadm trigger /dev/pps0
  5. Reboot

Note: the Adafruit MTK3339 only outputs PPS after a 3D fix, so any pulse logged
here confirms the GPS had a valid fix at that moment — no NMEA parsing needed.
"""

import csv
import os
import select
import threading
import time
from datetime import datetime, timezone

from config import GPS_PPS_DEV, GPS_LOG_DIR


class GPSPPSLogger:
    def __init__(self):
        os.makedirs(GPS_LOG_DIR, exist_ok=True)
        stamp          = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_path = os.path.join(GPS_LOG_DIR, f"gps_pps_{stamp}.csv")
        self._running  = False
        self._pulse_idx = 0
        self._thread   = None
        self._file     = None
        self._writer   = None

    def start(self):
        utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        self._file = open(self._log_path, 'w', newline='')
        self._file.write(f"# session_start_utc={utc_now}\n")
        self._writer = csv.writer(self._file)
        self._writer.writerow(['pulse_idx', 'monotonic_us'])
        self._file.flush()

        self._running = True
        self._thread  = threading.Thread(target=self._pps_loop,
                                         daemon=True, name='gps-pps')
        self._thread.start()
        print(f"GPS PPS logger started → {self._log_path}  (session UTC: {utc_now})")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=4.0)
        if self._file:
            self._file.close()
        print("GPS PPS logger stopped")

    def _pps_loop(self):
        try:
            fd = os.open(GPS_PPS_DEV, os.O_RDONLY)
        except OSError as e:
            print(f"GPS PPS: cannot open {GPS_PPS_DEV}: {e}")
            print("  → Is dtoverlay=pps-gpio,gpiopin=18 in /boot/firmware/config.txt?")
            return

        try:
            while self._running:
                # Block until /dev/pps0 is readable (a PPS pulse has arrived)
                # or the 2-second timeout expires.
                r, _, _ = select.select([fd], [], [], 2.0)
                if not r:
                    continue  # timeout — no pulse, check _running and loop

                # Sample CLOCK_MONOTONIC immediately when select() returns.
                # The fd becomes readable the moment the kernel GPIO interrupt fires.
                mono_us = int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1_000_000)

                # Drain the readable event so the next select() blocks correctly.
                try:
                    os.read(fd, 32)
                except OSError:
                    break

                self._writer.writerow([self._pulse_idx, mono_us])
                self._file.flush()
                self._pulse_idx += 1
        finally:
            os.close(fd)
