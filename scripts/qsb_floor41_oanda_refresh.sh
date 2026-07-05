#!/usr/bin/env bash
# QSB Floor 41 OANDA — Refresh
# Phase: QSB_FLOOR_41_OANDA_FULL_TRADING_FLOOR_REBUILD_V1
# Refreshes all qsb_floor41_oanda_* registries. Paper/practice only.

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
[ -f .env.oanda_practice ] && { set -a; . ./.env.oanda_practice; set +a; }

python3 -m tower.qsb_floor41_oanda 2>&1 | head -40
