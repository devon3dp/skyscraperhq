#!/usr/bin/env bash
# Leave a soft observational note for the user in the Letter Drawer.
# Usage: qsb_claude_letter_write.sh "<note>" ["<tone: observation|nudge|thanks>"]
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
NOTE="${1:?note required}"
TONE="${2:-observation}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.letter_drawer import LetterDrawer
e = LetterDrawer().leave(${NOTE@Q}, tone=${TONE@Q})
print("left letter:", e["ts"])
PY
