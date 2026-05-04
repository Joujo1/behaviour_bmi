"""
System health monitor — runs alongside the main server as a separate process.

Polls CPU temperature, CPU frequency (detects thermal throttling), and
free memory every POLL_S seconds. Writes to CSV and prints a live dashboard.

Throttling is detected by comparing the current CPU frequency against the
nominal maximum — a significant drop means the SoC has hit its thermal limit,
which could degrade trial timing and audio performance.

On Ctrl+C: saves a summary plot.

Usage:
    python3 debug/monitor_system.py [--poll 5] [--out output/system.csv]
"""

import argparse
import csv
import os
import signal
import sys
import time
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# /sys paths on Raspberry Pi OS
_TEMP_PATH     = "/sys/class/thermal/thermal_zone0/temp"
_FREQ_CUR_PATH = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
_FREQ_MAX_PATH = "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"
_MEM_PATH      = "/proc/meminfo"


def _read_int(path: str) -> int | None:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _read_meminfo() -> dict:
    result = {}
    try:
        with open(_MEM_PATH) as f:
            for line in f:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemAvailable:"):
                    result[parts[0][:-1]] = int(parts[1])   # kB
    except Exception:
        pass
    return result


def poll() -> dict | None:
    raw_temp = _read_int(_TEMP_PATH)
    freq_cur = _read_int(_FREQ_CUR_PATH)
    freq_max = _read_int(_FREQ_MAX_PATH)
    mem      = _read_meminfo()

    if raw_temp is None:
        return None

    temp_c      = raw_temp / 1000.0
    freq_mhz    = (freq_cur / 1000.0) if freq_cur else None
    freq_max_mhz= (freq_max / 1000.0) if freq_max else None
    throttled   = (freq_mhz < freq_max_mhz * 0.95) if (freq_mhz and freq_max_mhz) else False
    mem_total   = mem.get("MemTotal",     0) / 1024.0   # MB
    mem_avail   = mem.get("MemAvailable", 0) / 1024.0   # MB
    mem_used    = mem_total - mem_avail

    return {
        "timestamp":    datetime.now().isoformat(timespec="seconds"),
        "temp_c":       round(temp_c, 1),
        "freq_mhz":     round(freq_mhz, 0)     if freq_mhz     else None,
        "freq_max_mhz": round(freq_max_mhz, 0) if freq_max_mhz else None,
        "throttled":    int(throttled),
        "mem_used_mb":  round(mem_used, 1),
        "mem_total_mb": round(mem_total, 1),
    }


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = os.path.join(OUTPUT_DIR, f"system_{ts}.csv")

    p = argparse.ArgumentParser(description="Pi system health monitor")
    p.add_argument("--poll", type=float, default=5.0,
                   help="Poll interval in seconds (default: 5)")
    p.add_argument("--out", default=default_out, help="Output CSV path")
    args = p.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    rows: list = []

    csv_file   = open(args.out, "w", newline="")
    csv_writer = None   # initialised on first row

    print(f"System monitor  poll={args.poll:.0f} s  → {args.out}")
    print(f"{'Time':>10}  {'Temp':>7}  {'Freq':>9}  {'Throttle':>8}  {'Mem used':>10}")
    print("─" * 55)

    def finish(signum=None, frame=None):
        csv_file.close()
        print(f"\nStopped. {len(rows)} samples recorded → {args.out}")
        if len(rows) >= 5:
            _save_plot(rows, args.out)
        sys.exit(0)

    signal.signal(signal.SIGINT,  finish)
    signal.signal(signal.SIGTERM, finish)

    t0 = time.monotonic()
    while True:
        sample = poll()
        if sample is None:
            print("WARNING: could not read /sys — is this a Raspberry Pi?")
            time.sleep(args.poll)
            continue

        rows.append(sample)

        if csv_writer is None:
            csv_writer = csv.DictWriter(csv_file, fieldnames=list(sample.keys()))
            csv_writer.writeheader()
        csv_writer.writerow(sample)
        csv_file.flush()

        elapsed = time.monotonic() - t0
        throttle_str = "YES ⚠" if sample["throttled"] else "no"
        freq_str = f"{sample['freq_mhz']:.0f} MHz" if sample["freq_mhz"] else "n/a"
        print(f"  {elapsed:7.0f} s  "
              f"{sample['temp_c']:5.1f} °C  "
              f"{freq_str:>9}  "
              f"{throttle_str:>8}  "
              f"{sample['mem_used_mb']:6.0f} MB")

        time.sleep(args.poll)


def _save_plot(rows: list, csv_path: str) -> None:
    import numpy as np

    temps    = [r["temp_c"]       for r in rows]
    freqs    = [r["freq_mhz"]     for r in rows]
    throttle = [r["throttled"]    for r in rows]
    mem_used = [r["mem_used_mb"]  for r in rows]

    # Convert sample index to minutes using actual poll interval
    # (rows may not be perfectly spaced, use index as approximation)
    n = len(rows)

    fig = plt.figure(figsize=(12, 9))
    fig.suptitle("Pi system health during session", fontsize=13, fontweight="bold")
    gs = gridspec.GridSpec(3, 1, hspace=0.45)

    ax1 = fig.add_subplot(gs[0])
    ax1.plot(temps, color="#e15759", linewidth=1.2)
    ax1.axhline(80, color="red", linewidth=0.8, linestyle="--", label="80 °C throttle threshold")
    ax1.set_ylabel("CPU temp (°C)")
    ax1.set_title("CPU temperature")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    ax2 = fig.add_subplot(gs[1])
    if any(f is not None for f in freqs):
        freq_max = max(f for f in freqs if f is not None)
        ax2.plot([f if f else 0 for f in freqs], color="#4e79a7", linewidth=1.2)
        ax2.axhline(freq_max, color="grey", linewidth=0.8, linestyle="--",
                    label=f"max {freq_max:.0f} MHz")
        # Mark throttled samples
        thr_idx = [i for i, v in enumerate(throttle) if v]
        if thr_idx:
            ax2.scatter(thr_idx, [freqs[i] for i in thr_idx],
                        color="red", s=20, zorder=5, label="throttled")
    ax2.set_ylabel("CPU freq (MHz)")
    ax2.set_title("CPU frequency (drop = thermal throttling)")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)

    ax3 = fig.add_subplot(gs[2])
    ax3.plot(mem_used, color="#f28e2b", linewidth=1.2)
    ax3.set_ylabel("Memory used (MB)")
    ax3.set_xlabel("Sample index")
    ax3.set_title("Memory usage")
    ax3.grid(True, alpha=0.3)

    out_png = csv_path.replace(".csv", ".png")
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    print(f"Plot saved → {out_png}")
    plt.show()


if __name__ == "__main__":
    main()
