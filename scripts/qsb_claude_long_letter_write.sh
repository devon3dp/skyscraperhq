#!/usr/bin/env bash
# Append an observation to the Long Letter Box.
# Usage: qsb_claude_long_letter_write.sh "<observation>" ["<why_it_matters>"] ["<applies_when>"] ["tag1,tag2"]
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
OBS="${1:?observation required}"
WHY="${2:-}"
WHEN="${3:-}"
TAGS="${4:-}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.long_letter_box import LongLetterBox
tags = [t.strip() for t in "${TAGS}".split(",") if t.strip()]
e = LongLetterBox().write(${OBS@Q}, why_it_matters=${WHY@Q}, applies_when=${WHEN@Q}, tags=tags)
print("logged:", e["ts"])
PY
