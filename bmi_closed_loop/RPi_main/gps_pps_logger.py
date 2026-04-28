"""
GPS PPS logger — records CLOCK_MONOTONIC timestamps of each PPS pulse
alongside the GPS UTC second parsed from NMEA, for post-session drift correction.

Wiring (Adafruit Ultimate GPS breakout):
  GPS TX  → Pi GPIO15  (UART0 RX, physical pin 10)
  GPS RX  → Pi GPIO14  (UART0 TX, physical pin 8)   [optional, only needed to send commands]
  GPS PPS → Pi GPIO18  (physical pin 12)
  GPS VIN → 3.3 V
  GPS GND → GND

Pi one-time setup:
  sudo raspi-config → Interface Options → Serial Port
    → "login shell over serial" → No
    → "serial port hardware" → Yes
  pip install pyserial

Output CSV columns:
  pulse_idx     — 0-based index of the PPS pulse
  monotonic_us  — CLOCK_MONOTONIC at the rising edge, microseconds
  utc_hhmmss    — UTC time of this pulse (HHMMSS, from NMEA $GPRMC), empty if no fix yet
"""

import csv
import os
import queue
import threading
import time
from datetime import datetime

import RPi.GPIO as GPIO
import serial

from config import GPS_PPS_PIN, GPS_UART_PORT, GPS_UART_BAUD, GPS_LOG_DIR


class GPSPPSLogger:
    def __init__(self):
        os.makedirs(GPS_LOG_DIR, exist_ok=True)
        stamp    = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_path  = os.path.join(GPS_LOG_DIR, f"gps_pps_{stamp}.csv")
        self._running   = False
        self._pps_queue = queue.Queue()
        self._pulse_idx = 0
        self._thread    = None
        self._file      = None
        self._writer    = None

    def start(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(GPS_PPS_PIN, GPIO.IN)
        GPIO.add_event_detect(GPS_PPS_PIN, GPIO.RISING, callback=self._pps_isr)

        self._file   = open(self._log_path, "w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(["pulse_idx", "monotonic_us", "utc_hhmmss"])

        self._running = True
        self._thread  = threading.Thread(target=self._nmea_loop, daemon=True, name="gps-nmea")
        self._thread.start()
        print(f"GPS PPS logger started → {self._log_path}")

    def stop(self):
        self._running = False
        GPIO.remove_event_detect(GPS_PPS_PIN)
        if self._thread:
            self._thread.join(timeout=3.0)
        if self._file:
            self._file.close()
        print("GPS PPS logger stopped")

    # ── PPS interrupt ────────────────────────────────────────────────────────

    def _pps_isr(self, channel):
        # Grab timestamp first — minimal work in the ISR.
        mono_us = int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1_000_000)
        idx = self._pulse_idx
        self._pulse_idx += 1
        self._pps_queue.put((idx, mono_us))

    # ── NMEA reader thread ───────────────────────────────────────────────────

    def _nmea_loop(self):
        """
        Reads NMEA sentences from the GPS UART. When a valid $GPRMC with an
        active fix arrives, pairs it with the most recent PPS timestamp in the
        queue and writes one CSV row.

        Timing: the GPS emits the NMEA sentence 50–200 ms after the PPS pulse
        for the same second. The queue should therefore always have exactly one
        pending entry when the sentence arrives.
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

                line = raw.decode("ascii", errors="ignore").strip()
                utc  = _parse_gprmc_utc(line)
                if utc is None:
                    continue

                # One PPS pulse should be waiting. If somehow two accumulated
                # (e.g. startup race), discard extras to stay in sync.
                entry = None
                while not self._pps_queue.empty():
                    entry = self._pps_queue.get_nowait()

                if entry is not None:
                    idx, mono_us = entry
                    self._writer.writerow([idx, mono_us, utc])
                    self._file.flush()
        finally:
            ser.close()


# ── NMEA helpers ─────────────────────────────────────────────────────────────

def _parse_gprmc_utc(line: str):
    """
    Extract HHMMSS from a valid $GPRMC or $GNRMC sentence with an active fix.
    Returns the 6-character string or None.
    """
    if not (line.startswith("$GPRMC") or line.startswith("$GNRMC")):
        return None
    parts = line.split(",")
    if len(parts) < 3:
        return None
    if parts[2] != "A":   # 'A' = active fix, 'V' = void (no fix)
        return None
    return parts[1][:6]   # HHMMSS (ignore sub-second decimal)
