#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
echo "[smoke] reference board JSON exists"
[[ -f data/registries/qsb_unreal_visual_reference_board.json ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] reference board MD exists"
[[ -f data/logs/qsb_unreal_visual_reference_board.md ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] reference folder exists"
[[ -d references/visual_targets/tiktok_skyscraper_reference ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] reference URL recorded"
grep -q 'synclaro_marcoheer/video/7655064851110284576' data/registries/qsb_unreal_visual_reference_board.json || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] honest direct-access flag set"
jq -e '.direct_access == false' data/registries/qsb_unreal_visual_reference_board.json >/dev/null 2>&1 || { echo " FAIL"; fails=$((fails+1)); }
echo "result: fails=$fails"
exit $fails
