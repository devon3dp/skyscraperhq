#!/usr/bin/env bash
# QSB Tower V1.3 — runtime environment file
# Phase: QSB_TOWER_RUNTIME_VENV_STANDARDIZATION_V1
#
# Standardized environment for:
#   - dashboard server
#   - skyscraper cockpit
#   - sidecars
#   - AutoLoop
#   - OANDA Floor 41
#   - Binance Floor 42
#   - OpenClaw sandbox visual layer
#   - Strategy Intelligence
#   - Correlation
#   - kernel chat / talk scripts
#
# Source this file before running any QSB Tower module:
#   source /vaults/nvme0/qsb_tower_v1/scripts/qsb_env.sh
#
# Strict separation rules:
#   - This venv is for QSB Tower only.
#   - It must NEVER share a process with /vaults/ai/airllm_lab/.venv.
#   - AirLLM, torch, transformers, CUDA packages must not be installed here.

export QSB_ROOT=/vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
export PIP_CACHE_DIR=/vaults/ai/cache/pip

if [ -f /vaults/nvme0/qsb_tower_v1/.venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source /vaults/nvme0/qsb_tower_v1/.venv/bin/activate
else
    echo "[qsb_env] WARNING: /vaults/nvme0/qsb_tower_v1/.venv not found" >&2
fi
