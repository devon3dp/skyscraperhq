#!/usr/bin/env bash
# Given a question, print up to 3 clarifying questions I should ask first.
# Usage: qsb_claude_before_answer.sh "<question>"
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
Q="${1:?question required}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.before_answering_protocol import BeforeAnsweringProtocol
qs = BeforeAnsweringProtocol.clarifying_questions(${Q@Q})
print("Before answering, I should ask:")
for i, q in enumerate(qs, 1):
    print(f"  {i}. {q}")
PY
