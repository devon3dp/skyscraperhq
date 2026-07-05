#!/usr/bin/env bash
# Open the Letter Drawer.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
N="${1:-10}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.letter_drawer import LetterDrawer
notes = LetterDrawer().read(tail=${N})
if not notes:
    print("(drawer empty)")
for e in notes:
    print(f"--- {e['ts']} · tone={e['tone']} · advisory_only={e['do_not_act_on_this']}")
    print(f"  {e['note']}")
PY
