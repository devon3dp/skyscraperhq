#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
echo "[smoke] visual upgrade pass python exists"
[[ -f scripts/qsb_unreal_apply_visual_upgrade_pass.py ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] visual upgrade pass shell wrapper exists"
[[ -x scripts/qsb_unreal_apply_visual_upgrade_pass.sh ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] pipeline doc exists"
[[ -f data/logs/qsb_unreal_professional_visual_pipeline.md ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] pipeline JSON exists"
[[ -f data/registries/qsb_unreal_professional_visual_pipeline.json ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] diagnosis JSON marks blockout_prototype_not_final"
grep -q 'blockout_prototype_not_final' data/registries/qsb_unreal_current_visual_diagnosis.json 2>/dev/null || { echo " FAIL"; fails=$((fails+1)); }
echo "result: fails=$fails"
exit $fails
