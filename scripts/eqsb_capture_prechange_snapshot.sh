#!/usr/bin/env bash
# EQSB Phase Prechange Snapshot
# Phase: EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.eqsb_observatory prechange "$@"
