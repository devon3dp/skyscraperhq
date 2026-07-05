#!/usr/bin/env bash
# qsb_model_floor_health_check.sh — emits per-provider health.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
OUT="${ROOT}/data/registries/qsb_model_floor_health_status.json"
mkdir -p "$(dirname "${OUT}")"
python3 - <<PY > "${OUT}"
import json, datetime
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.model_floor_router import ModelFloorRouter
r = ModelFloorRouter()
out = {
  "ok": True,
  "kind": "qsb_model_floor_health_status",
  "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
  "claude":   r.claude.health(),
  "gpt":      r.gpt.health(),
  "deepseek": r.deepseek.health(),
}
print(json.dumps(out, indent=2))
PY
cat "${OUT}"
