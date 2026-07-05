#!/usr/bin/env bash
# Log a moment I sounded sure but wasn't.
# Usage: qsb_claude_uncertainty_log.sh "<claim>" ["<confidence: low|medium|high>"] ["<why_i_sounded_sure>"] ["<what_would_have_helped>"]
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CLAIM="${1:?claim required}"
CONF="${2:-low}"
WHY="${3:-}"
HELP="${4:-}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.uncertainty_journal import UncertaintyJournal
e = UncertaintyJournal().log(${CLAIM@Q}, actual_confidence=${CONF@Q}, why_i_sounded_sure=${WHY@Q}, what_would_have_helped=${HELP@Q})
print("logged:", e["ts"])
PY
echo
echo "pattern summary:"
python3 -c "
import sys; sys.path.insert(0, '${ROOT}')
from src.tower.model_floors.claude_floor.uncertainty_journal import UncertaintyJournal
import json
print(json.dumps(UncertaintyJournal().pattern_summary(), indent=2))
"
