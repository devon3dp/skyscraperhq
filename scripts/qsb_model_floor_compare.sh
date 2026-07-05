#!/usr/bin/env bash
# qsb_model_floor_compare.sh — ask same prompt across the three, side-by-side.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
MSG="${1:-Compare your strengths in 2 lines.}"
OUT="${ROOT}/data/registries/qsb_model_floor_compare_latest.json"
mkdir -p "$(dirname "${OUT}")"
python3 - <<PY > "${OUT}"
import json, datetime, sys
sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.model_floor_router import ModelFloorRouter
r = ModelFloorRouter()
prompt = ${MSG@Q}
results = {t: r.route(t, prompt) for t in ("claude","gpt","deepseek")}
out = {
  "ok": True,
  "kind": "qsb_model_floor_compare_latest",
  "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
  "prompt_length": len(prompt),
  "results": results,
}
print(json.dumps(out, indent=2))
PY
echo
echo "compare written → ${OUT}"
