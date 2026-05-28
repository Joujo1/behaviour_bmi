#!/usr/bin/env bash
# setup.sh — Full automated setup for one Pi cage controller.
# Run as root:  sudo bash setup.sh
# Re-running is safe (idempotent).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

[[ $EUID -ne 0 ]] && { echo "Run as root: sudo bash $0"; exit 1; }

# ── Pi number prompt ──────────────────────────────────────────────────────────
while true; do
    read -r -p "Which Pi number is this? (1, 2, 3, ...): " PI_NUM
    [[ "$PI_NUM" =~ ^[1-9][0-9]*$ ]] && break
    echo "  Enter a positive integer."
done
UDP_PORT=$((5000 + PI_NUM))
CONFIG_FILE="$SCRIPT_DIR/config.py"
if grep -q "^UDP_STREAM_PORT" "$CONFIG_FILE"; then
    sed -i "s/^UDP_STREAM_PORT\s*=.*/UDP_STREAM_PORT = $UDP_PORT/" "$CONFIG_FILE"
    echo "  UDP_STREAM_PORT set to $UDP_PORT in config.py (Pi #$PI_NUM)"
else
    echo "  WARNING: UDP_STREAM_PORT not found in config.py — set it manually to $UDP_PORT"
fi

echo "=== Step 1: cage_controller.service ==="
cat > /etc/systemd/system/cage_controller.service << EOF
[Unit]
Description=Cage Controller
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 $SCRIPT_DIR/main.py
WorkingDirectory=$SCRIPT_DIR
Restart=always
RestartSec=5
User=root
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal
CPUSchedulingPolicy=fifo
CPUSchedulingPriority=70
LimitMEMLOCK=infinity

[Install]
WantedBy=multi-user.target
EOF
echo "  Written /etc/systemd/system/cage_controller.service"

echo "=== Step 2: cpu-governor.service ==="
cat > /etc/systemd/system/cpu-governor.service << EOF
[Unit]
Description=Set CPU scaling governor to performance
After=multi-user.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c "echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"

[Install]
WantedBy=multi-user.target
EOF
echo "  Written /etc/systemd/system/cpu-governor.service"

echo "=== Step 3: RT sysctl (persists across reboots) ==="
cat > /etc/sysctl.d/99-rt.conf << EOF
kernel.sched_rt_runtime_us = -1
EOF
sysctl -p /etc/sysctl.d/99-rt.conf
echo "  RT throttle disabled (kernel.sched_rt_runtime_us = -1)"

echo "=== Step 4: Enable and start services ==="
systemctl daemon-reload
systemctl enable --now cpu-governor.service
systemctl enable cage_controller.service
echo "  Services enabled. cage_controller will start on next boot (or: sudo systemctl start cage_controller.service)"

echo "=== Step 5: Core isolation (requires reboot) ==="
CMDLINE=/boot/firmware/cmdline.txt
ISOLATE_ARGS="isolcpus=3 nohz_full=3 rcu_nocbs=3 irqaffinity=0-2"
if grep -q "isolcpus" "$CMDLINE"; then
    echo "  isolcpus already present in $CMDLINE — skipping"
else
    read -r -p "  Add '$ISOLATE_ARGS' to $CMDLINE and reboot? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        cp "$CMDLINE" "$CMDLINE.bak"
        sed -i "s/$/ $ISOLATE_ARGS/" "$CMDLINE"
        echo "  cmdline.txt updated (backup at $CMDLINE.bak)"
        echo "  Rebooting in 5 seconds — Ctrl+C to cancel"
        sleep 5
        reboot
    else
        echo "  Skipped. Add manually to $CMDLINE when ready, then reboot."
    fi
fi

echo "=== Step 6: Audio GPIO (ItsyBitsy DAC on PCB pins 9/10) ==="
# gpio= in config.txt runs before device tree overlays and can be overridden by
# them (e.g. the SPI overlay claims GPIO 9/10).  A systemd oneshot service that
# runs at sysinit.target — after the device tree is fully loaded but before
# cage_controller — is the reliable alternative.
SERVICE_FILE=/etc/systemd/system/audio-gpio-lock.service
if [[ -f "$SERVICE_FILE" ]]; then
    echo "  audio-gpio-lock.service already installed — skipping"
else
    cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=Lock GPIO 9/10 as pull-free inputs for ItsyBitsy DAC audio path
DefaultDependencies=no
Before=cage_controller.service
After=sysinit.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/pinctrl set 9 ip
ExecStart=/usr/bin/pinctrl set 10 ip

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now audio-gpio-lock.service
    echo "  audio-gpio-lock.service installed and enabled."
fi

echo ""
echo "=== Setup complete ==="
echo "Verify with:"
echo "  cat /proc/sys/kernel/sched_rt_runtime_us          # should be -1"
echo "  cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor  # should be performance"
echo "  sudo systemctl status cage_controller.service"
echo "  pinctrl get 9 10                                   # should show ip -- (input, no pull)"
