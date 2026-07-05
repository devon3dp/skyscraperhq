#!/usr/bin/env bash
# QSB 100% Online Self-Correcting Build Loop
# Phase: QSB_SKYSCRAPER_100_PERCENT_ONLINE_INTERACTIVE_3D_WORKFORCE_COMPLETION_V1
#
# Bounded audit → repair → verify loop. Stops when score=100/100 or when
# a hard blocker is recorded with exact file/line/endpoint references.
#
# No real-money trading is enabled. No OpenClaw execution is enabled.
# Hardware/code observatory remain read-only.

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

MAX_ITER="${QSB_LOOP_MAX_ITER:-5}"
echo "QSB 100% Online Completion Loop · max_iterations=${MAX_ITER}"
echo "============================================================"

ITER=0
SCORE=0
PREV_SCORE=-1

while [ "$ITER" -lt "$MAX_ITER" ]; do
  ITER=$((ITER + 1))
  echo ""
  echo "── Iteration $ITER ──"

  # Step 1: refresh all sources that feed gates
  python3 -m tower.qsb_workforce_expansion_v1 >/dev/null 2>&1 || true
  python3 -m tower.qsb_workforce_operations    >/dev/null 2>&1 || true
  python3 -m tower.qsb_workers_reconciliation  >/dev/null 2>&1 || true
  python3 -m tower.qsb_workforce               >/dev/null 2>&1 || true
  python3 -m tower.qsb_profit_command          >/dev/null 2>&1 || true
  python3 -m tower.qsb_live_telemetry_repairs  >/dev/null 2>&1 || true
  python3 -m tower.qsb_worker_truth            >/dev/null 2>&1 || true
  python3 -m tower.eqsb_observatory all        >/dev/null 2>&1 || true
  python3 -m tower.qsb_dashboard_live_telemetry >/dev/null 2>&1 || true

  # Step 2: make sure dashboard is up
  ./scripts/qsb_dashboard_start.sh >/dev/null 2>&1 || true

  # Step 3: evaluate gates
  python3 -m tower.qsb_completion_engine "$ITER" > /tmp/qsb_score.json
  PREV_SCORE=$SCORE
  SCORE=$(python3 -c "import json; print(json.load(open('/tmp/qsb_score.json'))['completion_score'])")
  PASSED=$(python3 -c "import json; print(json.load(open('/tmp/qsb_score.json'))['passed'])")
  TOTAL=$(python3 -c "import json; print(json.load(open('/tmp/qsb_score.json'))['total'])")
  FAILED=$(python3 -c "import json; print(','.join(json.load(open('/tmp/qsb_score.json'))['failed_gates']))")
  echo "  score=${SCORE} (${PASSED}/${TOTAL}) failed=${FAILED:-none}"

  if [ "$SCORE" = "100.0" ]; then
    echo ""
    echo "✅ 100/100 reached at iteration $ITER"
    break
  fi

  # Stop if score didn't improve — hard blocker
  if [ "$(echo "$SCORE == $PREV_SCORE" | bc -l 2>/dev/null || echo 0)" = "1" ] && [ "$ITER" -ge 2 ]; then
    echo ""
    echo "⚠️  Score plateaued at ${SCORE}. Recording hard blockers."
    break
  fi
done

echo ""
echo "── Final ──"
cat /tmp/qsb_score.json
echo ""
echo "Loop history: data/registries/qsb_100_online_loop_history.json"
echo "Hard blockers: data/registries/qsb_100_online_hard_blockers.json"
echo "Score MD:      data/logs/qsb_100_online_completion_score.md"
