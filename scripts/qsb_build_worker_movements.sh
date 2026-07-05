#!/usr/bin/env bash
# Build qsb_worker_movements_latest.json from paper_trade_events
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -c "from tower.qsb_live_telemetry_repairs import build_worker_movements; import json; print(json.dumps(build_worker_movements(), indent=2))"
