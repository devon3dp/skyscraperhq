#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

# Source env files (best-effort) so any provider creds are available — note
# this never enables execution. All locks remain enforced in code.
for env in .env.oanda_practice .env.binance .env.alpaca; do
  if [ -f "$env" ]; then
    set +u
    set -a
    # shellcheck disable=SC1090,SC1091
    source "$env"
    set +a
    set -u
  fi
done

echo "======================================================"
echo "  QSB Tower V1.3 — Cross-Market Bus Build"
echo "======================================================"
python3 - <<'PY'
from tower.cross_market_bus import CrossMarketBus
import json
print(json.dumps(CrossMarketBus().build(), indent=2))
PY
echo "======================================================"
