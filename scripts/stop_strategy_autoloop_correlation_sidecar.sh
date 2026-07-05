#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/strategy_autoloop_correlation_sidecar.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" || true)"
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

PIDS="$(lsof -ti tcp:8772 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
  kill $PIDS || true
fi

echo "Strategy <-> AutoLoop Correlation sidecar stopped."
