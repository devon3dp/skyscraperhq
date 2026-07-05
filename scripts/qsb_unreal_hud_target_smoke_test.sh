#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
echo "[smoke] HUD target JSON exists"
[[ -f data/registries/qsb_unreal_professional_hud_target.json ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] HUD target MD exists"
[[ -f data/logs/qsb_unreal_professional_hud_target.md ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] all 4 main zones present"
jq -e '
  .top_command_bar | length >= 8
  and .left_tab_rail | length >= 8
  and .right_contextual_panel | length >= 3
  and .bottom_dock | length >= 4
' data/registries/qsb_unreal_professional_hud_target.json >/dev/null 2>&1 || {
   jq -e '(.top_command_bar | length >= 8)
       and (.left_tab_rail | length >= 8)
       and (.right_contextual_panel | length >= 3)
       and (.bottom_dock | length >= 4)' \
       data/registries/qsb_unreal_professional_hud_target.json >/dev/null 2>&1 \
       || { echo " FAIL"; fails=$((fails+1)); }
}
echo "[smoke] floating windows >= 6"
jq -e '.floating_windows | length >= 6' data/registries/qsb_unreal_professional_hud_target.json >/dev/null 2>&1 || { echo " FAIL"; fails=$((fails+1)); }
echo "result: fails=$fails"
exit $fails
