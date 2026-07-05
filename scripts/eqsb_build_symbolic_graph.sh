#!/usr/bin/env bash
# EQSB Build Symbolic Graph — Major Phase
# Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1
# Reads kernel registries; writes data/registries/eqsb_symbolic_graph.json
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.eqsb_symbolic_graph "$@"
