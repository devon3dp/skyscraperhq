#!/usr/bin/env bash
# qsb_godot_overlay_audio_chat_smoke_test.sh — verify all required files exist.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="${ROOT}/data/logs/qsb_godot_overlay_audio_chat_smoke_test_${TS}.log"
RES="${ROOT}/data/registries/qsb_godot_overlay_audio_chat_smoke_test_latest.json"
mkdir -p "$(dirname "${LOG}")"

pass=0; fail=0
{
echo "QSB Godot Overlay/Audio/Chat Smoke Test  ·  ts=${TS}"

EXPECTED_SCRIPTS=(
  RightPanelTabs.gd
  KernelChatPanel.gd
  KernelChatBridge.gd
  AudioControlPanel.gd
  SoundManager.gd
  CommentaryManager.gd
  EventTicker.gd
  TalkBridge.gd
  FloorInspector.gd
  HUDController.gd
  Main.gd
)
for s in "${EXPECTED_SCRIPTS[@]}"; do
  if [ -f "${PROJECT}/scripts/${s}" ]; then
    echo "PASS: script ${s}"; pass=$((pass + 1))
  else
    echo "FAIL: script ${s}"; fail=$((fail + 1))
  fi
done

REQ_SCRIPTS_SH=(
  qsb_godot_audio_stack_status.sh
  qsb_godot_audio_test_sound.sh
  qsb_godot_audio_test_voice.sh
  qsb_godot_speak_event.sh
  qsb_godot_speak_kernel_status.sh
  qsb_godot_kernel_chat_bridge.sh
  qsb_godot_commentary_event_router.sh
)
for s in "${REQ_SCRIPTS_SH[@]}"; do
  if [ -x "${ROOT}/scripts/${s}" ]; then
    echo "PASS: bash ${s}"; pass=$((pass + 1))
  else
    echo "FAIL: bash ${s}"; fail=$((fail + 1))
  fi
done

REQ_REG=(
  qsb_godot_layout_overlay_repair_status.json
  qsb_godot_right_panel_tab_status.json
  qsb_godot_kernel_chat_real_panel_status.json
  qsb_godot_audio_stack_status.json
  qsb_godot_audio_voice_commentary_status.json
  qsb_godot_commentary_settings.json
  qsb_godot_event_ticker_repair_status.json
  qsb_godot_floor_inspector_repair_status.json
  qsb_godot_visual_clarity_score.json
)
for r in "${REQ_REG[@]}"; do
  if [ -f "${ROOT}/data/registries/${r}" ]; then
    echo "PASS: registry ${r}"; pass=$((pass + 1))
  else
    echo "FAIL: registry ${r}"; fail=$((fail + 1))
  fi
done

# Safety
if grep -r '"live_trading_enabled": true' "${ROOT}/data/registries/" 2>/dev/null | head -1 | grep -q .; then
  echo "FAIL: live_trading_enabled=true present"; fail=$((fail + 1))
else
  echo "PASS: no live_trading_enabled=true"; pass=$((pass + 1))
fi
if grep -r '"live_payments_enabled": true' "${ROOT}/data/registries/" 2>/dev/null | head -1 | grep -q .; then
  echo "FAIL: live_payments_enabled=true present"; fail=$((fail + 1))
else
  echo "PASS: no live_payments_enabled=true"; pass=$((pass + 1))
fi

echo "Total PASS: ${pass}  Total FAIL: ${fail}"
} | tee "${LOG}"

cat > "${RES}" <<EOF
{
  "ok": $([ "${fail}" -eq 0 ] && echo true || echo false),
  "kind": "qsb_godot_overlay_audio_chat_smoke_test_latest",
  "ts": "${TS}",
  "pass": ${pass},
  "fail": ${fail},
  "log_path": "${LOG}"
}
EOF
[ "${fail}" -eq 0 ] && exit 0 || exit 1
