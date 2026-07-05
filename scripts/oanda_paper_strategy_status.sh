#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

python3 - <<'PY'
from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab
import json
print(json.dumps(OANDAPaperStrategyLab().dashboard(), indent=2))
PY
