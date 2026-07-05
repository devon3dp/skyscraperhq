#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

PIDFILE="data/runtime/oanda_floor41_sidecar.pid"
LOGFILE="data/logs/oanda_floor41_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Floor 41 OANDA sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/oanda_floor41_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

echo "Floor 41 OANDA sidecar started: PID $(cat "$PIDFILE")"
echo "Status: http://127.0.0.1:8767/api/floor41/status"
