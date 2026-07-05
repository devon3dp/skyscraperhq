#!/usr/bin/env bash
# QSB Tower V1 — Floor 45 Worker Recruitment Agency
# Advances one onboarding/training step for the Floor 45 sandbox candidates.
# Visual dispatch only — execution gates remain locked.
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
source scripts/qsb_env.sh
exec python -m tower.worker_recruitment_agency tick "$@"
