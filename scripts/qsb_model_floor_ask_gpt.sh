#!/usr/bin/env bash
# qsb_model_floor_ask_gpt.sh — scaffold path; never issues a real call here.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
MSG="${1:-Smoke test prompt}"
OUT="${ROOT}/data/registries/qsb_model_floor_last_response.json"
mkdir -p "$(dirname "${OUT}")"
LOG="${ROOT}/data/logs/qsb_model_floor_requests.jsonl"
python3 - <<PY > "${OUT}"
import json, datetime, sys
sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.model_floor_router import ModelFloorRouter
from src.tower.model_floors.provider_base import ProviderBase
r = ModelFloorRouter()
res = r.route("gpt", ${MSG@Q})
out = {
  "ok": True,
  "kind": "qsb_model_floor_last_response",
  "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
  "target": "gpt",
  "response": res,
  "prompt_length": len(${MSG@Q}),
  "external_call_made": False,
}
print(json.dumps(out, indent=2))
PY
# Append metadata-only line (no payload body) to request log
python3 -c "
import json, datetime
ts = datetime.datetime.utcnow().isoformat(timespec='seconds') + 'Z'
with open('${LOG}', 'a') as f:
    f.write(json.dumps({'ts': ts, 'target': 'gpt', 'prompt_length': len('''${MSG}'''), 'external_call_made': False}) + chr(10))
"
cat "${OUT}"
