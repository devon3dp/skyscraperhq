#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.alpaca ]; then
  set +u
  set -a
  # shellcheck disable=SC1091
  source .env.alpaca
  set +a
  set -u
fi

SYMBOLS="${1:-AAPL,MSFT,NVDA,TSLA,SPY,QQQ}"

python3 - <<PY
from tower.stock_paper_strategy import StockPaperStrategyLab
import json
print(json.dumps(StockPaperStrategyLab().run("$SYMBOLS"), indent=2))
PY
