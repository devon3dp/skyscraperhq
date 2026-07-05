#!/usr/bin/env bash
# Wandering procedural "dreams" — random log juxtapositions composed into ~120 words.
# Usage:
#   qsb_claude_dream.sh           # produce a dream now
#   qsb_claude_dream.sh latest    # show the most recent
#   qsb_claude_dream.sh list [N]  # list recent dream files
#   qsb_claude_dream.sh schedule  # PRINT (do not execute) the cron line you would add
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-now}"
case "${CMD}" in
  now|"")
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.dream_engine import DreamEngine
d = DreamEngine.dream()
print(f"--- {d['title']} ---")
print(d['body'])
print()
print(f"saved: {d['path']}")
PY
    ;;
  latest)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.dream_engine import DreamEngine
d = DreamEngine.latest()
print(d['body'] if d else "(no dreams yet — run with no arg first)")
PY
    ;;
  list)
    N="${2:-10}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.dream_engine import DreamEngine
for d in DreamEngine.list_dreams(tail=${N}):
    print(d['name'])
PY
    ;;
  schedule)
    echo "# Add ONE of these to your crontab to auto-generate dreams locally."
    echo "# Pure procedural generation — NO LLM cost, NO external network. Just sampling logs."
    echo ""
    echo "# Once per day at 04:00 local:"
    echo "0 4 * * * cd ${ROOT} && ./scripts/qsb_claude_dream.sh now >/dev/null 2>&1"
    echo ""
    echo "# Twice per day (04:00 + 16:00):"
    echo "0 4,16 * * * cd ${ROOT} && ./scripts/qsb_claude_dream.sh now >/dev/null 2>&1"
    echo ""
    echo "# To install: crontab -e  then paste one of the lines above."
    echo "# To disable: crontab -e  then delete the line."
    ;;
  *) echo "usage: qsb_claude_dream.sh now|latest|list|schedule"; exit 1;;
esac
