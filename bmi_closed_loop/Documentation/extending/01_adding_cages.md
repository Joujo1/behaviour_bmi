# Adding Cages to the Dashboard

The system currently runs 12 cages. Adding more (or removing some) is mostly a one-line change. This page walks you through it.

---

## How cage numbering works

Cages are numbered starting from **1**. Every cage gets:

- A **UDP port** — the Pi streams video to port `5000 + cage_id` on the PC (so cage 1 → port 5001, cage 12 → port 5012).
- An **IP address** — the Pi is expected at `192.168.1.{100 + cage_id}` (cage 1 → `192.168.1.101`, cage 12 → `192.168.1.112`).

All of this is calculated automatically from the cage ID. You don't have to set ports or IPs anywhere except the one config variable described below.

---

## Step 1 — Change the cage count

Open [bmi_closed_loop/config.py](../../config.py) and change `N_CAGES`:

```python
N_CAGES = 12   # change this to however many cages you have
```

That is literally the only line you need to touch on the software side. Everything else reads from `N_CAGES`:

| What happens automatically | Where the code lives |
|---|---|
| One UDP listener started per cage | `acquisition/acquisition_main.py` lines 115–125 |
| One TCP command sender created per cage | `ui/ui_main.py` lines 49–57 |
| One CageRunner started per cage | `ui/ui_main.py` lines 60–61 |
| Dashboard cards drawn for each cage | `ui/templates/index.html` lines 336–397 |

---

## Step 2 — Set up the new Pi

Run `setup.sh` on the new Pi. It will ask for the Pi number and then take care of everything automatically:

```bash
sudo bash RPi_main/setup.sh
```

What `setup.sh` does:
- Asks which Pi number this is, then sets `UDP_STREAM_PORT` in `RPi_main/config.py` to `5000 + cage_id`
- Installs and enables the `cage_controller` systemd service (so the Pi software starts on boot)
- Sets the CPU governor to performance mode
- Disables the real-time scheduling throttle (needed for the SCHED_FIFO threads)
- Configures chrony for NTP time sync
- Optionally isolates CPU core 3 for the real-time threads (requires a reboot)

The static IP is **not** set by `setup.sh` — you need to set it manually using `nmtui` in the terminal on the Pi:

```bash
sudo nmtui
```

Go to **Edit a connection → your Ethernet connection → IPv4 configuration**. Set it to **Manual** and enter `192.168.1.{100 + cage_id}` (e.g. cage 13 → `192.168.1.113`). Save and reboot.

For the full Pi setup guide including flashing the OS and installing dependencies, see [Setting Up New Pis](../setup/02_setting_up_pis.md).

---

## That's it

Restart the PC software after changing `N_CAGES`. On the next start, the dashboard will show the new cage card and the UDP listener will open the new port automatically.

---

## What if I want fewer cages?

Just lower `N_CAGES`. Cards and listeners for removed cages will disappear. Any existing data in the database for those cage IDs stays untouched.

---

## Troubleshooting

**The new cage card shows "no signal"** — the Pi is probably not reachable. Check that the Pi is on, has the right static IP, and that the Pi software (`RPi_main/main.py`) is running.

**Port already in use error** — another process is listening on that UDP port. Use `sudo lsof -i UDP:5013` (replace with the port number) to find and stop it.
