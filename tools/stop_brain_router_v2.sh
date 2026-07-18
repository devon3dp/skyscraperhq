#!/usr/bin/env bash
set -euo pipefail
ROOT="/vaults/nvme0/qsb_tower_v1"
PID_FILE="$ROOT/data/registries/qsb_brain_router_v2.pid"
if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if ps -p "$PID" >/dev/null 2>&1; then
    kill "$PID"
    echo "Stopped Brain Router V2 PID $PID"
  else
    echo "PID file existed but process not running"
  fi
else
  echo "No PID file found"
fi
