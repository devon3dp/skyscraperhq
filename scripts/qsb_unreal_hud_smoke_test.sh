#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
echo "[smoke] HUD plan markdown exists"
[[ -f data/logs/qsb_unreal_hud_implementation_plan.md ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] HUD plan JSON exists + lists widgets"
[[ -f data/registries/qsb_unreal_hud_implementation_plan.json ]] || { echo " FAIL"; fails=$((fails+1)); }
jq -e '.widgets | length >= 8' data/registries/qsb_unreal_hud_implementation_plan.json >/dev/null 2>&1 || { echo " FAIL widgets count"; fails=$((fails+1)); }
echo "result: fails=$fails"
exit $fails
