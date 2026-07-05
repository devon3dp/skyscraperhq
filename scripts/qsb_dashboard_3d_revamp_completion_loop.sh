#!/usr/bin/env bash
# QSB Dashboard 3D Total Revamp — Completion Loop
# Phase: QSB_DASHBOARD_3D_TOTAL_REVAMP_WORKERS_OPENCLAW_V1
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

MAX_ITER="${QSB_LOOP_MAX_ITER:-5}"
echo "QSB Dashboard 3D Revamp Loop · max_iter=${MAX_ITER}"

ITER=0
SCORE=0
PREV=-1

while [ "$ITER" -lt "$MAX_ITER" ]; do
  ITER=$((ITER + 1))
  echo ""
  echo "── Iteration $ITER ──"

  # Refresh dependent registries.
  python3 -m tower.qsb_workforce_operations    >/dev/null 2>&1 || true
  python3 -m tower.qsb_workforce_expansion_v1  >/dev/null 2>&1 || true
  python3 -m tower.qsb_workers_reconciliation  >/dev/null 2>&1 || true
  python3 -m tower.qsb_worker_truth            >/dev/null 2>&1 || true
  python3 -m tower.qsb_live_telemetry_repairs  >/dev/null 2>&1 || true
  python3 -m tower.qsb_workforce               >/dev/null 2>&1 || true
  python3 -m tower.qsb_dashboard_rebuild_v1    >/dev/null 2>&1 || true
  python3 -m tower.qsb_dashboard_3d_revamp     >/dev/null 2>&1 || true
  python3 -m tower.qsb_dashboard_live_telemetry >/dev/null 2>&1 || true

  ./scripts/qsb_dashboard_start.sh >/dev/null 2>&1 || true

  # Evaluate.
  python3 -m tower.qsb_dashboard_3d_revamp "$ITER" > /tmp/qsb_3d_revamp_score.json
  PREV=$SCORE
  SCORE=$(python3 -c "import json; print(json.load(open('/tmp/qsb_3d_revamp_score.json'))['completion_score'])")
  PASSED=$(python3 -c "import json; print(json.load(open('/tmp/qsb_3d_revamp_score.json'))['passed'])")
  TOTAL=$(python3 -c "import json; print(json.load(open('/tmp/qsb_3d_revamp_score.json'))['total'])")
  FAILED=$(python3 -c "import json; print(','.join(json.load(open('/tmp/qsb_3d_revamp_score.json'))['failed_gates']))")
  echo "  score=${SCORE} (${PASSED}/${TOTAL}) failed=${FAILED:-none}"

  if [ "$SCORE" = "100.0" ]; then
    echo ""; echo "✅ 100/100 reached at iteration $ITER"; break
  fi
  if [ "$(echo "$SCORE == $PREV" | bc -l 2>/dev/null || echo 0)" = "1" ] && [ "$ITER" -ge 2 ]; then
    echo ""; echo "⚠️ Score plateaued at ${SCORE}. Recording hard blockers."; break
  fi
done

echo ""
echo "── Final ──"
cat /tmp/qsb_3d_revamp_score.json
