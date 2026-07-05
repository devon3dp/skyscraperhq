#!/usr/bin/env bash
# QSB Browser-Visible Reality Check
# Phase: QSB_KERNEL_CHAT_PENTHOUSE_AND_3D_DASHBOARD_REALITY_FIX_V1
#
# Verifies what automation CAN check (HTML state + payloads).
# Visible result MUST be confirmed by the user in a browser.

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

URL="http://127.0.0.1:8765"
REG_OUT="data/registries/qsb_browser_visible_reality_check.json"
LOG_OUT="data/logs/qsb_browser_visible_reality_check.txt"
mkdir -p "$(dirname "$LOG_OUT")"

pass=0; total=0; failed=""
check() {
  total=$((total + 1))
  if [ "$2" = "1" ]; then pass=$((pass + 1)); echo "  ✓ $1 — $3" | tee -a "$LOG_OUT"
  else failed="$failed $1"; echo "  ✗ $1 — $3" | tee -a "$LOG_OUT"; fi
}

: > "$LOG_OUT"
echo "QSB Browser-Visible Reality Check · $(date -u +%FT%TZ)" | tee -a "$LOG_OUT"
echo "phase: QSB_KERNEL_CHAT_PENTHOUSE_AND_3D_DASHBOARD_REALITY_FIX_V1" | tee -a "$LOG_OUT"
echo "" | tee -a "$LOG_OUT"

HTML=$(curl -s "${URL}/")

# Identity
SINGLE_TITLE=$(echo "$HTML" | grep -c "QSB Tower — 3D Operations Cockpit")
check single_title_present "$([ "$SINGLE_TITLE" -ge 1 ] && echo 1 || echo 0)" "title=$SINGLE_TITLE"
DUP=$(echo "$HTML" | grep -cE "TOWER V1\.3|TOWER V1\.4")
check no_duplicate_versions "$([ "$DUP" = "0" ] && echo 1 || echo 0)" "duplicates=$DUP"

# Speech voice
HAS_SPEECH=$(echo "$HTML" | grep -c "qsb_speech_voice.js")
check speech_voice_module_included "$([ "$HAS_SPEECH" -ge 1 ] && echo 1 || echo 0)" "matches=$HAS_SPEECH"
SPEECH_200=$(curl -s -o /dev/null -w "%{http_code}" "${URL}/static/qsb_speech_voice.js")
check speech_voice_asset_200 "$([ "$SPEECH_200" = "200" ] && echo 1 || echo 0)" "http=$SPEECH_200"
SPEECH_REG=$(curl -s "${URL}/api/dashboard/speech_settings" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('default_lang',''))" 2>/dev/null || echo "")
check speech_default_english "$([ "$SPEECH_REG" = "en-GB" ] && echo 1 || echo 0)" "default_lang=$SPEECH_REG"

# Kernel chat truth
CANNED=$(curl -s "${URL}/api/dashboard/kernel_chat_canned_audit" | python3 -c "import json,sys;print(len(json.load(sys.stdin).get('root_causes',[])))" 2>/dev/null || echo 0)
check kernel_canned_audit_populated "$([ "$CANNED" -ge 3 ] && echo 1 || echo 0)" "root_causes=$CANNED"

# Live behaviour test — Floor 41 question must NOT return identity paragraph
F41_REPLY=$(python3 -m tower.kernel_dialogue_adapter --symbolic-only "Kernel, what is Floor 41 OANDA doing right now?" 2>&1 | head -100)
F41_HAS_TOPIC=$(echo "$F41_REPLY" | grep -c "Floor 41 OANDA — Full Trading Floor Report" || true)
F41_HAS_IDENT=$(echo "$F41_REPLY" | grep -c "Local symbolic interpretation:" || true)
check kernel_floor41_topic_fires "$([ "$F41_HAS_TOPIC" -ge 1 ] && echo 1 || echo 0)" "topic block present=$F41_HAS_TOPIC"
check kernel_floor41_no_identity_paragraph "$([ "$F41_HAS_IDENT" = "0" ] && echo 1 || echo 0)" "identity_in_reply=$F41_HAS_IDENT"

F42_REPLY=$(python3 -m tower.kernel_dialogue_adapter --symbolic-only "Kernel, what workers are active on Floor 42?" 2>&1 | head -80)
F42_HAS_TOPIC=$(echo "$F42_REPLY" | grep -c "Floor 42 — Binance Trading Floor" || true)
check kernel_floor42_topic_fires "$([ "$F42_HAS_TOPIC" -ge 1 ] && echo 1 || echo 0)" "topic block present=$F42_HAS_TOPIC"

HW_REPLY=$(python3 -m tower.kernel_dialogue_adapter --symbolic-only "Kernel, what hardware are you running on?" 2>&1 | head -50)
HW_HAS_TOPIC=$(echo "$HW_REPLY" | grep -cE "Hardware Observatory|hardware_systems_floor|cpu_model:" || true)
check kernel_hardware_topic_fires "$([ "$HW_HAS_TOPIC" -ge 1 ] && echo 1 || echo 0)" "hw_block=$HW_HAS_TOPIC"

