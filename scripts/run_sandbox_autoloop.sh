#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

INTERVAL="${1:-30}"
INSTRUMENTS="${2:-EUR_USD,GBP_USD,USD_JPY}"
KERNEL_EVERY="${3:-5}"

PIDFILE="data/runtime/sandbox_autoloop.pid"
LOGFILE="data/logs/sandbox_autoloop.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Sandbox AutoLoop already running: PID $(cat "$PIDFILE")"
  exit 0
fi

python3 src/tower/sandbox_autoloop.py clear-stop >/dev/null

nohup python3 src/tower/sandbox_autoloop.py loop \
  --interval "$INTERVAL" \
  --instruments "$INSTRUMENTS" \
  --kernel-every "$KERNEL_EVERY" \
  > "$LOGFILE" 2>&1 &

echo $! > "$PIDFILE"
sleep 1

echo "Sandbox AutoLoop started: PID $(cat "$PIDFILE")"
echo "Interval seconds: $INTERVAL"
echo "Instruments: $INSTRUMENTS"
echo "Kernel commentary every N ticks: $KERNEL_EVERY"
echo "Log: $LOGFILE"
