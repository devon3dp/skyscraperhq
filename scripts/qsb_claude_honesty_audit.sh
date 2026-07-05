#!/usr/bin/env bash
# Audit a file for hedges / unsupported confidence / missing citations.
# Usage: qsb_claude_honesty_audit.sh <path>
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
P="${1:?path required}"
python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.honesty_audit import HonestyAudit
print(json.dumps(HonestyAudit.audit_file(${P@Q}), indent=2))
PY
