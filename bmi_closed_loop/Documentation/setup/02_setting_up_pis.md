# Setting Up New Pis

Three steps: set a static IP, clone the repo, run the setup script.

---

## Step 1 — Set a static IP with nmtui

Run `sudo nmtui` on the Pi. Select **Edit a connection**, choose the wired interface, and set a static IPv4 address following the existing scheme:

```
Address:  192.168.1.1<Pi number>   (e.g. cage 3 → 192.168.1.103)
Netmask:  255.255.255.0
Gateway:  192.168.1.1
```

Save and quit.

---

## Step 2 — Clone the repository

```bash
cd /home/pi
git clone https://github.com/Joujo1/behaviour_bmi.git
```

---

## Step 3 — Run the setup script

```bash
sudo bash /home/pi/behaviour_bmi/bmi_closed_loop/RPi_main/setup.sh
```

The script will ask which Pi number this is (1, 2, 3, …) and then automatically:

- Sets `UDP_STREAM_PORT` in `RPi_main/config.py` to `5000 + Pi number`
- Installs and enables `cage_controller.service` (the main trial process)
- Installs and enables `cpu-governor.service` (locks CPUs to performance frequency)
- Disables the RT scheduling throttle via `/etc/sysctl.d/99-rt.conf`
- Optionally patches `/boot/firmware/cmdline.txt` to isolate CPU core 3 and reboots
- Installs chrony and configures it to use the ETH Zürich NTP servers

The script is safe to re-run if something needs to be redone.

After the script finishes, verify everything is working:

```bash
# RT throttle should print -1
cat /proc/sys/kernel/sched_rt_runtime_us

# CPU governor should print "performance"
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Cage controller should be active
sudo systemctl status cage_controller.service

# NTP should show ETH servers synced (look for * next to the server)
chronyc sources -v
```
