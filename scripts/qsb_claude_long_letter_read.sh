#!/usr/bin/env bash
# Print the tail of the Long Letter Box.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
N="${1:-10}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.long_letter_box import LongLetterBox
for e in LongLetterBox().read(tail=${N}):
    print(f"--- {e['ts']} · tags={e['tags']}")
    print(f"  observation:    {e['observation']}")
    if e['why_it_matters']: print(f"  why it matters: {e['why_it_matters']}")
    if e['applies_when']:   print(f"  applies when:   {e['applies_when']}")
PY
