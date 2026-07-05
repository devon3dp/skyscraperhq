#!/usr/bin/env bash
# qsb_godot_feature_migration_smoke_test.sh — verify all required Godot files exist.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="${ROOT}/data/logs/qsb_godot_feature_migration_smoke_test_${TS}.log"
RES="${ROOT}/data/registries/qsb_godot_feature_migration_smoke_test_latest.json"

mkdir -p "$(dirname "${LOG}")"

pass=0; fail=0
{
echo "QSB Godot Feature Migration Smoke Test"
echo "ts=${TS}"
echo

# Project basics
for f in project.godot scenes/Main.tscn scripts/Main.gd; do
  if [ -f "${PROJECT}/${f}" ]; then
    echo "PASS: project file ${f}"
    pass=$((pass+1))
  else
    echo "FAIL: project file ${f}"
    fail=$((fail+1))
  fi
done

# Required scripts
EXPECTED=(
  ControlBar.gd
  KernelChatPanel.gd
  KernelChatBridge.gd
  AudioControlPanel.gd
  TalkBridge.gd
  VoiceControlBridge.gd
  FloorInteraction.gd
  FloorInspector.gd
  FloorInteriorRenderer.gd
  CameraController.gd
  EventTicker.gd
  EventStreamAnimator.gd
  WorkerRenderer.gd
  WorkerInspector.gd
  OpenClawRenderer.gd
  OpenClawPanel.gd
  TradingPanel.gd
  RiskPanel.gd
  MLRLPanel.gd
  BankingGatewayPanel.gd
  GitHubScoutPanel.gd
  KernelCognitivePanel.gd
  CommercePanel.gd
  ClassroomPanel.gd
  TelemetryBridge.gd
  TowerRenderer.gd
  LiftRenderer.gd
  HUDController.gd
  _PanelBase.gd
)
for s in "${EXPECTED[@]}"; do
  if [ -f "${PROJECT}/scripts/${s}" ]; then
    echo "PASS: script ${s}"
    pass=$((pass+1))
  else
    echo "FAIL: script ${s}"
    fail=$((fail+1))
  fi
done

# Required registries
REQ_REG=(
  qsb_old_dashboard_feature_inventory.json
  qsb_old_to_godot_feature_parity_matrix.json
  qsb_godot_control_wiring_status.json
  qsb_godot_kernel_chat_migration_status.json
  qsb_godot_audio_voice_migration_status.json
  qsb_godot_floor_navigation_migration_status.json
  qsb_godot_trading_panel_migration_status.json
  qsb_godot_worker_openclaw_migration_status.json
  qsb_godot_department_panel_migration_status.json
  qsb_godot_event_ticker_migration_status.json
  qsb_godot_telemetry_bridge_sources.json
  qsb_godot_layout_after_feature_migration_score.json
)
for r in "${REQ_REG[@]}"; do
  if [ -f "${ROOT}/data/registries/${r}" ]; then
    echo "PASS: registry ${r}"
    pass=$((pass+1))
  else
    echo "FAIL: registry ${r}"
    fail=$((fail+1))
  fi
done

# Safety: verify no live_trading_enabled=true in policy registries
if grep -r '"live_trading_enabled": true' "${ROOT}/data/registries/" 2>/dev/null | head -1 | grep -q '.'; then
  echo "FAIL: live_trading_enabled=true found"
  fail=$((fail+1))
else
  echo "PASS: no live_trading_enabled=true"
  pass=$((pass+1))
fi
if grep -r '"live_payments_enabled": true' "${ROOT}/data/registries/" 2>/dev/null | head -1 | grep -q '.'; then
  echo "FAIL: live_payments_enabled=true found"
  fail=$((fail+1))
else
  echo "PASS: no live_payments_enabled=true"
  pass=$((pass+1))
fi

echo
echo "Total PASS: ${pass}"
echo "Total FAIL: ${fail}"
} | tee "${LOG}"

# Result JSON
cat > "${RES}" <<EOF
{
  "ok": $([ "${fail}" -eq 0 ] && echo true || echo false),
  "kind": "qsb_godot_feature_migration_smoke_test_latest",
  "ts": "${TS}",
  "pass": ${pass},
  "fail": ${fail},
  "log_path": "${LOG}"
}
EOF
echo
echo "Result registry: ${RES}"
[ "${fail}" -eq 0 ] && exit 0 || exit 1
