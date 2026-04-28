"""
GPS PPS logger — records CLOCK_MONOTONIC timestamps of each PPS pulse
alongside the GPS UTC second parsed from NMEA, for post-session drift correction.

Wiring (Adafruit Ultimate GPS breakout):
  GPS TX  → Pi GPIO15  (UART0 RX, physical pin 10)
  GPS RX  → Pi GPIO14  (UART0 TX, physical pin 8)   [optional]
  GPS PPS → Pi GPIO18  (physical pin 12)
  GPS VIN → 3.3 V
  GPS GND → GND

Pi one-time setup:
  1. raspi-config → Interface Options → Serial Port
       → login shell over serial: No
       → serial port hardware enabled: Yes
  2. Add to /boot/firmware/config.txt:
       dtoverlay=pps-gpio,gpiopin=18
  3. Optionally disable Bluetooth for the full UART (better accuracy):
       dtoverlay=disable-bt
       then use GPS_UART_PORT = '/dev/ttyAMA0'
  4. pip install pyserial --break-system-packages
  5. udev rule for /dev/pps0:
       echo 'KERNEL=="pps0", GROUP="dialout", MODE="0660"' | sudo tee /etc/udev/rules.d/99-pps.rules
       sudo udevadm control --reload-rules && sudo udevadm trigger /dev/pps0
  6. Reboot

How timestamps are taken:
  The pps-gpio kernel driver hooks into the GPIO interrupt handler and calls
  ktime_get_real_ts64() before returning — the timestamp is captured in kernel
  context with no userspace scheduling overhead (<1 µs accuracy).
  The timestamp clock is CLOCK_REALTIME. We convert to CLOCK_MONOTONIC (the
  clock used by engine.py for all behavioural events) via a stable offset
  measured once at startup: offset = CLOCK_MONOTONIC − CLOCK_REALTIME.
  This offset equals the time since boot and is constant for the session
  (changes only on NTP step adjustments, which don't happen without network).

Output CSV columns:
  pulse_idx     — 0-based index of the PPS pulse
  monotonic_us  — CLOCK_MONOTONIC at the rising edge, microseconds
  utc_hhmmss    — UTC time of this pulse (HHMMSS from NMEA $GPRMC), empty if no fix
"""

import csv
import ctypes
import ctypes.util
import errno
import os
import queue
import threading
import time
from datetime import datetime

import serial

from config import GPS_PPS_DEV, GPS_UART_PORT, GPS_UART_BAUD, GPS_LOG_DIR


# ── libc ioctl (bypasses Python fcntl integer-conversion quirks) ──────────────

_libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
_libc.ioctl.restype  = ctypes.c_int
_libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]


# ── Linux PPS API (linux/pps.h) ───────────────────────────────────────────────

class _PpsKtime(ctypes.Structure):
    _fields_ = [
        ('sec',   ctypes.c_int64),
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
    ]

class _PpsFdata(ctypes.Structure):
    _fields_ = [
        ('info',    _PpsKinfo),
        ('timeout', _PpsKtime),
    ]

# Ioctl numbers — computed from actual struct sizes so they stay correct
# regardless of compiler padding on this platform.
_PPS_SETPARAMS = (
    (1 << 30) |                             # _IOC_WRITE
    (ctypes.sizeof(_PpsKparams) << 16) |
    (ord('p') << 8) |
    0xa2
)
_PPS_FETCH = (
    (3 << 30) |                             # _IOC_READ | _IOC_WRITE
    (ctypes.sizeof(_PpsFdata) << 16) |
    (ord('p') << 8) |
    0xa4
)

_PPS_API_VERS       = 1
_PPS_CAPTUREASSERT  = 0x01


# ── Clock offset ──────────────────────────────────────────────────────────────

