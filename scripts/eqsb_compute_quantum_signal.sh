#!/usr/bin/env bash
# EQSB Compute Quantum Signal — Major Phase
# Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1
# Simulated quantum-symbolic signal. No real hardware. No external calls.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.eqsb_quantum_signal "$@"