IDENT_REPLY=$(python3 -m tower.kernel_dialogue_adapter --symbolic-only "Kernel, who are you?" 2>&1 | head -20)
IDENT_HAS=$(echo "$IDENT_REPLY" | grep -c "I am QSB Kernel" || true)
check kernel_identity_query_works "$([ "$IDENT_HAS" -ge 1 ] && echo 1 || echo 0)" "identity_block=$IDENT_HAS"

# Penthouse
PH_CMD=$(curl -s "${URL}/api/dashboard/penthouse_command_state" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('zone_count',0))" 2>/dev/null || echo 0)
check penthouse_command_state_built "$([ "$PH_CMD" = "11" ] && echo 1 || echo 0)" "zone_count=$PH_CMD"
PH_GAUGE=$(curl -s "${URL}/api/dashboard/penthouse_gauges" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('gauge_count',0))" 2>/dev/null || echo 0)
check penthouse_gauges_built "$([ "$PH_GAUGE" -ge 8 ] && echo 1 || echo 0)" "gauge_count=$PH_GAUGE"
PH_REPAIR=$(curl -s "${URL}/api/dashboard/penthouse_repair_priority" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('priority_count',0))" 2>/dev/null || echo 0)
check penthouse_repair_priority_built "$([ "$PH_REPAIR" -ge 1 ] && echo 1 || echo 0)" "priority_count=$PH_REPAIR"
PH_SCRIPT=$(echo "$HTML" | grep -c "qsb_3d_penthouse.js")
check penthouse_script_included "$([ "$PH_SCRIPT" -ge 1 ] && echo 1 || echo 0)" "script tags=$PH_SCRIPT"

# Data availability (carried from prior phases)
LIFTS=$(curl -s "${URL}/api/dashboard/lift_scene_state" | python3 -c "import json,sys;print(json.load(sys.stdin).get('lift_count',0))" 2>/dev/null || echo 0)
check lifts_9 "$([ "$LIFTS" = "9" ] && echo 1 || echo 0)" "lift_count=$LIFTS"
F42_ROOMS=$(curl -s "${URL}/api/dashboard/floor42_binance_interior" | python3 -c "import json,sys;print(len(json.load(sys.stdin).get('rooms',[])))" 2>/dev/null || echo 0)
check floor42_rooms "$([ "$F42_ROOMS" -ge 4 ] && echo 1 || echo 0)" "rooms=$F42_ROOMS"
OC_FLOOR=$(curl -s "${URL}/api/openclaw/route" | python3 -c "import json,sys;print(json.load(sys.stdin).get('current_floor',''))" 2>/dev/null || echo "")
check openclaw_route_floor "$([ -n "$OC_FLOOR" ] && echo 1 || echo 0)" "current_floor=$OC_FLOOR"

score=$(python3 -c "print(round(100.0 * $pass / $total, 1))")
echo "" | tee -a "$LOG_OUT"
echo "automated score: ${score} (${pass}/${total})" | tee -a "$LOG_OUT"
echo "failed:${failed:-none}" | tee -a "$LOG_OUT"
echo "" | tee -a "$LOG_OUT"

cat <<'MANUAL' | tee -a "$LOG_OUT"
--- MANUAL VISUAL CHECKLIST (you must open the browser to confirm) ---
Automation CANNOT verify pixels. Please tick by eye after hard-reload:

[ ] Single title visible only — "QSB TOWER · 3D OPERATIONS COCKPIT"
[ ] Backend pill shows "backend v1.5"; no "V1.3" or "V1.4" elsewhere
[ ] BUILD BADGE "visible-cockpit-v1" still on top-center
[ ] LIFT COLUMN bottom-left with 9 readable lift cells
[ ] OPENCLAW ORB anchored to its current floor with ticket count
[ ] Voice selector dropdown in header (left of refresh button)
[ ] Voice meta pill shows "voice: en-GB" (or selected English voice)
[ ] Click 🔊 Test → hears English voice (not German)
[ ] Open ?floor=55 → Penthouse panel with gauges + zones + repair board
[ ] Open ?floor=42 → Binance panel with 6 rooms + 8 workers
[ ] Open ?floor=41 → OANDA panel with prices, open trades, PnL
[ ] In Kernel chat, ask "what is floor 41 doing right now?" — reply is Floor 41 specifics, NOT identity paragraph
[ ] In Kernel chat, ask "who are you?" — reply IS the identity paragraph
[ ] No decorative random dots/particles moving in Penthouse
MANUAL

python3 - <<PYEOF
import json, time
open("${REG_OUT}", "w").write(json.dumps({
  "ok": True,
  "kind": "qsb_browser_visible_reality_check",
  "phase": "QSB_KERNEL_CHAT_PENTHOUSE_AND_3D_DASHBOARD_REALITY_FIX_V1",
  "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
  "passed": ${pass}, "total": ${total},
  "automated_score": float(${score}),
  "failed": "${failed}".strip().split() if "${failed}".strip() else [],
  "manual_visual_required": True,
  "automation_can_only_verify_html_and_payloads": True,
  "execution_allowed": False,
  "real_money_live_trading_enabled": False,
  "openclaw_real_tool_execution_enabled": False,
}, indent=2))
PYEOF

echo "score=${score} (${pass}/${total})"
