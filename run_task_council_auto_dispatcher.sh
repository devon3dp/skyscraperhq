#!/usr/bin/env bash
set -u
PROJECT="/vaults/nvme0/qsb_tower_v1"
SERVICE="$PROJECT/tools/qsb_task_council_auto_dispatcher.py"
LOG="$PROJECT/logs/task_council_auto_dispatcher.log"
PIDFILE="$PROJECT/runtime/task_council_auto_dispatcher.pid"

mkdir -p "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries"

cd "$PROJECT" || exit 1
ulimit -n 65535
export MALLOC_ARENA_MAX=2
export TASK_COUNCIL_INTERVAL="${TASK_COUNCIL_INTERVAL:-60}"
export TASK_COUNCIL_MAX_PER_CYCLE="${TASK_COUNCIL_MAX_PER_CYCLE:-2}"
export TASK_COUNCIL_DRY_RUN="${TASK_COUNCIL_DRY_RUN:-0}"

if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
    echo "[OK] already running pid=$OLD"
    exit 0
  fi
fi

nohup python3 -u "$SERVICE" >> "$LOG" 2>&1 &
PID="$!"
echo "$PID" > "$PIDFILE"
echo "[OK] Task Council Auto Dispatcher started pid=$PID"
echo "[OK] Log: $LOG"
