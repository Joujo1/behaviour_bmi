"""
GPS PPS logger — records CLOCK_MONOTONIC timestamps of each PPS pulse for
post-session clock-drift correction.

Uses the canonical Linux PPS character-device API (linux/pps.h) via
fcntl.ioctl + struct — no ctypes, no libc lookup, no select/read tricks.

Rationale for PPS_FETCH over select()+read():
  • PPS_FETCH blocks inside the kernel until the next rising edge increments
    the assert_sequence counter, then returns immediately. Same scheduling
    cost as select(), but it's the documented API contract.
  • read() on /dev/pps0 is not part of the documented API. Some kernel
    versions return data, others return -EINVAL — relying on it is fragile.
  • PPS_FETCH gives us assert_sequence, so missed pulses are visible in the
    CSV as gaps in the seq column. select() can't tell us this.

CSV columns:
  seq        — kernel-side rising-edge counter (gaps = dropped pulses)
  mono_us    — CLOCK_MONOTONIC sampled in userspace right after the ioctl
               returns, so it shares the time domain of the rest of the rig

Note on time domains: the kernel also fills in assert_tu (sec, nsec) at IRQ
time with sub-µs precision, but it's CLOCK_REALTIME — not directly comparable
with CLOCK_MONOTONIC samples elsewhere. We ignore it on purpose. The ~tens-of-
µs scheduling jitter on the userspace timestamp averages out completely in a
2-hour polyfit over 7200 pulses.

Important: NTP/timesyncd must be disabled during the session, otherwise the
local clock is being slewed against the same GPS reference we're measuring,
and the drift fit becomes a tautology. `sudo systemctl stop systemd-timesyncd`.
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


# ── Linux PPS API (from <linux/pps.h>) ────────────────────────────────────────
#
# struct pps_ktime  { __s64 sec; __s32 nsec; __u32 flags; }                 16 B
# struct pps_kparams{ s32 api_version; s32 mode;
#                     pps_ktime assert_off_tu; pps_ktime clear_off_tu; }   40 B
# struct pps_kinfo  { __u32 assert_sequence; __u32 clear_sequence;
#                     pps_ktime assert_tu;    pps_ktime clear_tu;
#                     s32 current_mode; }                                  48 B
# struct pps_fdata  { pps_kinfo info; pps_ktime timeout; }                 64 B
#
# Format strings use '=' (standard sizes, no native alignment) plus an
# explicit '4x' to match the kernel's 4-byte trailing pad on pps_kinfo.

_KPARAMS_FMT = '=iiqiIqiI'         # 40 B  (matches kernel sizeof)
_FDATA_FMT   = '=IIqiIqiIi4xqiI'   # 64 B  (info + timeout)
assert struct.calcsize(_KPARAMS_FMT) == 40
assert struct.calcsize(_FDATA_FMT)   == 64

_PPS_API_VERS_1    = 1
_PPS_CAPTUREASSERT = 0x01

# Replicate the _IOC encoding from <asm-generic/ioctl.h>:
#   bits 31..30 = direction, 29..16 = size, 15..8 = type, 7..0 = nr
def _IOC(direction, type_char, nr, size):
    return (direction << 30) | (size << 16) | (ord(type_char) << 8) | nr

_PPS_SETPARAMS = _IOC(1,     'p', 0xa2, struct.calcsize(_KPARAMS_FMT))  # _IOW
_PPS_FETCH     = _IOC(1 | 2, 'p', 0xa4, struct.calcsize(_FDATA_FMT))    # _IOWR

# Pre-built pps_fdata template with a 2-second timeout. Re-packed each
# iteration because PPS_FETCH overwrites the buffer with the result.
_FETCH_TEMPLATE = struct.pack(
    _FDATA_FMT,
    0, 0,           # assert_sequence, clear_sequence
    0, 0, 0,        # assert_tu  (sec, nsec, flags)
    0, 0, 0,        # clear_tu
    0,              # current_mode
    2, 0, 0,        # timeout    (sec=2, nsec=0, flags=0)
)


# ── Logger ────────────────────────────────────────────────────────────────────

class GPSPPSLogger:
    def __init__(self):
        os.makedirs(GPS_LOG_DIR, exist_ok=True)
        stamp           = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_path  = os.path.join(GPS_LOG_DIR, f"gps_pps_{stamp}.csv")
        self._running   = False
        self._thread    = None
        self._file      = None
        self._writer    = None

    def start(self):
        utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        self._file = open(self._log_path, 'w', newline='')
        self._file.write(f"# session_start_utc={utc_now}\n")
        self._writer = csv.writer(self._file)
        self._writer.writerow(['seq', 'mono_us'])
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

        try:
            # Configure capture mode: rising edges, no offset corrections.
            params = struct.pack(_KPARAMS_FMT,
                                 _PPS_API_VERS_1,    # api_version
                                 _PPS_CAPTUREASSERT, # mode
                                 0, 0, 0,            # assert_off_tu (sec, nsec, flags)
                                 0, 0, 0)            # clear_off_tu
            try:
                fcntl.ioctl(fd, _PPS_SETPARAMS, params)
            except OSError as e:
                # Some pps-gpio versions don't honour SETPARAMS but still
                # capture correctly with default settings. Don't bail.
                print(f"GPS PPS: PPS_SETPARAMS failed ({e}) — continuing")

            last_seq = None
            while self._running:
                # Fresh buffer each iteration: PPS_FETCH writes the result
                # into the buffer, clobbering the timeout fields.
                buf = bytearray(_FETCH_TEMPLATE)
                try:
                    fcntl.ioctl(fd, _PPS_FETCH, buf, True)
                except OSError as e:
                    if e.errno in (errno.ETIMEDOUT, errno.ETIME):
                        continue                # no pulse in 2 s — keep waiting
                    print(f"GPS PPS: PPS_FETCH failed: {e}")
                    break

                # Sample CLOCK_MONOTONIC immediately after the ioctl unblocks,
                # in the same time domain as everything else in the rig.
                mono_us = int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1_000_000)

                # Only the first uint32 of the fdata buffer (assert_sequence)
                # matters for our purposes — pull it out without unpacking the
                # full 64 bytes.
                seq = struct.unpack_from('=I', buf, 0)[0]
                if seq == last_seq:
                    # Spurious wake (shouldn't happen on PPS_FETCH, but cheap
                    # to guard against).
                    continue
                last_seq = seq

                self._writer.writerow([seq, mono_us])
                self._file.flush()
        finally:
            os.close(fd)