#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

PIDFILE="data/runtime/strategy_intelligence_sidecar.pid"
LOGFILE="data/logs/strategy_intelligence_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Strategy Intelligence sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/strategy_intelligence_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Strategy Intelligence sidecar started: PID $(cat "$PIDFILE")"
  echo "Status: http://127.0.0.1:8771/api/strategy/status"
else
  echo "FAILED to start Strategy Intelligence sidecar"
  tail -60 "$LOGFILE" || true
  exit 1
fi
