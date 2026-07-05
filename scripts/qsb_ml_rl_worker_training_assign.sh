#!/usr/bin/env bash
# QSB ML/RL integration · worker_training
# Phase: QSB_ML_RL_LAB_CLASSROOM_RESEARCH_WORKER_INTEGRATION_V1
# Idempotent. Does not install packages. Does not enable execution.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh 2>/dev/null || true
ts=$(date -u +%FT%TZ)
LOG=data/logs/qsb_ml_rl_worker_training_assign.log
mkdir -p data/logs
echo "[$ts] worker_training · verifying registries" | tee -a "$LOG"
ok=0; fail=0
for r in qsb_worker_ml_rl_training_roster.json qsb_worker_learning_assignments.json qsb_worker_skill_matrix.json qsb_worker_certification_status.json; do
  if [ -f data/registries/$r ]; then echo "  ✓ $r" | tee -a "$LOG"; ok=$((ok+1))
  else echo "  ✗ $r MISSING" | tee -a "$LOG"; fail=$((fail+1)); fi
done
# Append OpenClaw supervision event for this script run (audit trail)
echo "{\"ts\":\"$ts\",\"event\":\"worker_training\",\"ok_count\":$ok,\"fail_count\":$fail,\"execution_allowed\":false}" >> data/logs/qsb_openclaw_ml_rl_supervision.jsonl
echo "ok=$ok fail=$fail · log=$LOG"
