#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
for f in scripts/unreal/qsb_unreal_find_project.sh \
         scripts/unreal/qsb_unreal_editor_status.sh \
         scripts/unreal/qsb_unreal_open_editor.sh \
         scripts/unreal/qsb_unreal_cli_build_pass.sh \
         scripts/unreal/qsb_unreal_take_screenshot.sh \
         scripts/unreal/qsb_unreal_driver_status.sh \
         scripts/unreal/python/qsb_unreal_build_skyscraper_pass.py \
         scripts/unreal/python/qsb_unreal_build_hud_pass.py \
         scripts/unreal/python/qsb_unreal_build_city_pass.py \
         scripts/unreal/python/qsb_unreal_build_lift_worker_pass.py \
         scripts/unreal/python/qsb_unreal_save_and_screenshot.py; do
  [[ -f "$f" ]] || { echo "MISSING $f"; fails=$((fails+1)); }
done
./scripts/unreal/qsb_unreal_find_project.sh > /tmp/proof_ue.txt 2>&1
PJ=$(jq -r .project_found data/registries/qsb_unreal_cli_driver_status.json 2>/dev/null || echo no)
EN=$(jq -r .engine_found data/registries/qsb_unreal_cli_driver_status.json 2>/dev/null || echo no)
echo "project_found=$PJ engine_found=$EN"
echo "unreal driver fails=$fails"
exit $fails
