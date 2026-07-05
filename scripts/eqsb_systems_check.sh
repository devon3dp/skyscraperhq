#!/usr/bin/env bash
# EQSB Systems Check — Major Phase
# Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1
# Builds every EQSB layer (V1 + major) and writes the full introspection.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.eqsb_kernel_core_ext all "$@"
