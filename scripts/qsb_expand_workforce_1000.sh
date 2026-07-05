#!/usr/bin/env bash
# Phase: QSB_FULL_SKYSCRAPER_OCCUPANCY_COMMERCE_WORKFORCE_EXPANSION_V1
# Idempotent wrapper — does not publish listings, spend money, or unlock live trading.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

# Lightweight backup before modifying registries (no-op if directory
# does not exist).
ts=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p data/backups/skyscraper_occupancy_v1
for f in qsb_worker_room_assignments.json qsb_worker_station_assignments.json qsb_new_1000_workers_employed.json; do
  [ -f data/registries/$f ] && cp data/registries/$f data/backups/skyscraper_occupancy_v1/${ts}_$f 2>/dev/null || true
done

python3 -m tower.qsb_skyscraper_occupancy workforce_1000 2>&1 | head -8
echo "locks: live_money=False · listings_publish=False · payments=False · openclaw_exec=False"
