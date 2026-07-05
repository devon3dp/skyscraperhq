#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

INSTRUMENTS="${1:-EUR_USD,GBP_USD,USD_JPY}"

python3 - <<PY
from tower.strategy_intelligence import StrategyIntelligence
import json
print(json.dumps(StrategyIntelligence().run("$INSTRUMENTS"), indent=2))
PY
