#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
echo "[smoke] material pass python exists"
[[ -f scripts/qsb_unreal_apply_cinematic_material_pass.py ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] material pass shell exists"
[[ -x scripts/qsb_unreal_apply_cinematic_material_pass.sh ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] lighting pass python exists"
[[ -f scripts/qsb_unreal_apply_lighting_pass.py ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] lighting pass shell exists"
[[ -x scripts/qsb_unreal_apply_lighting_pass.sh ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] material recipe was written or material status JSON exists"
[[ -f /tmp/qsb_ue_material_pass.py || -f data/registries/qsb_unreal_cinematic_material_pass_status.json ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] lighting recipe was written or lighting status JSON exists"
[[ -f /tmp/qsb_ue_lighting_pass.py || -f data/registries/qsb_unreal_lighting_pass_status.json ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "result: fails=$fails"
exit $fails
