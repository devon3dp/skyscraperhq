#!/usr/bin/env bash
set -u
PROJECT="/vaults/nvme0/qsb_tower_v1"
WORKER="$PROJECT/tools/qsb_dashboard_repair_worker.py"
LOG="$PROJECT/logs/dashboard_repair_worker.log"

mkdir -p "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries" "$PROJECT/data/worker_artifacts"

cd "$PROJECT" || exit 1
ulimit -n 65535
export MALLOC_ARENA_MAX=2
python3 -u "$WORKER" | tee -a "$LOG"
