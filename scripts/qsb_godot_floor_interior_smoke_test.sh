#!/usr/bin/env bash
# qsb_godot_floor_interior_smoke_test.sh — verify all required files exist.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="${ROOT}/data/logs/qsb_godot_floor_interior_smoke_test_${TS}.log"
OUT="${ROOT}/data/registries/qsb_godot_floor_interior_smoke_test_latest.json"
mkdir -p "$(dirname "${LOG}")"
pass=0; fail=0

check_file() {
  if [ -f "$1" ]; then echo "PASS: $1"; pass=$((pass+1))
  else echo "FAIL: $1"; fail=$((fail+1)); fi
}

{
echo "Floor interior smoke test  ·  ts=${TS}"
# Scenes
check_file "${PROJECT}/scenes/interiors/FloorInterior.tscn"
check_file "${PROJECT}/scenes/interiors/GenericFloorInterior.tscn"
check_file "${PROJECT}/scenes/interiors/KernelPenthouseInterior.tscn"
check_file "${PROJECT}/scenes/interiors/TradingFloorInterior.tscn"
check_file "${PROJECT}/scenes/interiors/MLRLClassroomInterior.tscn"
check_file "${PROJECT}/scenes/interiors/BankingCommerceInterior.tscn"
check_file "${PROJECT}/scenes/interiors/SecurityGuardianInterior.tscn"
check_file "${PROJECT}/scenes/interiors/HardwareObservatoryInterior.tscn"
check_file "${PROJECT}/scenes/units/WorkerAvatar.tscn"
check_file "${PROJECT}/scenes/units/OpenClawAvatar.tscn"
check_file "${PROJECT}/scenes/units/RoomZone.tscn"
check_file "${PROJECT}/scenes/units/DepartmentZone.tscn"
check_file "${PROJECT}/scenes/units/ManagerDesk.tscn"
check_file "${PROJECT}/scenes/units/TelemetryBoard.tscn"
check_file "${PROJECT}/scenes/units/ActivityPacket.tscn"
# Scripts
check_file "${PROJECT}/scripts/interiors/FloorInteriorController.gd"
check_file "${PROJECT}/scripts/interiors/FloorInteriorFactory.gd"
check_file "${PROJECT}/scripts/interiors/FloorInteriorRegistry.gd"
check_file "${PROJECT}/scripts/interiors/FloorClickRouter.gd"
check_file "${PROJECT}/scripts/interiors/FloorInteriorCamera.gd"
check_file "${PROJECT}/scripts/interiors/FloorInteriorHUD.gd"
check_file "${PROJECT}/scripts/interiors/LiveInteriorTelemetryBridge.gd"
check_file "${PROJECT}/scripts/interiors/InteriorActivityStream.gd"
check_file "${PROJECT}/scripts/avatars/WorkerAvatar.gd"
check_file "${PROJECT}/scripts/avatars/WorkerActivityAnimator.gd"
check_file "${PROJECT}/scripts/avatars/OpenClawInteriorInspector.gd"
check_file "${PROJECT}/scripts/systems/InteriorLODPool.gd"
check_file "${PROJECT}/scripts/systems/InteriorSafetyGate.gd"
check_file "${PROJECT}/scripts/systems/InteriorScreenshotReview.gd"
check_file "${PROJECT}/scripts/panels/FloorInteriorPanel.gd"
check_file "${PROJECT}/scripts/panels/WorkerDetailPanel.gd"
check_file "${PROJECT}/scripts/panels/RoomDetailPanel.gd"
check_file "${PROJECT}/scripts/panels/DepartmentActivityPanel.gd"
# Registries
check_file "${ROOT}/data/registries/qsb_floor_interior_master_registry.json"
check_file "${ROOT}/data/registries/qsb_worker_animation_contract.json"
check_file "${ROOT}/data/registries/qsb_floor_worker_animation_status.json"
check_file "${ROOT}/data/registries/qsb_floor_interior_performance_policy.json"
check_file "${ROOT}/data/registries/qsb_floor_activity_stream_latest.json"
check_file "${ROOT}/scripts/qsb_floor_activity_stream_tick.sh"
check_file "${ROOT}/scripts/qsb_floor_interior_coverage_audit.sh"
check_file "${ROOT}/scripts/qsb_godot_floor_interior_smoke_test.sh"

# Coverage check — must have F01..F55
if [ -f "${ROOT}/data/registries/qsb_floor_interior_master_registry.json" ]; then
  count=$(python3 -c "import json; print(len(json.load(open('${ROOT}/data/registries/qsb_floor_interior_master_registry.json')).get('floors',[])))")
  if [ "${count}" = "55" ]; then
    echo "PASS: F01-F55 coverage (${count} floors)"; pass=$((pass+1))
  else
    echo "FAIL: F01-F55 coverage (got ${count})"; fail=$((fail+1))
  fi
fi

# Safety
if grep -r '"live_trading_enabled": true' "${ROOT}/data/registries/" 2>/dev/null | head -1 | grep -q .; then
  echo "FAIL: live_trading_enabled=true present"; fail=$((fail+1))
else
  echo "PASS: live_trading_enabled remains false"; pass=$((pass+1))
fi
if grep -r '"live_payments_enabled": true' "${ROOT}/data/registries/" 2>/dev/null | head -1 | grep -q .; then
  echo "FAIL: live_payments_enabled=true present"; fail=$((fail+1))
else
  echo "PASS: live_payments_enabled remains false"; pass=$((pass+1))
fi

echo "TOTAL: pass=${pass} fail=${fail}"
} | tee "${LOG}"

cat > "${OUT}" <<EOF
{
  "ok": $([ "${fail}" -eq 0 ] && echo true || echo false),
  "kind": "qsb_godot_floor_interior_smoke_test_latest",
  "ts": "${TS}",
  "pass": ${pass},
  "fail": ${fail},
  "log_path": "${LOG}"
}
EOF
[ "${fail}" -eq 0 ] && exit 0 || exit 1
