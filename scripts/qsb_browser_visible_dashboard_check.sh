#!/usr/bin/env bash
# QSB Browser-Visible Dashboard Check
# Phase: QSB_DASHBOARD_VISIBLE_REALITY_REBUILD_V1
#
# Does NOT pass from JSON alone. Fetches the actual HTML the browser
# would receive and checks for visible-cockpit markers + asset
# inclusion. Also fetches Floor 42 interior payload to confirm it has
# real rooms+workers, not the previous 2-worker stub.
#
# Output: pass/fail per check + manual visual checklist printed at end.

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

URL="http://127.0.0.1:8765"
REG_OUT="data/registries/qsb_browser_visible_dashboard_check.json"
LOG_OUT="data/logs/qsb_browser_visible_dashboard_check.txt"

mkdir -p "$(dirname "$LOG_OUT")"

pass=0; total=0; failed=""
check() {
  total=$((total + 1))
  if [ "$2" = "1" ]; then pass=$((pass + 1)); echo "  ✓ $1 — $3" | tee -a "$LOG_OUT"
  else failed="$failed $1"; echo "  ✗ $1 — $3" | tee -a "$LOG_OUT"; fi
}

: > "$LOG_OUT"
echo "QSB Browser-Visible Dashboard Check · $(date -u +%FT%TZ)" | tee -a "$LOG_OUT"
echo "phase: QSB_DASHBOARD_VISIBLE_REALITY_REBUILD_V1" | tee -a "$LOG_OUT"
echo "" | tee -a "$LOG_OUT"
echo "--- HTML INSPECTION ---" | tee -a "$LOG_OUT"

HTML=$(curl -s "${URL}/")

# 1. Single unified title
SINGLE_TITLE=$(echo "$HTML" | grep -c "QSB Tower — 3D Operations Cockpit")
check single_title_present "$([ "$SINGLE_TITLE" -ge 1 ] && echo 1 || echo 0)" "title=$SINGLE_TITLE"

# 2. No duplicate V1.3 visible branding
DUP_V13=$(echo "$HTML" | grep -cE "TOWER V1\.3|Tower V1\.3 — 3D")
check no_duplicate_v13 "$([ "$DUP_V13" = "0" ] && echo 1 || echo 0)" "v1.3 occurrences in served HTML=$DUP_V13"

# 3. No duplicate V1.4 visible branding (the proBanner injection no longer says V1.4)
DUP_V14=$(echo "$HTML" | grep -cE "TOWER V1\.4|Tower V1\.4")
check no_duplicate_v14_in_html "$([ "$DUP_V14" = "0" ] && echo 1 || echo 0)" "v1.4 occurrences in served HTML=$DUP_V14"

# 4. Unified header h-title
HDR_NEW=$(echo "$HTML" | grep -c "QSB TOWER · 3D OPERATIONS COCKPIT")
check unified_header_title "$([ "$HDR_NEW" = "1" ] && echo 1 || echo 0)" "hdr-title matches=$HDR_NEW"

# 5. Backend version label distinct from dashboard build
BACKEND_LABEL=$(echo "$HTML" | grep -c 'id="hdrBackend"')
check backend_label_present "$([ "$BACKEND_LABEL" = "1" ] && echo 1 || echo 0)" "hdrBackend id=$BACKEND_LABEL"

# 6. qsb_visible_dashboard.js loaded
SCRIPT=$(echo "$HTML" | grep -c "qsb_visible_dashboard.js")
check visible_script_included "$([ "$SCRIPT" -ge 1 ] && echo 1 || echo 0)" "script tag=$SCRIPT"

# 7. qsb_visible_dashboard.css loaded
CSS=$(echo "$HTML" | grep -c "qsb_visible_dashboard.css")
check visible_css_included "$([ "$CSS" -ge 1 ] && echo 1 || echo 0)" "link tag=$CSS"

# 8. Assets serve 200
JS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${URL}/static/qsb_visible_dashboard.js")
CSS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${URL}/static/qsb_visible_dashboard.css")
check visible_js_200 "$([ "$JS_CODE" = "200" ] && echo 1 || echo 0)" "js http=$JS_CODE"
check visible_css_200 "$([ "$CSS_CODE" = "200" ] && echo 1 || echo 0)" "css http=$CSS_CODE"

echo "" | tee -a "$LOG_OUT"
echo "--- DATA AVAILABILITY FOR VISIBLE LAYER ---" | tee -a "$LOG_OUT"

# 9. Lift scene state has 9 lifts (drives the always-on lift column)
LIFTS=$(curl -s "${URL}/api/dashboard/lift_scene_state" | python3 -c "import json,sys;print(json.load(sys.stdin).get('lift_count',0))" 2>/dev/null || echo 0)
check lifts_9 "$([ "$LIFTS" = "9" ] && echo 1 || echo 0)" "lift_count=$LIFTS"

