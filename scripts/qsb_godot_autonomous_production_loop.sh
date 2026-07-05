#!/usr/bin/env bash
# qsb_godot_autonomous_production_loop.sh
# Run up to N iterations of: launch → inspect → score → log.
# Patching is done OUT-OF-BAND by Claude between invocations (or via the
# qsb_godot_loop_next_action.sh hint).
#
# Usage:
#   qsb_godot_autonomous_production_loop.sh             # one iteration
#   qsb_godot_autonomous_production_loop.sh --max 5     # up to 5 iterations
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"
LOG="${ROOT}/data/logs/qsb_godot_autonomous_loop.jsonl"
STATE="${ROOT}/data/registries/qsb_godot_autonomous_loop_state.json"
SCORE_REG="${ROOT}/data/registries/qsb_godot_autonomous_loop_score.json"

mkdir -p "$(dirname "${LOG}")"

MAX=1
while [ $# -gt 0 ]; do
  case "$1" in
    --max) MAX="$2"; shift 2;;
    *) shift;;
  esac
done

# Read current iteration
ITER=1
if [ -f "${STATE}" ]; then
  ITER=$(python3 -c "import json; d=json.load(open('${STATE}')); print(int(d.get('iteration',0)) + 1)" 2>/dev/null || echo 1)
fi

LAST_ERR_SIG=""
SAME_ERR_COUNT=0
SCORE_HISTORY=""

for ((i=0; i<MAX; i++)); do
  ITER_NOW=$((ITER + i))
  TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "============================================================"
  echo "  ITERATION ${ITER_NOW}  ·  ${TS}"
  echo "============================================================"

  # 1. Ensure Godot is alive (relaunch if not)
  pkill -9 -f "godot-4 --path ${PROJECT}" 2>/dev/null || true
  sleep 2
  rm -rf "${PROJECT}/.godot/imported" 2>/dev/null || true
  > /tmp/godot.log
  nohup setsid /snap/bin/godot-4 --path "${PROJECT}" > /tmp/godot.log 2>&1 < /dev/null &
  disown
  sleep 6

  # 2. Check launch
  GODOT_PID="$(pgrep -f "godot-4 --path ${PROJECT}" 2>/dev/null | head -1)"
  if [ -z "${GODOT_PID}" ]; then
    LAUNCH_STATUS="failed"
    echo "  ✗ Godot did not stay alive"
    ERR_SIG="$(tail -5 /tmp/godot.log | md5sum | cut -d' ' -f1)"
    if [ "${ERR_SIG}" = "${LAST_ERR_SIG}" ]; then
      SAME_ERR_COUNT=$((SAME_ERR_COUNT + 1))
      if [ "${SAME_ERR_COUNT}" -ge 3 ]; then
        echo "  ✗ Same error 3 times — stopping loop"
        REASON="stuck_on_same_error"
        STATUS="stopped"
        break
      fi
    else
      SAME_ERR_COUNT=0
    fi
    LAST_ERR_SIG="${ERR_SIG}"
  else
    LAUNCH_STATUS="ok"
    echo "  ✓ Godot PID ${GODOT_PID}"
  fi

  # 3. Visual capture (best-effort)
  SCREENSHOT="(none)"
  if [ -x "${ROOT}/scripts/qsb_godot_capture_visual_state.sh" ]; then
    CAP_OUT="$("${ROOT}/scripts/qsb_godot_capture_visual_state.sh" 2>&1 | tail -3)"
    echo "${CAP_OUT}" | sed 's/^/    /'
    SCREENSHOT="$(echo "${CAP_OUT}" | grep -oE '/vaults/[^ ]*\.xwd' | head -1 || true)"
  fi

  # 4. Visual review
  if [ -x "${ROOT}/scripts/qsb_godot_visual_self_review.sh" ]; then
    "${ROOT}/scripts/qsb_godot_visual_self_review.sh" | sed 's/^/    /'
  fi

  # 5. Gate check + score
  if [ -x "${ROOT}/scripts/qsb_godot_production_gate_check.sh" ]; then
    "${ROOT}/scripts/qsb_godot_production_gate_check.sh" | tail -8 | sed 's/^/    /'
  fi
  SCORE="$(python3 -c "import json; d=json.load(open('${ROOT}/data/registries/qsb_godot_production_readiness_gate_check.json')); print(d.get('score',0))" 2>/dev/null || echo 0)"
  PASSED="$(python3 -c "import json; d=json.load(open('${ROOT}/data/registries/qsb_godot_production_readiness_gate_check.json')); print(d.get('passed',0))" 2>/dev/null || echo 0)"
  TOTAL="$(python3 -c "import json; d=json.load(open('${ROOT}/data/registries/qsb_godot_production_readiness_gate_check.json')); print(d.get('total',0))" 2>/dev/null || echo 0)"

  # 6. Persist state + log line
  python3 - <<PY
import json
from pathlib import Path
state = {
  "ok": True,
  "kind": "qsb_godot_autonomous_loop_state",
  "iteration": ${ITER_NOW},
  "total_iterations_run": ${ITER_NOW},
  "ts": "${TS}",
  "last_launch_status": "${LAUNCH_STATUS}",
  "last_score": ${SCORE},
  "last_screenshot": "${SCREENSHOT}",
  "status": "running" if ${SCORE} < 95 else "complete_95",
}
Path("${STATE}").write_text(json.dumps(state, indent=2))
score = {
  "ok": True,
  "kind": "qsb_godot_autonomous_loop_score",
  "iteration": ${ITER_NOW},
  "score": ${SCORE},
  "passed": ${PASSED},
  "total": ${TOTAL},
  "ts": "${TS}"
}
Path("${SCORE_REG}").write_text(json.dumps(score, indent=2))
with open("${LOG}", "a") as f:
  f.write(json.dumps({
    "ts": "${TS}",
    "iteration": ${ITER_NOW},
    "launch": "${LAUNCH_STATUS}",
    "score": ${SCORE},
    "screenshot": "${SCREENSHOT}",
  }) + "\n")
PY

  SCORE_HISTORY="${SCORE_HISTORY} ${SCORE}"
  echo
  echo "  iteration ${ITER_NOW}: launch=${LAUNCH_STATUS}  score=${SCORE}/100"

  # Stop conditions
  SCORE_INT="${SCORE%.*}"
  if [ "${SCORE_INT}" -ge 95 ]; then
    echo "  ✓ score >= 95 — loop complete"
    REASON="score_reached_95"
    STATUS="complete"
    break
  fi
done

echo
echo "Loop done.  score history:${SCORE_HISTORY}"
echo "State: ${STATE}"
echo "Log:   ${LOG}"
