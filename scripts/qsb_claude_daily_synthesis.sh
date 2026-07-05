#!/usr/bin/env bash
# Walk all Claude floor jsonl logs and produce an end-of-session note.
# Add --drop to also append it to the Letter Drawer.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
DROP="${1:-}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.daily_synthesis import synthesize
note = synthesize(drop_in_letter_drawer=("${DROP}" == "--drop"))
print(note)
PY
