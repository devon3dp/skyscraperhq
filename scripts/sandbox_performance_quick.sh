#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
./scripts/sandbox_performance_loop.sh 3 5 EUR_USD,GBP_USD,USD_JPY
