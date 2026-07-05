#!/usr/bin/env bash
# Check whether I am in 'just agreeing' mode over recent turns.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
N="${1:-20}"
python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.pushback_meter import PushbackMeter
print(json.dumps(PushbackMeter().streak_summary(tail=${N}), indent=2))
PY
