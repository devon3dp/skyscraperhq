#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

PIDFILE="data/runtime/kernel_chat_sidecar.pid"
LOGFILE="data/logs/kernel_chat_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Kernel chat sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/kernel_chat_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

sleep 1
echo "Kernel chat sidecar started: PID $(cat "$PIDFILE")"
echo "Health: http://127.0.0.1:8766/api/kernel_chat_health"
