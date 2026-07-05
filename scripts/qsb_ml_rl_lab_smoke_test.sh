#!/usr/bin/env bash
# QSB ML/RL Lab smoke tests — DQN forward+backward, RL package imports + CartPole.
set -uo pipefail

QSB_ML_RL_ROOT="${QSB_ML_RL_ROOT:-/vaults/ai/qsb_ml_rl_lab}"
if [ ! -d "$QSB_ML_RL_ROOT" ]; then
  QSB_ML_RL_ROOT=/vaults/nvme0/qsb_tower_v1/native_cockpit/ml_rl_lab
fi
VENV="$QSB_ML_RL_ROOT/.venv"
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
  echo "ERROR: ML/RL venv missing at $VENV — run ./scripts/qsb_ml_rl_lab_install.sh first"
  exit 2
fi

mkdir -p "$QSB_ML_RL_ROOT/reports" "$QSB_ML_RL_ROOT/logs"
DQN_LOG="$QSB_ML_RL_ROOT/logs/dqn_smoke_test.log"
RL_LOG="$QSB_ML_RL_ROOT/logs/rl_package_smoke_test.log"

echo "== DQN smoke test ==" | tee "$DQN_LOG"
"$PY" "$QSB_ML_RL_ROOT/smoke_tests/qsb_dqn_smoke_test.py" 2>&1 | tee -a "$DQN_LOG"
DQN_EXIT=$?

echo "" | tee -a "$DQN_LOG"
echo "== RL package smoke test ==" | tee "$RL_LOG"
"$PY" "$QSB_ML_RL_ROOT/smoke_tests/qsb_rl_package_smoke_test.py" 2>&1 | tee -a "$RL_LOG"
RL_EXIT=$?

echo ""
echo "DQN exit=$DQN_EXIT · RL package exit=$RL_EXIT"
echo "Reports: $QSB_ML_RL_ROOT/reports/"
