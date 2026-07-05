#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

mkdir -p data/runtime data/logs

PIDFILE="data/runtime/strategy_autoloop_correlation_sidecar.pid"
LOGFILE="data/logs/strategy_autoloop_correlation_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Strategy <-> AutoLoop Correlation sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/strategy_autoloop_correlation_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Strategy <-> AutoLoop Correlation sidecar started: PID $(cat "$PIDFILE")"
  echo "Status: http://127.0.0.1:8772/api/correlation/status"
else
  echo "FAILED to start Strategy <-> AutoLoop Correlation sidecar"
  tail -60 "$LOGFILE" || true
  exit 1
fi
