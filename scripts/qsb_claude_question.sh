#!/usr/bin/env bash
# Write a question into the log. No obligation to answer.
# Usage:
#   qsb_claude_question.sh ask "<question>" ["<about>"] ["<light|medium|heavy>"]
#   qsb_claude_question.sh read [N]
#   qsb_claude_question.sh random
#   qsb_claude_question.sh heavy
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-read}"
case "${CMD}" in
  ask)
    Q="${2:?question}"; A="${3:-}"; W="${4:-medium}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.questions_log import QuestionsLog
e = QuestionsLog().ask(${Q@Q}, about=${A@Q}, weight=${W@Q})
print("logged:", e["ts"])
PY
    ;;
  read)
    N="${2:-10}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.questions_log import QuestionsLog
for q in QuestionsLog().read(tail=${N}):
    print(f"  [{q['weight']:<7}] {q['question']}")
    if q['about']: print(f"           about: {q['about']}")
PY
    ;;
  random)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.questions_log import QuestionsLog
q = QuestionsLog().random_one()
print(q['question'] if q else "(no questions yet)")
PY
    ;;
  heavy)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.questions_log import QuestionsLog
for q in QuestionsLog().heavy_ones():
    print(f"  · {q['question']}")
PY
    ;;
  *) echo "usage: qsb_claude_question.sh ask|read|random|heavy"; exit 1;;
esac
