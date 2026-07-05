#!/usr/bin/env bash
# QSB Kernel recent_upgrades report — registry-backed direct script.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec /usr/bin/python3 -m tower.kernel_registry_answer_builder recent
