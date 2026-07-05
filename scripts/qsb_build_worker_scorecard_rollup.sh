#!/usr/bin/env bash
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -c "from tower.qsb_live_telemetry_repairs import build_scorecard_rollup_7d; import json; print(json.dumps(build_scorecard_rollup_7d(), indent=2))"
