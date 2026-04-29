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
       → serial port hardware enabled: Yes   (needed for UART, ignored if BT disabled)
  2. Add to /boot/firmware/config.txt:
       dtoverlay=pps-gpio,gpiopin=18
       dtoverlay=disable-bt          (frees full UART; not required for PPS-only use)
  3. udev rule for /dev/pps0:
       echo 'KERNEL=="pps0", GROUP="dialout", MODE="0660"' | sudo tee /etc/udev/rules.d/99-pps.rules
       sudo udevadm control --reload-rules && sudo udevadm trigger /dev/pps0
  4. Reboot

Note: the Adafruit MTK3339 only outputs PPS after a 3D fix, so any pulse logged
here confirms the GPS had a valid fix at that moment — no NMEA parsing needed.
"""

import csv
import ctypes
import ctypes.util
import errno
import os
import threading
import time
from datetime import datetime, timezone

from config import GPS_PPS_DEV, GPS_LOG_DIR


# ── libc ioctl ────────────────────────────────────────────────────────────────

_libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
_libc.ioctl.restype  = ctypes.c_int
_libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]


# ── Linux PPS API (linux/pps.h) ───────────────────────────────────────────────

class _PpsKtime(ctypes.Structure):
    _fields_ = [
        ('sec',   ctypes.c_longlong),  # __s64 — c_longlong is 8-byte aligned on ARM (32 and 64-bit)
        ('nsec',  ctypes.c_int32),
        ('flags', ctypes.c_uint32),
    ]

class _PpsKparams(ctypes.Structure):
    _fields_ = [
        ('api_version',   ctypes.c_int32),
        ('mode',          ctypes.c_int32),
        ('assert_off_tu', _PpsKtime),
        ('clear_off_tu',  _PpsKtime),
    ]

class _PpsKinfo(ctypes.Structure):
    _fields_ = [
        ('assert_sequence', ctypes.c_uint32),
        ('clear_sequence',  ctypes.c_uint32),
        ('assert_tu',       _PpsKtime),
        ('clear_tu',        _PpsKtime),
        ('current_mode',    ctypes.c_int32),
        ('_pad',            ctypes.c_uint32),  # explicit tail pad — kernel aligns to 8 bytes
    ]

class _PpsFdata(ctypes.Structure):
    _fields_ = [
        ('info',    _PpsKinfo),
        ('timeout', _PpsKtime),
    ]

# Sanity check at import time — catches any future struct-layout regression.
assert ctypes.sizeof(_PpsKparams) == 40, f"_PpsKparams size {ctypes.sizeof(_PpsKparams)} != 40"
assert ctypes.sizeof(_PpsFdata)   == 64, f"_PpsFdata size {ctypes.sizeof(_PpsFdata)} != 64"

_PPS_SETPARAMS = (
    (1 << 30) |
    (ctypes.sizeof(_PpsKparams) << 16) |
    (ord('p') << 8) |
    0xa2
)
_PPS_FETCH = (
    (3 << 30) |
    (ctypes.sizeof(_PpsFdata) << 16) |
    (ord('p') << 8) |
    0xa4
)

_PPS_API_VERS      = 1
_PPS_CAPTUREASSERT = 0x01


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
        # First line: UTC anchor as a comment so the CSV is still machine-readable
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

        params = _PpsKparams()
        params.api_version = _PPS_API_VERS
        params.mode        = _PPS_CAPTUREASSERT
        ret = _libc.ioctl(fd, _PPS_SETPARAMS, ctypes.byref(params))
        if ret == -1:
            err = ctypes.get_errno()
            print(f"GPS PPS: PPS_SETPARAMS failed: errno={err} ({os.strerror(err)}) — continuing anyway")

        fdata    = _PpsFdata()
        last_seq = None

        try:
            while self._running:
                fdata.timeout.sec   = 2
                fdata.timeout.nsec  = 0
                fdata.timeout.flags = 0

                ret = _libc.ioctl(fd, _PPS_FETCH, ctypes.byref(fdata))

                # Sample CLOCK_MONOTONIC immediately after the ioctl unblocks.
                # Scheduling latency here is negligible vs. the 1 Hz pulse period.
                mono_us = int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1_000_000)

                if ret == -1:
                    err = ctypes.get_errno()
                    if err in (errno.ETIMEDOUT, errno.ETIME):
                        continue
                    print(f"GPS PPS: ioctl error: errno={err} ({os.strerror(err)})")
                    break

                seq = fdata.info.assert_sequence
                if seq == last_seq:
                    continue
                last_seq = seq

                self._writer.writerow([self._pulse_idx, mono_us])
                self._file.flush()
                self._pulse_idx += 1
        finally:
            os.close(fd)
