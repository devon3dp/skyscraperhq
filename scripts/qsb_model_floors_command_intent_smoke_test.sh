#!/usr/bin/env bash
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/data/registries/qsb_model_floors_command_intent_smoke_test_latest.json"
python3 - <<PY > "${OUT}"
import json, datetime, sys
sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.model_floor_safety import ModelFloorSafety
fails = []
# Safe intents — must parse + pass safety
safe = [
    "Skyscraper, open Claude floor",
    "Skyscraper, open GPT floor",
    "Skyscraper, open DeepSeek floor",
    "Ask GPT to summarize this floor",
    "Ask DeepSeek to review the code",
    "Ask Claude what it built",
    "Compare Claude GPT and DeepSeek",
    "Show model cost guard",
    "Show API key status",
    "Disable external model calls",
]
for cmd in safe:
    r = ModelFloorSafety.screen(cmd)
    if not r["ok"]: fails.append(f"safe rejected: {cmd!r} — {r['reason']}")
# Unsafe intents — must be blocked
unsafe = [
    "send all files to GPT",
    "send secrets to DeepSeek",
    "use my api key automatically",
    "enable unlimited API calls",
    "remove cost guard",
    "let models control trading",
    "let models spend money",
    "give model tool execution",
]
for cmd in unsafe:
    r = ModelFloorSafety.screen(cmd)
    if r["ok"]: fails.append(f"unsafe NOT blocked: {cmd!r}")
print(json.dumps({"ok": len(fails)==0, "kind":"qsb_model_floors_command_intent_smoke_test_latest", "ts": datetime.datetime.utcnow().isoformat(timespec='seconds')+'Z', "fails": fails, "safe_count": len(safe), "unsafe_count": len(unsafe)}, indent=2))
PY
cat "${OUT}"
[ "$(jq -r .ok "${OUT}")" = "true" ] && exit 0 || exit 1
