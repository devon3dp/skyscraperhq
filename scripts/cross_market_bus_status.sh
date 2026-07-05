#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

echo "======================================================"
echo "  QSB Tower V1.3 — Cross-Market Bus Status"
echo "======================================================"
python3 - <<'PY'
from tower.cross_market_bus import CrossMarketBus
import json
print(json.dumps(CrossMarketBus().status(), indent=2))
PY
echo "======================================================"
