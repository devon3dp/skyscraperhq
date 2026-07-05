#!/usr/bin/env bash
# EQSB Hardware Floor audit + manifest writer
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.qsb_hardware_floor "$@"
