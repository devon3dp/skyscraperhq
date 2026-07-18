#!/usr/bin/env bash
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
for pidfile in "$ROOT/data/registries/qsb_asa_node.pid" "$ROOT/data/registries/qsb_task_council.pid"; do
  if [ -f "$pidfile" ]; then
    PID="$(cat "$pidfile")"
    if ps -p "$PID" >/dev/null 2>&1; then
      kill "$PID"
      echo "stopped pid $PID from $pidfile"
    else
      echo "pid not running: $PID"
    fi
  fi
done
