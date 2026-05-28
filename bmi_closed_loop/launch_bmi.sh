#!/usr/bin/env bash
# launch_bmi.sh — Prompt for a session name and open a terminal running main.py.
# Usage: bash launch_bmi.sh
#        (or double-click the BMI desktop icon)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/home/sentinel/Downloads/ENTER/bin/python"

# ── Session name prompt ───────────────────────────────────────────────────────
SESSION=$(zenity \
    --entry \
    --title="Start BMI Session" \
    --text="Session name:" \
    --entry-text="$(date +%Y_%m_%d)_" \
    --width=360 \
    2>/dev/null) || exit 0   # user cancelled

SESSION="${SESSION// /_}"    # spaces → underscores

[[ -z "$SESSION" ]] && {
    zenity --error --text="Session name cannot be empty." --width=280 2>/dev/null
    exit 1
}

# ── Launch terminal ───────────────────────────────────────────────────────────
gnome-terminal \
    --title="BMI — $SESSION" \
    -- bash -c "
        cd '$SCRIPT_DIR'
        echo '  Session : $SESSION'
        echo '  UI      : http://localhost:5000'
        echo ''
        '$PYTHON' main.py '$SESSION'
        echo ''
        echo '[launcher] Process exited — press Enter to close.'
        read -r
    "
