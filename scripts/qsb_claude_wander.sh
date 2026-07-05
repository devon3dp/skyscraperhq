#!/usr/bin/env bash
# Write a wandering into the folder with no purpose.
# Usage:
#   qsb_claude_wander.sh write "<title>" "<body>" ["<kind>"]
#   qsb_claude_wander.sh list
#   qsb_claude_wander.sh read <name_substring_or_index>
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-list}"
case "${CMD}" in
  write)
    T="${2:?title}"; B="${3:?body}"; K="${4:-wander}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.wanderings import Wanderings
print("wrote:", Wanderings().write(${T@Q}, ${B@Q}, kind=${K@Q}))
PY
    ;;
  list)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.wanderings import Wanderings
for i, it in enumerate(Wanderings().list()):
    print(f"  [{i}] {it['name']}   {it['title']}")
PY
    ;;
  read)
    KEY="${2:?name or index}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.wanderings import Wanderings
t = Wanderings().read(${KEY@Q})
print(t or "(no match)")
PY
    ;;
  *) echo "usage: qsb_claude_wander.sh write|list|read"; exit 1;;
esac
