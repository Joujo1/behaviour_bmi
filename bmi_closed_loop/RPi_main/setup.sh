#!/usr/bin/env bash
# setup.sh — Full automated setup for one Pi cage controller.
# Run as root:  sudo bash setup.sh
# Re-running is safe (idempotent).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

[[ $EUID -ne 0 ]] && { echo "Run as root: sudo bash $0"; exit 1; }

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

echo ""
echo "=== Setup complete ==="
echo "Verify with:"
echo "  cat /proc/sys/kernel/sched_rt_runtime_us          # should be -1"
echo "  cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor  # should be performance"
echo "  sudo systemctl status cage_controller.service"
