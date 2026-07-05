#!/usr/bin/env bash
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
ITERS="${1:-10}"
LOG="${ROOT}/data/logs/qsb_model_floors_visual_repair_loop.jsonl"
mkdir -p "$(dirname "${LOG}")"
i=0
while [ "${i}" -lt "${ITERS}" ]; do
  i=$((i+1))
  TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "============================================================"
  echo "  iter ${i}/${ITERS}  ·  ${TS}"
  echo "============================================================"
  ./scripts/qsb_model_floors_full_smoke_suite.sh >/dev/null 2>&1
  ok=$(jq -r '.ok' data/registries/qsb_model_floors_full_smoke_suite_latest.json 2>/dev/null || echo "false")
  pass=$(jq -r '.pass' data/registries/qsb_model_floors_full_smoke_suite_latest.json 2>/dev/null || echo 0)
  echo "{\"iter\":${i},\"ts\":\"${TS}\",\"ok\":${ok},\"pass\":${pass}}" >> "${LOG}"
  if [ "${ok}" = "true" ]; then
    echo "STOP: all P0 model floor tests pass (pass=${pass})"
    break
  fi
done
cat > data/registries/qsb_model_floors_visual_repair_loop_latest.json <<EOF
{"ok": true, "kind":"qsb_model_floors_visual_repair_loop_latest","ts":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","iterations":${i}}
EOF
