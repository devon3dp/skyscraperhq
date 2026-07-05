#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

TICKS="${1:-5}"
DELAY="${2:-10}"
INSTRUMENTS="${3:-EUR_USD,GBP_USD,USD_JPY}"

python3 - <<PY
from tower.sandbox_performance_loop import SandboxPerformanceLoop
import json
print(json.dumps(SandboxPerformanceLoop().run(
    ticks=int("$TICKS"),
    delay_seconds=int("$DELAY"),
    instruments="$INSTRUMENTS",
    kernel_commentary=True
), indent=2))
PY
