#!/usr/bin/env bash
# EQSB Audit Current Kernel — Major Phase
# Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1
# Read-only. Writes:
#   data/registries/eqsb_kernel_major_audit.json
#   data/registries/eqsb_kernel_existing_capabilities.json
#   data/registries/eqsb_kernel_missing_capabilities.json
#   data/registries/eqsb_kernel_upgrade_plan.json
#   data/logs/eqsb_kernel_major_audit.jsonl
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.eqsb_kernel_core_ext audit "$@"
