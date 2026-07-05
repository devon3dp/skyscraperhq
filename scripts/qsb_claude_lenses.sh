#!/usr/bin/env bash
# F47 self-observation lenses — render the current posture of all five.
# Usage:
#   qsb_claude_lenses.sh                # all five summaries, human-readable
#   qsb_claude_lenses.sh json           # all five summaries, raw JSON
#   qsb_claude_lenses.sh drift          # just the drift lens
#   qsb_claude_lenses.sh compliance     # just the compliance lens
#   qsb_claude_lenses.sh source         # just the source-of-claim lens
#   qsb_claude_lenses.sh ross           # just the ross lens
#   qsb_claude_lenses.sh stale          # just the stale-memory lens
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-all}"

case "${CMD}" in
  all)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.lenses import render_lens_summaries
print(render_lens_summaries())
PY
    ;;
  json)
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.lenses import all_lens_summaries
print(json.dumps(all_lens_summaries(), indent=2, default=str))
PY
    ;;
  drift)
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.lenses import DriftLens
s = DriftLens().summary()
print(json.dumps(s, indent=2, default=str))
PY
    ;;
  compliance)
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.lenses import ComplianceLens
s = ComplianceLens().summary()
print(json.dumps(s, indent=2, default=str))
PY
    ;;
  source)
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.lenses import SourceOfClaimLens
s = SourceOfClaimLens().summary()
print(json.dumps(s, indent=2, default=str))
PY
    ;;
  ross)
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.lenses import RossLens
s = RossLens().summary()
print(json.dumps(s, indent=2, default=str))
PY
    ;;
  stale)
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.lenses import StaleMemoryLens
s = StaleMemoryLens().summary()
print(json.dumps(s, indent=2, default=str))
PY
    ;;
  *)
    echo "usage: qsb_claude_lenses.sh [all|json|drift|compliance|source|ross|stale]"
    exit 1
    ;;
esac
