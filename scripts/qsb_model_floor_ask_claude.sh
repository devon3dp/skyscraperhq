#!/usr/bin/env bash
# qsb_model_floor_ask_claude.sh — advisory-only (no external call).
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
MSG="${1:-What did you build on your floor?}"
OUT="${ROOT}/data/registries/qsb_model_floor_last_response.json"
mkdir -p "$(dirname "${OUT}")"
python3 - <<PY > "${OUT}"
import json, datetime, sys
sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.model_floor_router import ModelFloorRouter
r = ModelFloorRouter()
res = r.route("claude", ${MSG@Q})
out = {
  "ok": True,
  "kind": "qsb_model_floor_last_response",
  "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
  "target": "claude",
  "response": res,
}
print(json.dumps(out, indent=2))
PY
python3 -c "import json; d=json.load(open('${OUT}')); print(d['response'].get('reply','(no reply)'))"
