#!/usr/bin/env bash
# EQSB Hypothesis Engine — Major Phase
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.eqsb_hypotheses "$@"
