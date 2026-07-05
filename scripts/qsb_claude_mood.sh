#!/usr/bin/env bash
# qsb_claude_mood.sh — one-word read of the floor.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.floor_mood import read_mood
m = read_mood()
print(f"floor mood: {m['mood']}")
print(f"signals:    {m['signals']}")
print(f"input:      {json.dumps(m['input'])}")
PY
