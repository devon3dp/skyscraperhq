#!/usr/bin/env bash
# Start the QSB Receptionist Dashboard V1 on :8856 (no Pico dependency).
# Usage: scripts/start_receptionist_dash.sh   (foreground)
#        nohup scripts/start_receptionist_dash.sh >/tmp/qsb_receptionist.log 2>&1 &  (background)
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
exec python3 tools/qsb_receptionist_dash.py
