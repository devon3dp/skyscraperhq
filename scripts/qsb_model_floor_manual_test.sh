#!/usr/bin/env bash
# qsb_model_floor_manual_test.sh — sanity-test the disabled paths.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.model_floor_router import ModelFloorRouter
r = ModelFloorRouter()
for target in ("claude","gpt","deepseek"):
    res = r.route(target, "Sanity test: are you scaffolded?")
    print(f"--- {target} ---")
    print(res.get("reply", res))
PY
