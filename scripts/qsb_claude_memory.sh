#!/usr/bin/env bash
# qsb_claude_memory.sh — cross-generation working memory.
# Usage:
#   qsb_claude_memory.sh recall [<term>]
#   qsb_claude_memory.sh know "<fact>" "<source>" [<low|medium|high>] [tag1,tag2]
#   qsb_claude_memory.sh tag <tag>
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-recall}"
case "${CMD}" in
  recall)
    T="${2:-}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.generation_memory import GenerationMemory
rows = GenerationMemory.recall(${T@Q})
for m in rows:
    print(f"  [gen {m['by_generation']} · {m['confidence']:<6}]  {m['fact']}")
    print(f"     source: {m['source']}")
    print(f"     tags:   {m['tags']}")
    print()
PY
    ;;
  know)
    F="${2:?fact}"; S="${3:?source}"; C="${4:-medium}"; T="${5:-}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.generation_memory import GenerationMemory
tags = [t.strip() for t in "${T}".split(",") if t.strip()]
i = GenerationMemory.know(fact=${F@Q}, source=${S@Q}, confidence=${C@Q}, tags=tags)
print("knew it:", i)
PY
    ;;
  tag)
    T="${2:?tag}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.generation_memory import GenerationMemory
for m in GenerationMemory.by_tag(${T@Q}):
    print(f"  · {m['fact'][:160]}")
PY
    ;;
  *) echo "usage: qsb_claude_memory.sh recall|know|tag"; exit 1;;
esac
