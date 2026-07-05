#!/usr/bin/env bash
# EQSB Kernel Learning Loop tick (refreshes learning + lessons + assistance policy)
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
python3 -m tower.eqsb_observatory learning
python3 -m tower.eqsb_observatory patches
