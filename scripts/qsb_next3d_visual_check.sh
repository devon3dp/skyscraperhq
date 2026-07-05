#!/usr/bin/env bash
# QSB Next3D Visual Check
# Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
#
# Verifies the new route serves a fresh build, all next3d assets load,
# the build badge is in the served HTML, and the chosen engine
# (Babylon) is wired. Uses headless Chrome to capture screenshots when
# google-chrome is available — those are the closest thing to "visible
# proof" automation can produce without a full Playwright stack.

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

URL=http://127.0.0.1:8765
REG_OUT=data/registries/qsb_next3d_visual_check.json
LOG_OUT=data/logs/qsb_next3d_visual_check.txt
SHOT_DIR=data/screenshots
mkdir -p "$SHOT_DIR" "$(dirname "$LOG_OUT")"

pass=0; total=0; failed=""
check() {
  total=$((total + 1))
  if [ "$2" = "1" ]; then pass=$((pass + 1)); echo "  ✓ $1 — $3" | tee -a "$LOG_OUT"
  else failed="$failed $1"; echo "  ✗ $1 — $3" | tee -a "$LOG_OUT"; fi
}

: > "$LOG_OUT"
echo "QSB Next3D Visual Check · $(date -u +%FT%TZ)" | tee -a "$LOG_OUT"
echo "phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1" | tee -a "$LOG_OUT"
echo "" | tee -a "$LOG_OUT"

# 1. Next3D route loads
PAGE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/next3d")
check next3d_path_200 "$([ "$PAGE" = "200" ] && echo 1 || echo 0)" "http=$PAGE"

QPAGE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/?v=next3d")
check next3d_query_200 "$([ "$QPAGE" = "200" ] && echo 1 || echo 0)" "http=$QPAGE"

# 2. Served HTML carries the next3d build marker
HTML=$(curl -s "$URL/?v=next3d")
BADGE=$(echo "$HTML" | grep -c "next3d-v1")
check next3d_build_marker "$([ "$BADGE" -ge 1 ] && echo 1 || echo 0)" "build_tag_matches=$BADGE"
TITLE=$(echo "$HTML" | grep -c "QSB TOWER · NEXT3D COCKPIT")
check next3d_unique_title "$([ "$TITLE" = "1" ] && echo 1 || echo 0)" "matches=$TITLE"
OLD_DUP=$(echo "$HTML" | grep -cE "QSB TOWER V1\.3|QSB TOWER V1\.4")
check no_old_cockpit_title "$([ "$OLD_DUP" = "0" ] && echo 1 || echo 0)" "old_strings=$OLD_DUP"

# 3. Babylon engine selected
ENG=$(echo "$HTML" | grep -c "/static/vendor/babylon.js")
check babylon_engine_selected "$([ "$ENG" -ge 1 ] && echo 1 || echo 0)" "babylon vendor included=$ENG"

# 4. All 13 next3d assets serve 200
NX_FAIL=0
for f in index.html next3d.css next3d_telemetry.js next3d_camera.js next3d_tower.js next3d_lifts.js next3d_workers.js next3d_openclaw.js next3d_floors.js next3d_interiors.js next3d_hud.js next3d_scene.js next3d_app.js; do
  c=$(curl -s -o /dev/null -w '%{http_code}' "$URL/static/next3d/$f")
  [ "$c" = "200" ] || NX_FAIL=$((NX_FAIL+1))
done
check all_next3d_assets_200 "$([ "$NX_FAIL" = "0" ] && echo 1 || echo 0)" "fail_count=$NX_FAIL"

# 5. Backend data sources reachable
LIFTS=$(curl -s "$URL/api/dashboard/lift_scene_state" | python3 -c "import json,sys;print(json.load(sys.stdin).get('lift_count',0))" 2>/dev/null || echo 0)
check lifts_data_available "$([ "$LIFTS" = "9" ] && echo 1 || echo 0)" "lift_count=$LIFTS"

WS=$(curl -s "$URL/api/dashboard/worker_scene_state" | python3 -c "import json,sys;print(json.load(sys.stdin).get('canonical_total',0))" 2>/dev/null || echo 0)
check workers_data_available "$([ "$WS" -ge 1000 ] && echo 1 || echo 0)" "canonical_workers=$WS"

OCF=$(curl -s "$URL/api/openclaw/route" | python3 -c "import json,sys;print(json.load(sys.stdin).get('current_floor',''))" 2>/dev/null || echo "")
check openclaw_route_available "$([ -n "$OCF" ] && echo 1 || echo 0)" "openclaw_floor=$OCF"

F41=$(curl -s "$URL/api/trading/oanda/floor41/pnl" | python3 -c "import json,sys;d=json.load(sys.stdin);print('1' if 'total_pnl' in d else '0')" 2>/dev/null || echo 0)
check floor41_pnl_available "$F41" "pnl_present=$F41"

