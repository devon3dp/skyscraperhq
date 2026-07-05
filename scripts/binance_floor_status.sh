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

echo "======================================================"
echo "  QSB Tower V1.3 — Floor 42 Binance Trading Floor Status"
echo "======================================================"
python3 - <<'PY'
from tower.binance_floor import BinanceTradingFloor
import json
print(json.dumps(BinanceTradingFloor().dashboard(), indent=2))
PY
echo "======================================================"
