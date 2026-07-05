#!/usr/bin/env bash
# QSB Tower V1 — Floor 45 Worker Recruitment Agency
# Lists the sandbox-only Floor 45 worker candidates.
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
source scripts/qsb_env.sh
exec python -m tower.worker_recruitment_agency candidates "$@"
