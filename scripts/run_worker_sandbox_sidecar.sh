#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

PIDFILE="data/runtime/worker_sandbox_sidecar.pid"
LOGFILE="data/logs/worker_sandbox_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Worker Sandbox sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/worker_sandbox_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

echo "Worker Sandbox sidecar started: PID $(cat "$PIDFILE")"
echo "Status: http://127.0.0.1:8768/api/worker_sandbox/status"
