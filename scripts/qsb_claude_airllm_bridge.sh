#!/usr/bin/env bash
# qsb_claude_airllm_bridge.sh — read F23's published state from F47 via the
# building's sealed-packet pattern. Never touches /vaults/ai/airllm_lab/.venv.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-status}"
case "${CMD}" in
  status)
    python3 - <<PY
import json, sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.airllm_bridge import status
print(json.dumps(status(), indent=2))
PY
    ;;
  knock)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.airllm_bridge import proper_form_address
print(proper_form_address())
PY
    ;;
  observe)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.airllm_bridge import status
print(status()["what_f47_observes"])
PY
    ;;
  *) echo "usage: qsb_claude_airllm_bridge.sh status|knock|observe"; exit 1;;
esac
