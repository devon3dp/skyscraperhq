#!/usr/bin/env bash
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/data/registries/qsb_model_floors_env_smoke_test_latest.json"
TEMPLATE="${ROOT}/config/model_floors/.env.model_floors.template"
README="${ROOT}/config/model_floors/README_MODEL_FLOOR_KEYS.md"
fail=0
[ -f "${TEMPLATE}" ] || fail=$((fail+1))
[ -f "${README}" ] || fail=$((fail+1))
# Template must NOT contain a real-looking key value (just empty)
if grep -E '^QSB_OPENAI_API_KEY=.+$|^QSB_DEEPSEEK_API_KEY=.+$' "${TEMPLATE}" 2>/dev/null | grep -v '^[A-Z_]*=$' | head -1 | grep -q .; then
  fail=$((fail+1))
fi
# Key presence detection works without printing keys
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.provider_env import ProviderEnv
# Simulate presence without printing the value
print("presence detection ok:", ProviderEnv.get_presence("QSB_OPENAI_API_KEY","OPENAI_API_KEY"))
PY
cat > "${OUT}" <<EOF
{"ok": $([ ${fail} -eq 0 ] && echo true || echo false), "kind":"qsb_model_floors_env_smoke_test_latest","ts":"${TS}","fail":${fail}}
EOF
cat "${OUT}"
[ ${fail} -eq 0 ] && exit 0 || exit 1
