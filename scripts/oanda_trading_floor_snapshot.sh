#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

INSTRUMENTS="${1:-EUR_USD,GBP_USD,USD_JPY,XAU_USD}"

python3 - <<PY
from tower.oanda_trading_floor import OANDATradingFloor
import json
print(json.dumps(OANDATradingFloor().snapshot("$INSTRUMENTS"), indent=2))
PY
