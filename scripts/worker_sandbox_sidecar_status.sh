#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/worker_sandbox_sidecar.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Worker Sandbox sidecar running: PID $(cat "$PIDFILE")"
else
  echo "Worker Sandbox sidecar not running"
fi

curl -s http://127.0.0.1:8768/api/worker_sandbox/status | python3 -m json.tool || true
