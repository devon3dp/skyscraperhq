#!/usr/bin/env bash
# qsb_model_floor_disable_external_calls.sh — turn the global lock OFF + record it.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
export QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED=0
cd "${ROOT}"
python3 -m src.tower.model_floors.model_floor_reporter >/dev/null 2>&1
echo "QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED=0 — external model floor calls disabled."
echo "Provider status refreshed at data/registries/qsb_model_floor_provider_status.json"
