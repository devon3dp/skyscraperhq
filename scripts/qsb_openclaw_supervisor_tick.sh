#!/usr/bin/env bash
# OpenClaw Supervisor tick — refresh role/tickets/route/findings.
# Phase: QSB_DASHBOARD_TOTAL_REBUILD_3D_WORKERS_OPENCLAW_ONLINE_V1
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -c "from tower.qsb_dashboard_rebuild_v1 import build_openclaw_supervisor; import json; print(json.dumps(build_openclaw_supervisor(), indent=2))"