def _measure_rt_to_mono(n: int = 200) -> float:
    """
    Return CLOCK_MONOTONIC − CLOCK_REALTIME, median of n back-to-back pairs.

    Both clocks are vDSO calls (no syscall overhead), so consecutive reads
    are <1 µs apart. The median removes outliers from rare GIL/cache misses.
    The offset equals seconds-since-boot and is stable for the session.
    """
    samples = []
    for _ in range(n):
        rt   = time.clock_gettime(time.CLOCK_REALTIME)
        mono = time.clock_gettime(time.CLOCK_MONOTONIC)
        samples.append(mono - rt)
    samples.sort()
    return samples[n // 2]


# ── Logger ────────────────────────────────────────────────────────────────────

class GPSPPSLogger:
    def __init__(self):
        os.makedirs(GPS_LOG_DIR, exist_ok=True)
        stamp          = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_path = os.path.join(GPS_LOG_DIR, f"gps_pps_{stamp}.csv")
        self._running  = False
        self._pps_queue = queue.Queue()
        self._pulse_idx = 0
        self._pps_thread  = None
        self._nmea_thread = None
        self._file   = None
        self._writer = None
        self._rt_to_mono: float = 0.0

    def start(self):
        self._rt_to_mono = _measure_rt_to_mono()
        print(f"GPS: CLOCK_REALTIME → CLOCK_MONOTONIC offset = {self._rt_to_mono:.6f} s")

        self._file   = open(self._log_path, 'w', newline='')
        self._writer = csv.writer(self._file)
        self._writer.writerow(['pulse_idx', 'monotonic_us', 'utc_hhmmss'])
        self._file.flush()

        self._running = True
        self._pps_thread  = threading.Thread(target=self._pps_loop,
                                             daemon=True, name='gps-pps')
        self._nmea_thread = threading.Thread(target=self._nmea_loop,
                                             daemon=True, name='gps-nmea')
        self._pps_thread.start()
        self._nmea_thread.start()
        print(f"GPS PPS logger started → {self._log_path}")

    def stop(self):
        self._running = False
        if self._pps_thread:
            self._pps_thread.join(timeout=4.0)
        if self._nmea_thread:
            self._nmea_thread.join(timeout=3.0)
        if self._file:
            self._file.close()
        print("GPS PPS logger stopped")

    # ── PPS reader thread ────────────────────────────────────────────────────

    def _pps_loop(self):
        """
        Blocks on PPS_FETCH ioctl (2 s timeout). Each time a pulse arrives the
        kernel fills in assert_tu with the CLOCK_REALTIME timestamp captured in
        the interrupt handler. We convert to CLOCK_MONOTONIC and enqueue it.
        """
        try:
            fd = os.open(GPS_PPS_DEV, os.O_RDWR)
        except OSError as e:
            print(f"GPS PPS: cannot open {GPS_PPS_DEV}: {e}")
            print("  → Is dtoverlay=pps-gpio,gpiopin=18 in /boot/firmware/config.txt?")
            return

        # Enable assert-edge capture — mirrors what ppstest does before PPS_FETCH.
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
                fdata.timeout.sec   = 2   # block up to 2 s for the next pulse
                fdata.timeout.nsec  = 0
                fdata.timeout.flags = 0   # 0 = valid timeout (not PPS_TIME_INVALID)

                ret = _libc.ioctl(fd, _PPS_FETCH, ctypes.byref(fdata))
                if ret == -1:
                    err = ctypes.get_errno()
                    if err in (errno.ETIMEDOUT, errno.ETIME):
                        continue   # no pulse within 2 s — loop and check _running
                    print(f"GPS PPS: ioctl error: errno={err} ({os.strerror(err)})")
                    break

                seq = fdata.info.assert_sequence
                if seq == last_seq:
                    continue   # ioctl returned but no new assert edge
                last_seq = seq

                # Convert kernel CLOCK_REALTIME timestamp to CLOCK_MONOTONIC
                rt_s    = fdata.info.assert_tu.sec
                rt_ns   = fdata.info.assert_tu.nsec
                mono_us = int((rt_s + rt_ns * 1e-9 + self._rt_to_mono) * 1_000_000)

                self._pps_queue.put((self._pulse_idx, mono_us))
                self._pulse_idx += 1
        finally:
            os.close(fd)

    # ── NMEA reader thread ───────────────────────────────────────────────────

    def _nmea_loop(self):
        """
        Reads NMEA sentences from the GPS UART. When a valid $GPRMC with an
        active fix arrives, pairs it with the most recent PPS timestamp and
        writes one CSV row.

        The GPS emits the NMEA sentence 50–200 ms after the PPS pulse for the
        same UTC second, so the queue normally has exactly one pending entry.
        """
        try:
            ser = serial.Serial(GPS_UART_PORT, GPS_UART_BAUD, timeout=1.0)
        except Exception as e:
            print(f"GPS UART open failed ({GPS_UART_PORT}): {e}")
            return

        try:
            while self._running:
                try:
                    raw = ser.readline()
                except Exception:
                    continue

                line = raw.decode('ascii', errors='ignore').strip()
                utc  = _parse_gprmc_utc(line)
                if utc is None:
                    continue

                # Drain the queue: the last entry is the pulse for this sentence.
                entry = None
                while not self._pps_queue.empty():
                    entry = self._pps_queue.get_nowait()

                if entry is not None:
                    idx, mono_us = entry
                    self._writer.writerow([idx, mono_us, utc])
                    self._file.flush()
        finally:
            ser.close()


# ── NMEA helpers ──────────────────────────────────────────────────────────────

def _parse_gprmc_utc(line: str):
    """Extract HHMMSS from a valid $GPRMC/$GNRMC sentence with an active fix."""
    if not (line.startswith('$GPRMC') or line.startswith('$GNRMC')):
        return None
    parts = line.split(',')
    if len(parts) < 3:
        return None
    if parts[2] != 'A':   # 'A' = active fix, 'V' = void
        return None
    return parts[1][:6]   # HHMMSS
