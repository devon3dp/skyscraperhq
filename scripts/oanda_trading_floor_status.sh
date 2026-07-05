#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

echo "======================================================"
echo "  QSB Tower V1.3 — Floor 41 OANDA Trading Floor Status"
echo "======================================================"
python3 - <<'PY'
from tower.oanda_trading_floor import OANDATradingFloor
import json
print(json.dumps(OANDATradingFloor().dashboard(), indent=2))
PY
echo "======================================================"
