#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
echo "[smoke] visible build status script exists"
[[ -x scripts/qsb_unreal_visible_build_status.sh ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] open editor script exists"
[[ -x scripts/qsb_unreal_open_editor.sh ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] run editor build pass script exists"
[[ -x scripts/qsb_unreal_run_editor_build_pass.sh ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] take viewport screenshot script exists"
[[ -x scripts/qsb_unreal_take_viewport_screenshot.sh ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] visible build loop script exists"
[[ -x scripts/qsb_unreal_visible_build_loop.sh ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] status check produces JSON"
./scripts/qsb_unreal_visible_build_status.sh >/tmp/qsb_smoke_vb_status.txt 2>&1
grep -q '"dashboard_8847_http"' /tmp/qsb_smoke_vb_status.txt || { echo " FAIL (no dashboard_8847_http key)"; fails=$((fails+1)); }
echo "result: fails=$fails"
exit $fails