F42=$(curl -s "$URL/api/dashboard/floor42_binance_interior" | python3 -c "import json,sys;print(len(json.load(sys.stdin).get('rooms',[])))" 2>/dev/null || echo 0)
check floor42_interior_available "$([ "$F42" -ge 4 ] && echo 1 || echo 0)" "floor42_rooms=$F42"

PH=$(curl -s "$URL/api/dashboard/penthouse_gauges" | python3 -c "import json,sys;print(json.load(sys.stdin).get('gauge_count',0))" 2>/dev/null || echo 0)
check penthouse_gauges_available "$([ "$PH" -ge 8 ] && echo 1 || echo 0)" "gauge_count=$PH"

# 6. Legacy fallback still works
LEG=$(curl -s -o /dev/null -w "%{http_code}" "$URL/?v=unified")
check legacy_fallback_alive "$([ "$LEG" = "200" ] && echo 1 || echo 0)" "http=$LEG"

# 7. Headless Chrome screenshots
SHOT_OK=0; SHOT_FAIL=""
if command -v google-chrome >/dev/null 2>&1; then
  for f in 55 41 42; do
    OUT="$SHOT_DIR/qsb_next3d_floor${f}.png"
    rm -f "$OUT"
    timeout 12 google-chrome --headless --disable-gpu --no-sandbox \
      --window-size=1600,900 \
      --virtual-time-budget=6000 \
      --screenshot="$OUT" \
      "$URL/?v=next3d&floor=${f}" >/dev/null 2>&1 || true
    if [ -f "$OUT" ] && [ "$(stat -c%s "$OUT" 2>/dev/null || echo 0)" -gt 8000 ]; then
      SHOT_OK=$((SHOT_OK+1))
    else
      SHOT_FAIL="$SHOT_FAIL $f"
    fi
  done
  check screenshots_captured "$([ "$SHOT_OK" = "3" ] && echo 1 || echo 0)" "captured=$SHOT_OK / 3 missing:$SHOT_FAIL"
else
  echo "  (Chrome not found — skipping screenshots)" | tee -a "$LOG_OUT"
fi

score=$(python3 -c "print(round(100.0 * $pass / $total, 1))")
echo "" | tee -a "$LOG_OUT"
echo "automated score: ${score} (${pass}/${total})" | tee -a "$LOG_OUT"
echo "failed:${failed:-none}" | tee -a "$LOG_OUT"
echo "" | tee -a "$LOG_OUT"
echo "screenshots: $SHOT_DIR/*.png" | tee -a "$LOG_OUT"

cat <<'MANUAL' | tee -a "$LOG_OUT"

--- MANUAL VISUAL CHECKLIST (open browser to confirm) ---
[ ] http://127.0.0.1:8765/?v=next3d&floor=55 loads
[ ] Top-right neon NEXT3D · V1 · GREENFIELD badge visible
[ ] Title "QSB TOWER · NEXT3D COCKPIT" (no V1.3 / V1.4)
[ ] Babylon 3D tower visible (NOT the old SVG cockpit)
[ ] You can orbit (drag), zoom (wheel), pan (right-drag) the tower
[ ] Click a floor in the tower OR in the left roster → interior opens
[ ] 9 lift cars visible on the back-left, back-right, and behind tower
[ ] Lift cars move toward their telemetry floor (green when moving)
[ ] Purple OpenClaw orb orbits at OpenClaw's current_floor height
[ ] Floor 55 Penthouse interior shows real gauges
[ ] Floor 41 OANDA interior shows live prices, open/closed trades, PnL
[ ] Floor 42 Binance interior shows 6 rooms + 8 workers
[ ] Real-money OFF + OpenClaw exec OFF in footer
[ ] Legacy cockpit at /?v=unified still works
MANUAL

python3 - <<PYEOF
import json, time, os
shots = []
for f in (55, 41, 42):
    p = "${SHOT_DIR}/qsb_next3d_floor%d.png" % f
    if os.path.exists(p):
        shots.append({"floor": f, "path": p, "bytes": os.path.getsize(p)})
open("${REG_OUT}", "w").write(json.dumps({
  "ok": True,
  "kind": "qsb_next3d_visual_check",
  "phase": "QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1",
  "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
  "passed": ${pass}, "total": ${total},
  "automated_score": float(${score}),
  "failed": "${failed}".strip().split() if "${failed}".strip() else [],
  "screenshots": shots,
  "screenshot_tool": "google-chrome --headless",
  "manual_visual_required": True,
  "execution_allowed": False,
  "real_money_live_trading_enabled": False,
  "openclaw_real_tool_execution_enabled": False,
}, indent=2))
PYEOF
echo "score=${score} (${pass}/${total})"