# 10. OpenClaw route has current_floor (drives the orb position)
OC_FLOOR=$(curl -s "${URL}/api/openclaw/route" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('current_floor',''))" 2>/dev/null || echo "")
check openclaw_route "$([ -n "$OC_FLOOR" ] && echo 1 || echo 0)" "current_floor=$OC_FLOOR"

# 11. Floor 42 interior has rooms (drives the Binance panel)
F42_ROOMS=$(curl -s "${URL}/api/dashboard/floor42_binance_interior" | python3 -c "import json,sys;print(len(json.load(sys.stdin).get('rooms',[])))" 2>/dev/null || echo 0)
check floor42_has_rooms "$([ "$F42_ROOMS" -ge 4 ] && echo 1 || echo 0)" "floor_42_rooms=$F42_ROOMS"

# 12. Floor 42 interior has workers
F42_WK=$(curl -s "${URL}/api/dashboard/floor42_binance_interior" | python3 -c "import json,sys;print(len(json.load(sys.stdin).get('workers',[])))" 2>/dev/null || echo 0)
check floor42_has_workers "$([ "$F42_WK" -ge 5 ] && echo 1 || echo 0)" "floor_42_workers=$F42_WK"

# 13. Selected floor URL param recognized
URL_PARAM_OK=$(curl -s "${URL}/api/dashboard/selected_floor_state_audit" | python3 -c "import json,sys;print('1' if json.load(sys.stdin).get('url_param_recognized') else '0')" 2>/dev/null || echo 0)
check url_param_recognized "$URL_PARAM_OK" "url floor=N parses on boot"

# 14. Worker scene state populated for tower density
WS=$(curl -s "${URL}/api/dashboard/worker_scene_state" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('canonical_total',0))" 2>/dev/null || echo 0)
check worker_density_source "$([ "$WS" -ge 100 ] && echo 1 || echo 0)" "canonical_total=$WS"

# 15. Floor 42 page loads
PAGE=$(curl -s -o /dev/null -w "%{http_code}" "${URL}/?v=unified&floor=42")
check floor_42_page_200 "$([ "$PAGE" = "200" ] && echo 1 || echo 0)" "http=$PAGE"

# 16. Identity cleanup registry present
ID_CLEAN=$(curl -s "${URL}/api/dashboard/identity_cleanup" | python3 -c "import json,sys;print('1' if json.load(sys.stdin).get('ok') else '0')" 2>/dev/null || echo 0)
check identity_cleanup_logged "$ID_CLEAN" "registry present"

score=$(python3 -c "print(round(100.0 * $pass / $total, 1))")
echo "" | tee -a "$LOG_OUT"
echo "score: ${score} (${pass}/${total})" | tee -a "$LOG_OUT"
echo "failed:${failed:-none}" | tee -a "$LOG_OUT"
echo "" | tee -a "$LOG_OUT"

cat <<'MANUAL' | tee -a "$LOG_OUT"
--- MANUAL VISUAL CHECKLIST (open browser at /?v=unified&floor=42) ---
Browser-only items — the script CANNOT verify these without a headless
browser. Reader must confirm by eye:

[ ] One title only: "QSB TOWER · 3D OPERATIONS COCKPIT"
[ ] No "V1.3" or "V1.4" anywhere on screen except the small backend pill
[ ] BUILD BADGE "visible-cockpit-v1" visible top-center
[ ] LEFT LIFT COLUMN: 9 lift cells, each readable, status MOVING/IDLE
[ ] OPENCLAW ORB: purple glowing orb near a slab; label shows floor
[ ] Selected floor (42) has a yellow ring around its SVG slab
[ ] FLOOR 42 BINANCE panel opens with 6 rooms + 8 workers
[ ] No "Click a floor" placeholder when ?floor=42 in URL
[ ] No random repeating worker loops (motion only from cadence)
MANUAL

python3 - <<PYEOF
import json, time
open("${REG_OUT}", "w").write(json.dumps({
  "ok": True,
  "kind": "qsb_browser_visible_dashboard_check",
  "phase": "QSB_DASHBOARD_VISIBLE_REALITY_REBUILD_V1",
  "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
  "passed": ${pass}, "total": ${total},
  "score": float(${score}),
  "failed": "${failed}".strip().split() if "${failed}".strip() else [],
  "manual_visual_required": True,
  "automation_can_only_verify_html_state_and_payloads": True,
  "execution_allowed": False,
  "real_money_live_trading_enabled": False,
  "openclaw_real_tool_execution_enabled": False,
}, indent=2))
PYEOF

echo "score=${score} (${pass}/${total})"
