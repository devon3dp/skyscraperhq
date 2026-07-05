#!/usr/bin/env bash
PID=/vaults/nvme0/qsb_tower_v1/data/runtime/dashboard.pid
if [ -f "$PID" ]; then
  kill "$(cat "$PID")" 2>/dev/null || true
  rm -f "$PID"
fi
fuser -k 8765/tcp 2>/dev/null || true
echo "stopped"
