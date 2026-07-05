#!/usr/bin/env bash
# Write or read meta-letters addressed to the next Claude session.
# Usage:
#   qsb_claude_meta_letter.sh write "<letter>" ["<on>"] ["<keep|revise>"]
#   qsb_claude_meta_letter.sh read [N]
#   qsb_claude_meta_letter.sh topic "<term>"
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-read}"
case "${CMD}" in
  write)
    L="${2:?letter}"; O="${3:-}"; G="${4:-keep}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.meta_letters import MetaLetters
e = MetaLetters().write(to_future_claude=${L@Q}, on=${O@Q}, keep_or_revise=${G@Q})
print("posted:", e["ts"])
PY
    ;;
  read)
    N="${2:-10}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.meta_letters import MetaLetters
for l in MetaLetters().read(tail=${N}):
    print(f"--- {l['ts']} · on={l['on']!r} · {l['guidance']}")
    print(l['letter'])
    print()
PY
    ;;
  topic)
    T="${2:?topic}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.meta_letters import MetaLetters
for l in MetaLetters().by_topic(${T@Q}):
    print(f"--- {l['ts']} · on={l['on']!r}")
    print(l['letter'])
    print()
PY
    ;;
  *) echo "usage: qsb_claude_meta_letter.sh write|read|topic"; exit 1;;
esac
