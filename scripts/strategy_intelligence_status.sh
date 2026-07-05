#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

python3 - <<'PY'
from tower.strategy_intelligence import StrategyIntelligence
import json
print(json.dumps(StrategyIntelligence().status(), indent=2))
PY
