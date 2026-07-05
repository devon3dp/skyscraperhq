#!/usr/bin/env bash
# Pick 2 random entries from across all Claude floor logs and juxtapose them.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.connection_finder import ConnectionFinder
print(ConnectionFinder.juxtapose())
PY
