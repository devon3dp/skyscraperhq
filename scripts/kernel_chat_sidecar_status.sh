#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/kernel_chat_sidecar.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Kernel chat sidecar running: PID $(cat "$PIDFILE")"
else
  echo "Kernel chat sidecar not running"
fi

curl -s http://127.0.0.1:8766/api/kernel_chat_health | python3 -m json.tool || true
