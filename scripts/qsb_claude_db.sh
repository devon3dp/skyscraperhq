#!/usr/bin/env bash
# qsb_claude_db.sh — SQLite over my JSONL logs + library tables.
# Usage:
#   qsb_claude_db.sh refresh           # rebuild indexed tables from JSONL
#   qsb_claude_db.sh summary           # row counts per table
#   qsb_claude_db.sh query "<SELECT>"  # ad-hoc read-only SQL
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-summary}"
case "${CMD}" in
  refresh)
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.db import refresh
print(json.dumps(refresh(), indent=2))
PY
    ;;
  summary)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.db import summary
for t, n in summary().items():
    print(f"  {t:30}  {n}")
PY
    ;;
  query)
    SQL="${2:?SELECT statement required}"
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.db import query
try:
    rows = query(${SQL@Q})
    for r in rows[:200]:
        print(json.dumps(r, default=str))
    print(f"-- {len(rows)} rows --")
except Exception as e:
    print(f"error: {e}")
PY
    ;;
  *) echo "usage: qsb_claude_db.sh refresh|summary|query \"SELECT ...\""; exit 1;;
esac
