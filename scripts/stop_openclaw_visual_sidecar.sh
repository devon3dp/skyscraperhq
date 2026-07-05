#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/openclaw_visual_sidecar.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

echo "OpenClaw Visual sidecar stopped."
