#!/usr/bin/env bash
# Render the ASCII tower garden (or a small haiku over current state).
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
MODE="${1:-render}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.tower_garden import render, haiku
mode = ${MODE@Q}
if mode == "haiku":
    print(haiku())
else:
    print(render(width=86))
PY
