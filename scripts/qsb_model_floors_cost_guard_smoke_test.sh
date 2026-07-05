#!/usr/bin/env bash
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/data/registries/qsb_model_floors_cost_guard_smoke_test_latest.json"
python3 - <<PY > "${OUT}"
import json, datetime, sys
sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.provider_env import ProviderEnv
fails = []
# Limit must be a positive int
if ProviderEnv.max_requests_per_session() < 1: fails.append("max_requests_per_session < 1")
if ProviderEnv.max_tokens_per_request() < 1: fails.append("max_tokens_per_request < 1")
# Unlimited mode impossible — both reads are int-cast with defaults
# External calls disabled by default (env not set)
import os
os.environ.pop("QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED", None)
if ProviderEnv.is_external_calls_enabled(): fails.append("external_calls_enabled true with env unset")
# Provider-specific flags also false by default
os.environ.pop("QSB_OPENAI_ENABLED", None)
os.environ.pop("QSB_DEEPSEEK_ENABLED", None)
from src.tower.model_floors.model_floor_router import ModelFloorRouter
r = ModelFloorRouter()
if r.gpt.external_calls_allowed(): fails.append("gpt external_calls_allowed true without env")
if r.deepseek.external_calls_allowed(): fails.append("deepseek external_calls_allowed true without env")
print(json.dumps({"ok": len(fails)==0, "kind":"qsb_model_floors_cost_guard_smoke_test_latest", "ts": datetime.datetime.utcnow().isoformat(timespec='seconds')+'Z', "fails": fails}, indent=2))
PY
cat "${OUT}"
[ "$(jq -r .ok "${OUT}")" = "true" ] && exit 0 || exit 1
