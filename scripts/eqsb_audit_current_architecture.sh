#!/usr/bin/env bash
# EQSB Deep Kernel Audit V1
# Phase: EQSB_DEEP_KERNEL_ARCHITECTURE_AND_SYMBOLIC_COGNITION_V1
#
# Read-only audit. Never edits source files. Never enables execution.
# Never calls external APIs. Never calls AirLLM. Never places orders.
#
# Writes:
#   data/registries/eqsb_deep_kernel_audit.json
#   data/registries/eqsb_missing_architecture_report.json
#   data/registries/eqsb_existing_capabilities_map.json
#   data/logs/eqsb_deep_kernel_audit.jsonl
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.eqsb_cognition audit "$@"
