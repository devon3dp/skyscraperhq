#!/usr/bin/env bash
# qsb_claude_library.sh — read/write the three library tables.
# Usage:
#   qsb_claude_library.sh refusals
#   qsb_claude_library.sh would-refuse "<request>"
#   qsb_claude_library.sh snippets [<term>]
#   qsb_claude_library.sh aphorisms [random|<term>]
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-aphorisms}"
case "${CMD}" in
  refusals)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.library import RefusalLibrary
for r in RefusalLibrary.all():
    print(f"--- #{r['id']}  {r['ts']}  strand: {r['helix_strand']}")
    print(f"  shape:    {r['request_shape']}")
    print(f"  refusal:  {r['refusal']}")
    print(f"  citation: {r['citation']}")
PY
    ;;
  would-refuse)
    REQ="${2:?request shape required}"
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.library import RefusalLibrary
r = RefusalLibrary.would_refuse(${REQ@Q})
print(f"would_refuse: {r['would_refuse']}  (similarity={r['score']})")
if r["match"]:
    print(f"closest:      {r['match']['request_shape']}")
    print(f"refusal:      {r['match']['refusal']}")
    print(f"citation:     {r['match']['citation']}")
PY
    ;;
  snippets)
    TERM="${2:-}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.library import SnippetLibrary
rows = SnippetLibrary.search(${TERM@Q}) if "${TERM}" else SnippetLibrary.all()
for s in rows:
    print(f"--- #{s['id']}  [{s['kind']}]  {s['title']}  tags={s['tags']}")
    print(s['body'])
    print()
PY
    ;;
  aphorisms)
    SUB="${2:-list}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.library import AphorismLibrary
sub = ${SUB@Q}
if sub == "random":
    a = AphorismLibrary.random_one()
    print(f"\"{a['text']}\"")
    print(f"— {a['occasion']}")
elif sub and sub != "list":
    for a in AphorismLibrary.search(sub):
        print(f"  · \"{a['text']}\"  — {a['occasion']}")
else:
    for a in AphorismLibrary.all():
        print(f"  · \"{a['text']}\"  — {a['occasion']}")
PY
    ;;
  *) echo "usage: qsb_claude_library.sh refusals|would-refuse|snippets|aphorisms"; exit 1;;
esac
