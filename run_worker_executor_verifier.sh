#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
WORKER="$PROJECT/tools/qsb_worker_executor_verifier.py"
LOG="$PROJECT/logs/worker_executor_verifier.log"
PIDFILE="$PROJECT/runtime/worker_executor_verifier.pid"

mkdir -p "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries" "$PROJECT/data/worker_artifacts"

cd "$PROJECT" || exit 1
ulimit -n 65535
export MALLOC_ARENA_MAX=2
export WORKER_EXECUTOR_INTERVAL="${WORKER_EXECUTOR_INTERVAL:-60}"
export WORKER_EXECUTOR_MAX_PER_CYCLE="${WORKER_EXECUTOR_MAX_PER_CYCLE:-1}"
export WORKER_EXECUTOR_DRY_RUN="${WORKER_EXECUTOR_DRY_RUN:-0}"

if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
    echo "[OK] already running pid=$OLD"
    exit 0
  fi
fi

nohup python3 -u "$WORKER" >> "$LOG" 2>&1 &
PID="$!"
echo "$PID" > "$PIDFILE"
echo "[OK] Worker Executor + Verifier started pid=$PID"
echo "[OK] Log: $LOG"
