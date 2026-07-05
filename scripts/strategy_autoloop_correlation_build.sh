#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

INSTRUMENTS="${1:-EUR_USD,GBP_USD,USD_JPY}"

python3 - <<PY
from tower.strategy_autoloop_correlation import StrategyAutoloopCorrelation
import json
print(json.dumps(StrategyAutoloopCorrelation().build("$INSTRUMENTS"), indent=2, default=str))
PY
