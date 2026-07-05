#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.binance ]; then
  set +u
  set -a
  # shellcheck disable=SC1091
  source .env.binance
  set +a
  set -u
fi

SYMBOLS="${1:-BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT}"

python3 - <<PY
from tower.binance_floor import BinanceTradingFloor
import json
print(json.dumps(BinanceTradingFloor().snapshot("$SYMBOLS"), indent=2))
PY
