#!/usr/bin/env bash
# qsb_model_floor_status.sh — prints presence-only provider status. NEVER prints full keys.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
# Always re-run the reporter so the status registries are fresh.
python3 -m src.tower.model_floors.model_floor_reporter >/dev/null 2>&1 || true
echo "============================================================"
echo "  QSB · Three Model Embassy Floors · status"
echo "============================================================"
python3 - <<'PY'
import json, os
ROOT = "/vaults/nvme0/qsb_tower_v1"
p = os.path.join(ROOT, "data/registries/qsb_model_floor_provider_status.json")
with open(p) as f:
    d = json.load(f)
for key in ("claude","gpt","deepseek"):
    s = d["providers"].get(key, {})
    print(f"  {key:9} · {s.get('floor_id')} · {s.get('provider_name')}")
    print(f"    enabled:                {s.get('enabled')}")
    print(f"    env_key_present:        {s.get('env_key_present')}")
    print(f"    external_calls_allowed: {s.get('external_calls_allowed')}")
    print(f"    model_name:             {s.get('model_name')}")
    print(f"    masked_key:             {s.get('masked_key')}")
cg = d["providers"].get("cost_guard_snapshot", {})
print()
print(f"  cost guard ·")
print(f"    max_requests_per_session: {cg.get('max_requests_per_session')}")
print(f"    max_tokens_per_request:   {cg.get('max_tokens_per_request')}")
print(f"    external_calls_enabled_global: {cg.get('external_calls_enabled_global')}")
PY
