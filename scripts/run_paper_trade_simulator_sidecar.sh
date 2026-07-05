#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

mkdir -p data/runtime data/logs

PIDFILE="data/runtime/paper_trade_simulator_sidecar.pid"
LOGFILE="data/logs/paper_trade_simulator_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Paper Trade Simulator sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/paper_trade_simulator_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Paper Trade Simulator sidecar started: PID $(cat "$PIDFILE")"
  echo "Status: http://127.0.0.1:8774/api/paper_trades/status"
else
  echo "FAILED to start Paper Trade Simulator sidecar"
  tail -60 "$LOGFILE" || true
  exit 1
fi
