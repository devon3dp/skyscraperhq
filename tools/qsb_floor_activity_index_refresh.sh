#!/usr/bin/env bash
# qsb_floor_activity_index_refresh.sh — regenerate the honest per-floor activity index.
# STAGED, NOT installed. Ross: wire this to a systemd timer / cron only if you want it.
#
# One-shot:
#   bash tools/qsb_floor_activity_index_refresh.sh
#
# Loop (every 3 minutes) without systemd, if you want it ad-hoc:
#   while true; do bash tools/qsb_floor_activity_index_refresh.sh; sleep 180; done
#
# Suggested (NOT installed) systemd units for Ross to review:
#   /etc/systemd/system/qsb-floor-activity-index.service
#     [Service]
#     Type=oneshot
#     WorkingDirectory=/vaults/nvme0/qsb_tower_v1
#     ExecStart=/usr/bin/python3 tools/qsb_floor_activity_index.py
#   /etc/systemd/system/qsb-floor-activity-index.timer
#     [Timer]
#     OnBootSec=60
#     OnUnitActiveSec=180
#     [Install]
#     WantedBy=timers.target
set -euo pipefail
REPO="/vaults/nvme0/qsb_tower_v1"
cd "$REPO"
exec /usr/bin/python3 tools/qsb_floor_activity_index.py
