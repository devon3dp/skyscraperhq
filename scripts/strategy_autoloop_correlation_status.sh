#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

python3 - <<'PY'
from tower.strategy_autoloop_correlation import StrategyAutoloopCorrelation
import json
print(json.dumps(StrategyAutoloopCorrelation().status(), indent=2, default=str))
PY
