#!/usr/bin/env bash
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/data/registries/qsb_model_floors_provider_health_smoke_test_latest.json"
# Re-run reporter so status is fresh
cd "${ROOT}"
python3 -m src.tower.model_floors.model_floor_reporter >/dev/null 2>&1
python3 - <<PY > "${OUT}"
import json, datetime, sys
sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.model_floor_router import ModelFloorRouter
r = ModelFloorRouter()
fails = []
for name, adapter in (("claude", r.claude), ("gpt", r.gpt), ("deepseek", r.deepseek)):
    h = adapter.health()
    if not isinstance(h, dict) or "ok" not in h: fails.append(f"{name}: bad health shape")
    # External calls must be FALSE for gpt/deepseek by default
    s = adapter.status()
    if name in ("gpt","deepseek") and s.external_calls_allowed:
        fails.append(f"{name}: external_calls_allowed should be false by default")
    if name == "claude" and not s.enabled:
        fails.append("claude: should be enabled (local advisory)")
print(json.dumps({"ok": len(fails)==0, "kind":"qsb_model_floors_provider_health_smoke_test_latest", "ts": datetime.datetime.utcnow().isoformat(timespec='seconds')+'Z', "fails": fails}, indent=2))
PY
cat "${OUT}"
[ "$(jq -r .ok "${OUT}")" = "true" ] && exit 0 || exit 1
