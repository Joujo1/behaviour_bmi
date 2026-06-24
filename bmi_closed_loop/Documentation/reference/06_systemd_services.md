# Systemd Services on Pi

Two systemd services run on every cage Pi, plus one sysctl config file for real-time scheduling. The unit files are defined in [RPi_main/systemmd.txt](../../RPi_main/systemmd.txt).

---

## Services

### `cage_controller.service`

The main cage process. Runs `RPi_main/main.py` as root with `SCHED_FIFO` priority 70.

**Install path:** `/etc/systemd/system/cage_controller.service`

Key settings:
- `Restart=always` — automatically restarts on crash with a 5-second delay.
- `User=root` — required for gpiod v2 GPIO access and `SCHED_FIFO` scheduling.
- `CPUSchedulingPolicy=fifo` / `CPUSchedulingPriority=70` — elevates the main process to real-time before Python starts.
- `LimitMEMLOCK=infinity` — needed for `mlock()` if used by gpiod internals.
- `StandardOutput=journal` / `StandardError=journal` — all output goes to systemd journal (read with `journalctl`).

### `cpu-governor.service`

One-shot service that runs at boot and sets all CPU cores to the `performance` cpufreq governor. This prevents frequency-scaling latency spikes when the Pi's CPU ramps up from idle.

**Install path:** `/etc/systemd/system/cpu-governor.service`

---

## RT sysctl config

**Install path:** `/etc/sysctl.d/99-rt.conf`

Contains one line:
```
kernel.sched_rt_runtime_us = -1
```

This removes the kernel's default RT budget throttle (which would cap `SCHED_FIFO` threads at 95 % CPU time and cause forced ~50 ms stalls). The cage controller also sets this at runtime in `main.py`, but the sysctl file ensures it survives reboots without depending on the service.

---

## CPU core isolation

Add the following to the end of `/boot/firmware/cmdline.txt` (single line, no newline):

```
isolcpus=3 nohz_full=3 rcu_nocbs=3 irqaffinity=0-2
```

After a reboot, core 3 is reserved for the RT Python threads (GPIO monitor and FSM). The H264 encoder, network stack, and kernel threads are confined to cores 0–2.

---

## Common commands

```bash
# Check service status
sudo systemctl status cage_controller.service
sudo systemctl status cpu-governor.service

# View live logs
journalctl -u cage_controller.service -f

# Restart after a code change
sudo systemctl restart cage_controller.service

# Stop / start manually
sudo systemctl stop cage_controller.service
sudo systemctl start cage_controller.service

# Verify RT throttle is disabled (should print -1)
cat /proc/sys/kernel/sched_rt_runtime_us

# Verify CPU governor (should print "performance" for each core)
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Check which CPU core the cage process is running on
grep Cpus_allowed_list /proc/$(pgrep -f main.py)/status
```

---

## First-time setup

All services are installed automatically by [RPi_main/setup.sh](../../RPi_main/setup.sh). See [setup/02_setting_up_pis.md](../setup/02_setting_up_pis.md) for instructions.
