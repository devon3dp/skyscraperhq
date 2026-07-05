#!/usr/bin/env bash
# EQSB Kernel Self Audit — Major Phase
# Read-only. Runs the cadence loop and prints introspection summary.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.eqsb_kernel_core_ext all "$@"
