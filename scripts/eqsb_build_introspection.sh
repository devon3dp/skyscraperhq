#!/usr/bin/env bash
# EQSB Build Introspection — Major Phase
# Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1
# Rebuilds data/registries/eqsb_kernel_introspection_latest.json from
# every EQSB major-phase registry.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.eqsb_introspection "$@"
