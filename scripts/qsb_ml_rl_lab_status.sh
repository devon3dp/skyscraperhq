#!/usr/bin/env bash
# QSB ML/RL Lab status — prints the status registry + smoke test results.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
STATUS=data/registries/qsb_ml_rl_lab_status.json
if [ ! -f "$STATUS" ]; then
  echo "ERROR: $STATUS missing — run installer + smoke tests first."
  exit 2
fi
if command -v jq >/dev/null 2>&1; then
  jq . "$STATUS"
else
  cat "$STATUS"
fi
