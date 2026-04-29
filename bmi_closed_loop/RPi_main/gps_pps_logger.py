"""
GPS PPS logger — records CLOCK_MONOTONIC timestamps of each PPS pulse for
post-session clock-drift correction.

How it works:
  The pps-gpio kernel driver hooks into the GPIO interrupt handler and sets an
  internal assert_sequence counter the moment the rising edge arrives.
  PPS_FETCH blocks until the sequence number advances, then returns immediately.
  We sample CLOCK_MONOTONIC right after the ioctl returns; the scheduling
  latency is negligible (<< 1 ms) compared to the 1 Hz pulse period and the
  ~100 ppm crystal drift we are trying to characterise.

  Post-processing: fit a line through (pulse_idx, monotonic_us) with
  numpy.polyfit. The slope gives the true oscillator period (should be very
  close to 1 000 000 µs/pulse). Divide any stored timestamp by the fitted
  period to correct for cumulative drift over a 2-hour session.

CSV columns:
  pulse_idx     — 0-based index of the PPS rising edge
  monotonic_us  — CLOCK_MONOTONIC sampled immediately after PPS_FETCH returns

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
  3. udev rule for /dev/pps0:
       echo 'KERNEL=="pps0", GROUP="dialout", MODE="0660"' | sudo tee /etc/udev/rules.d/99-pps.rules
       sudo udevadm control --reload-rules && sudo udevadm trigger /dev/pps0
  4. Reboot

Note: the Adafruit MTK3339 only outputs PPS after a 3D fix, so any pulse logged
here confirms the GPS had a valid fix at that moment — no NMEA parsing needed.
"""

import csv
import errno
import fcntl
import os
import struct
import threading
import time
from datetime import datetime, timezone

from config import GPS_PPS_DEV, GPS_LOG_DIR


# ── Linux PPS API (linux/pps.h) ───────────────────────────────────────────────
#
# Ioctl numbers are hardcoded from the kernel ABI (verified by running the
# Python struct-size check and comparing with ppstest via strace on this Pi).
#   _IOW ('p', 0xa2, struct pps_kparams)  — sizeof = 40 → 0x402870a2
#   _IOWR('p', 0xa4, struct pps_fdata)    — sizeof = 64 → 0xc04070a4

_PPS_SETPARAMS = 0x402870a2
_PPS_FETCH     = 0xc04070a4

_PPS_API_VERS      = 1
_PPS_CAPTUREASSERT = 0x01

# struct pps_kparams (40 bytes, little-endian, no implicit padding needed):
#   int32  api_version
#   int32  mode
#   int64  assert_off_tu.sec,  int32 .nsec,  uint32 .flags
#   int64  clear_off_tu.sec,   int32 .nsec,  uint32 .flags
_KPARAMS_PACK = '<iiqIIqII'

# struct pps_fdata (64 bytes):
#   uint32 assert_sequence,  uint32 clear_sequence
#   int64  assert_tu.sec,    int32 .nsec,  uint32 .flags   (offset  8)
#   int64  clear_tu.sec,     int32 .nsec,  uint32 .flags   (offset 24)
#   int32  current_mode,     uint32 _pad                   (offset 40)
#   int64  timeout.sec,      int32 .nsec,  uint32 .flags   (offset 48)
_FDATA_PACK = '<IIqIIqIIiIqII'
_FDATA_SIZE = struct.calcsize(_FDATA_PACK)   # must be 64

assert _FDATA_SIZE == 64, f"pps_fdata size mismatch: {_FDATA_SIZE} != 64"

_FDATA_TIMEOUT_OFFSET     = 48   # byte offset of the timeout field in pps_fdata
_FDATA_ASSERT_SEQ_OFFSET  = 0    # byte offset of assert_sequence


# ── Logger ────────────────────────────────────────────────────────────────────

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
            fd = os.open(GPS_PPS_DEV, os.O_RDWR)
        except OSError as e:
            print(f"GPS PPS: cannot open {GPS_PPS_DEV}: {e}")
            print("  → Is dtoverlay=pps-gpio,gpiopin=18 in /boot/firmware/config.txt?")
            return

        # Enable assert-edge capture.
        params = struct.pack(_KPARAMS_PACK,
                             _PPS_API_VERS, _PPS_CAPTUREASSERT,
                             0, 0, 0,   # assert_off_tu
                             0, 0, 0)   # clear_off_tu
        try:
            fcntl.ioctl(fd, _PPS_SETPARAMS, params)
        except OSError as e:
            print(f"GPS PPS: PPS_SETPARAMS failed: {e} — continuing anyway")

        buf      = bytearray(_FDATA_SIZE)
        last_seq = None

        try:
            while self._running:
                # Write 2-second timeout into fdata.timeout before each call.
                struct.pack_into('<qII', buf, _FDATA_TIMEOUT_OFFSET, 2, 0, 0)

                try:
                    fcntl.ioctl(fd, _PPS_FETCH, buf, True)
                except OSError as e:
                    if e.errno in (errno.ETIMEDOUT, errno.ETIME):
                        continue
                    print(f"GPS PPS: PPS_FETCH failed: {e}")
                    break

                # Sample CLOCK_MONOTONIC immediately after the ioctl unblocks.
                mono_us = int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1_000_000)

                seq = struct.unpack_from('<I', buf, _FDATA_ASSERT_SEQ_OFFSET)[0]
                if seq == last_seq:
                    continue
                last_seq = seq

                self._writer.writerow([self._pulse_idx, mono_us])
                self._file.flush()
                self._pulse_idx += 1
        finally:
            os.close(fd)
