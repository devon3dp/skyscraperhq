#!/usr/bin/env bash
# EQSB Guardian State — Major Phase
# Read-only kernel introspection. Writes data/registries/eqsb_guardian_state.json
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.eqsb_guardian "$@"
