#!/usr/bin/env bash
# EQSB Memory + Continuity — Major Phase
# Writes data/registries/eqsb_memory_policy.json and eqsb_continuity_state.json
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.eqsb_memory "$@"
