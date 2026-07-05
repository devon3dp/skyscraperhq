#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
F=data/registries/qsb_team_last_model_calls.json
[[ -f $F ]] || { echo "NO model-call history"; exit 1; }
N=$(jq 'length' $F 2>/dev/null || echo 0)
echo "model_call_history_count=$N"
[[ "$N" -ge 1 ]] && exit 0 || exit 1
