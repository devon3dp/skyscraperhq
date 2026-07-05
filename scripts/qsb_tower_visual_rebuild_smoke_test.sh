#!/usr/bin/env bash
# qsb_tower_visual_rebuild_smoke_test.sh — verify tower visual rebuild files.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="${ROOT}/data/logs/qsb_tower_visual_rebuild_smoke_test_${TS}.log"
OUT="${ROOT}/data/registries/qsb_tower_visual_rebuild_smoke_test_latest.json"
mkdir -p "$(dirname "${LOG}")"
pass=0; fail=0

check() {
  if [ -f "$1" ]; then echo "PASS: $1"; pass=$((pass+1))
  else echo "FAIL: $1"; fail=$((fail+1)); fi
}

{
echo "Tower visual rebuild smoke  ·  ts=${TS}"
# Scenes
for s in TowerRoot TowerFloorUnit TowerLiftShaft TowerLiftCar TowerWorkerBadge TowerPacketFlow TowerOpenClawMarker TowerDepartmentBand TowerFloorLabel TowerSelectionRing; do
  check "${PROJECT}/scenes/${s}.tscn"
done
# Scripts
for s in TowerRenderer TowerLiftSystem TowerLiftCar TowerWorkerVisualizer TowerWorkerActivityAnimator TowerPacketFlow TowerOpenClawAnimator TowerDepartmentBands TowerFloorLabelManager TowerSelectionController TowerCameraController TowerFloorUnit; do
  check "${PROJECT}/scripts/${s}.gd"
done
# Registries
for r in qsb_tower_visual_rebuild_status qsb_tower_floor_visual_identity_map qsb_tower_lift_system_status qsb_tower_lift_positions qsb_tower_worker_visibility_status qsb_tower_worker_density_map qsb_tower_worker_animation_status qsb_tower_openclaw_animation_status qsb_tower_packet_flow_status qsb_tower_camera_readability_status qsb_tower_interaction_status qsb_tower_data_source_status qsb_tower_visual_quality_score; do
  check "${ROOT}/data/registries/${r}.json"
done
# F01-F55 master registry (must exist OR placeholders OK)
if [ -f "${ROOT}/data/registries/qsb_floor_interior_master_registry.json" ]; then
  count=$(python3 -c "import json; print(len(json.load(open('${ROOT}/data/registries/qsb_floor_interior_master_registry.json')).get('floors',[])))")
  if [ "${count}" = "55" ]; then echo "PASS: F01-F55 master registry (${count})"; pass=$((pass+1))
  else echo "FAIL: F01-F55 master registry got ${count}"; fail=$((fail+1)); fi
fi
# Safety
if grep -r '"live_trading_enabled": true' "${ROOT}/data/registries/" 2>/dev/null | head -1 | grep -q .; then
  echo "FAIL: live_trading_enabled=true"; fail=$((fail+1))
else echo "PASS: live_trading_enabled=false"; pass=$((pass+1)); fi
if grep -r '"live_payments_enabled": true' "${ROOT}/data/registries/" 2>/dev/null | head -1 | grep -q .; then
  echo "FAIL: live_payments_enabled=true"; fail=$((fail+1))
else echo "PASS: live_payments_enabled=false"; pass=$((pass+1)); fi
# Secrets
if grep -rE '"api_token"[[:space:]]*:[[:space:]]*"[^*]' "${ROOT}/data/registries/" 2>/dev/null | head -1 | grep -q .; then
  echo "FAIL: unmasked api_token in registries"; fail=$((fail+1))
else echo "PASS: no unmasked tokens"; pass=$((pass+1)); fi
echo "TOTAL: pass=${pass} fail=${fail}"
} | tee "${LOG}"
cat > "${OUT}" <<EOF
{"ok": $([ "${fail}" -eq 0 ] && echo true || echo false), "kind":"qsb_tower_visual_rebuild_smoke_test_latest","ts":"${TS}","pass":${pass},"fail":${fail},"log_path":"${LOG}"}
EOF
[ "${fail}" -eq 0 ] && exit 0 || exit 1
