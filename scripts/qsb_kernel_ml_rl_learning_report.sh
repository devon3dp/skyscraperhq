#!/usr/bin/env bash
# QSB Kernel ML/RL learning report.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh 2>/dev/null || true
echo "=== ML/RL lab status registries ==="
for r in qsb_ml_rl_lab_path.json qsb_ml_rl_existing_environment_audit.json qsb_ml_rl_lab_verified_for_integration.json qsb_ml_rl_torch_status.json qsb_ml_rl_package_install_status.json qsb_ml_rl_classroom_map.json qsb_ml_rl_curriculum.json qsb_ml_rl_research_lab_map.json qsb_worker_ml_rl_training_roster.json qsb_openclaw_ml_rl_supervision.json qsb_opencore_ml_rl_access_policy.json qsb_kernel_ml_rl_learning_evidence.json; do
  p=data/registries/$r
  if [ -f "$p" ]; then
    echo "--- $r ---"
    if command -v jq >/dev/null 2>&1; then jq -c '. | {kind, generated_ts}' "$p"
    else head -c 200 "$p"; echo; fi
  fi
done
echo ""
echo "=== Ask the kernel chat (will use registry-aware adapter) ==="
./scripts/qsb_kernel_chat.sh "Kernel, report the ML/RL lab integration. Mention Torch, CUDA, DQN smoke test, classrooms, research labs, worker learning, OpenClaw/OpenCore supervision, and safety locks." | head -200
