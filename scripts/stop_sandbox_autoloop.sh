#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/sandbox_autoloop.pid"

python3 src/tower/sandbox_autoloop.py request-stop >/dev/null 2>&1 || true
sleep 2

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

echo "Sandbox AutoLoop stopped."
./scripts/sandbox_autoloop_status.sh || true
