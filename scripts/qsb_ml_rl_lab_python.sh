#!/usr/bin/env bash
# Opens an interactive Python from the ML/RL venv with the right env vars set.
set -uo pipefail
QSB_ML_RL_ROOT="${QSB_ML_RL_ROOT:-/vaults/ai/qsb_ml_rl_lab}"
if [ ! -d "$QSB_ML_RL_ROOT" ]; then
  QSB_ML_RL_ROOT=/vaults/nvme0/qsb_tower_v1/native_cockpit/ml_rl_lab
fi
export PIP_CACHE_DIR="$QSB_ML_RL_ROOT/cache/pip"
export HF_HOME="$QSB_ML_RL_ROOT/cache/huggingface"
export TRANSFORMERS_CACHE="$QSB_ML_RL_ROOT/cache/huggingface/transformers"
export TORCH_HOME="$QSB_ML_RL_ROOT/cache/torch"
export TMPDIR="$QSB_ML_RL_ROOT/cache/tmp"
PY="$QSB_ML_RL_ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: venv missing at $QSB_ML_RL_ROOT/.venv — run ./scripts/qsb_ml_rl_lab_install.sh first"
  exit 2
fi
exec "$PY" "$@"
