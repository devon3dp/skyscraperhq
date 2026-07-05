#!/usr/bin/env bash
# Run a snippet of Python in the Failure-Mode Lab subprocess sandbox.
# Usage:
#   qsb_claude_failure_mode_lab.sh "print('hello')"
#   qsb_claude_failure_mode_lab.sh - <<< "import json; print(json.dumps({'ok': True}))"
#   qsb_claude_failure_mode_lab.sh syntax-check path/to/file.py
#   qsb_claude_failure_mode_lab.sh can-import src.tower.model_floors.claude_floor
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"

if [ "${1:-}" = "syntax-check" ] && [ -n "${2:-}" ]; then
  python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.failure_mode_lab import FailureModeLab
print(json.dumps(FailureModeLab.syntax_check_file(${2@Q}), indent=2))
PY
  exit 0
fi
if [ "${1:-}" = "can-import" ] && [ -n "${2:-}" ]; then
  python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.failure_mode_lab import FailureModeLab
print(json.dumps(FailureModeLab.can_import(${2@Q}), indent=2))
PY
  exit 0
fi
CODE="${1:?code or 'syntax-check'/'can-import' required}"
if [ "${CODE}" = "-" ]; then CODE="$(cat)"; fi
python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.failure_mode_lab import FailureModeLab
print(json.dumps(FailureModeLab.run(${CODE@Q}), indent=2))
PY
