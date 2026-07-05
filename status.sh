#!/usr/bin/env bash
PID=/vaults/nvme0/qsb_tower_v1/data/runtime/dashboard.pid
if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then echo "Dashboard running: http://127.0.0.1:8765"; else echo "Dashboard stopped"; fi
echo "Project: /vaults/nvme0/qsb_tower_v1"
find /vaults/nvme0/qsb_tower_v1 -maxdepth 2 -type d | sort | head -80
