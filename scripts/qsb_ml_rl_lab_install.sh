#!/usr/bin/env bash
# QSB ML/RL Lab installer — isolated venv, CPU torch, idempotent.
# Phase: QSB_ML_RL_TORCH_LAB_INSTALL_AND_SMOKE_TEST_V1
#
# DOES NOT touch the main QSB .venv or the AirLLM lab.
# DOES NOT enable live trading / autonomous dispatch / real OpenClaw exec.

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1 2>/dev/null || true
# shellcheck disable=SC1091
source scripts/qsb_env.sh 2>/dev/null || true

QSB_ML_RL_ROOT="${QSB_ML_RL_ROOT:-/vaults/ai/qsb_ml_rl_lab}"
export PIP_CACHE_DIR="$QSB_ML_RL_ROOT/cache/pip"
export HF_HOME="$QSB_ML_RL_ROOT/cache/huggingface"
export TRANSFORMERS_CACHE="$QSB_ML_RL_ROOT/cache/huggingface/transformers"
export TORCH_HOME="$QSB_ML_RL_ROOT/cache/torch"
export TMPDIR="$QSB_ML_RL_ROOT/cache/tmp"

# Fallback if /vaults/ai not writable
if [ ! -d /vaults/ai ] || ! touch /vaults/ai/.write_test 2>/dev/null; then
  QSB_ML_RL_ROOT=/vaults/nvme0/qsb_tower_v1/native_cockpit/ml_rl_lab
  echo "FALLBACK: /vaults/ai unavailable — using $QSB_ML_RL_ROOT"
else
  rm -f /vaults/ai/.write_test
fi

mkdir -p "$QSB_ML_RL_ROOT"/{cache/pip,cache/huggingface,cache/torch,cache/tmp,logs,reports,smoke_tests,models,runs}

VENV="$QSB_ML_RL_ROOT/.venv"
LOG="$QSB_ML_RL_ROOT/logs/install.log"
PIP_LOG="$QSB_ML_RL_ROOT/logs/pip.log"
RESULT_REG=/vaults/nvme0/qsb_tower_v1/data/registries/qsb_ml_rl_package_install_status.json
TORCH_REG=/vaults/nvme0/qsb_tower_v1/data/registries/qsb_ml_rl_torch_status.json

mkdir -p /vaults/nvme0/qsb_tower_v1/data/registries
: > "$LOG"
echo "QSB ML/RL Lab installer · $(date -u +%FT%TZ)" | tee -a "$LOG"
echo "QSB_ML_RL_ROOT=$QSB_ML_RL_ROOT" | tee -a "$LOG"

# Create venv if missing — use system Python 3.12 explicitly
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating venv at $VENV" | tee -a "$LOG"
  /usr/bin/python3 -m venv "$VENV"
fi

# Activate
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "venv python: $(which python)" | tee -a "$LOG"
echo "venv python version: $(python --version)" | tee -a "$LOG"

# Upgrade pip stack
python -m pip install --upgrade pip setuptools wheel 2>&1 | tee -a "$PIP_LOG" | tail -5

# Install with --quiet, log everything to pip.log
PKG_OK=()
PKG_FAIL=()
install_one() {
  local pkg="$1"
  echo "" | tee -a "$LOG"
  echo "▶ pip install $pkg" | tee -a "$LOG"
  if python -m pip install --quiet "$pkg" 2>&1 | tee -a "$PIP_LOG" | tail -3 ; then
    PKG_OK+=("$pkg")
    echo "  ✓ $pkg" | tee -a "$LOG"
  else
    PKG_FAIL+=("$pkg")
    echo "  ✗ $pkg failed — continuing" | tee -a "$LOG"
  fi
}

# Core CPU torch first
for p in torch torchvision torchaudio numpy scipy pandas scikit-learn matplotlib pillow tqdm rich pydantic requests psutil joblib tensorboard; do
  install_one "$p"
done

# Deep learning utilities
for p in accelerate transformers datasets safetensors einops lightning optuna; do
  install_one "$p"
done

# Reinforcement learning
for p in torchrl tensordict gymnasium 'stable-baselines3[extra]' shimmy; do
  install_one "$p"
done

# Optional RL — best effort
for p in pettingzoo supersuit; do
  install_one "$p"
done

# Capture Torch status
TORCH_INFO=$(python - <<'PY'
import json
try:
  import torch
  cuda = torch.cuda.is_available()
  out = {
    "ok": True,
    "torch_version": torch.__version__,
    "cuda_available": cuda,
    "cuda_version_in_torch": torch.version.cuda,
    "gpu_name": torch.cuda.get_device_name(0) if cuda else None,
  }
except Exception as e:
  out = {"ok": False, "error": str(e)[:200]}
print(json.dumps(out))
PY
)
echo "$TORCH_INFO" | tee -a "$LOG"

python <<PY
import json, time
data = json.loads('''$TORCH_INFO''')
data["phase"] = "QSB_ML_RL_TORCH_LAB_INSTALL_AND_SMOKE_TEST_V1"
data["generated_ts"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
data["kind"] = "qsb_ml_rl_torch_status"
data["execution_allowed"] = False
data["real_money_live_trading_enabled"] = False
data["autonomous_dispatch_enabled"] = False
data["openclaw_real_tool_execution_enabled"] = False
data["advisory_only"] = True
open("$TORCH_REG", "w").write(json.dumps(data, indent=2))
PY

# Write package install status registry
python <<PY
import json, time
ok = """${PKG_OK[*]}""".split()
fail = """${PKG_FAIL[*]}""".split()
data = {
  "ok": True,
  "kind": "qsb_ml_rl_package_install_status",
  "phase": "QSB_ML_RL_TORCH_LAB_INSTALL_AND_SMOKE_TEST_V1",
  "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
  "lab_root": "$QSB_ML_RL_ROOT",
  "venv": "$VENV",
  "installed_count": len(ok),
  "failed_count": len(fail),
  "installed": ok,
  "failed": fail,
  "execution_allowed": False,
  "real_money_live_trading_enabled": False,
  "autonomous_dispatch_enabled": False,
  "openclaw_real_tool_execution_enabled": False,
  "advisory_only": True,
}
open("$RESULT_REG", "w").write(json.dumps(data, indent=2))
print(f"installed={len(ok)} failed={len(fail)}")
PY

echo "" | tee -a "$LOG"
echo "Install complete." | tee -a "$LOG"
echo "Logs: $LOG · $PIP_LOG" | tee -a "$LOG"
echo "Status: $RESULT_REG  $TORCH_REG" | tee -a "$LOG"
