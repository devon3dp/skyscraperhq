#!/usr/bin/env bash
# qsb_claude_cite_check.sh — cite-or-strike on a file (or stdin).
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
SRC="${1:--}"
if [ "${SRC}" = "-" ]; then
  TEXT="$(cat)"
else
  TEXT="$(cat "${SRC}")"
fi
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.cite_or_strike import render
print(render(${TEXT@Q}))
PY
