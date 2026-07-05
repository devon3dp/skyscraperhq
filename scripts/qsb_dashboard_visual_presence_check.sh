#!/usr/bin/env bash
# QSB Dashboard Visual Presence Check
# Phase: QSB_RENDER_VISIBLE_WORKERS_AND_LIFTS_FIX_V1
#
# Verifies that the dashboard's rendering layer is actually wired to
# produce visible workers and lifts — not just 200-OK endpoints with
# empty payloads.

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

URL="http://127.0.0.1:8765"
REG_OUT="data/registries/qsb_dashboard_visual_presence_check.json"
LOG_OUT="data/logs/qsb_dashboard_visual_presence_check.txt"

mkdir -p "$(dirname "$LOG_OUT")"

pass=0
total=0
failed=""

check() {
  local name="$1"
  local result="$2"
  local detail="$3"
  total=$((total + 1))
  if [ "$result" = "1" ]; then
    pass=$((pass + 1))
    echo "  ✓ $name — $detail" >> "$LOG_OUT"
  else
    failed="$failed $name"
    echo "  ✗ $name — $detail" >> "$LOG_OUT"
  fi
}

: > "$LOG_OUT"
echo "QSB Dashboard Visual Presence Check · $(date -u +%FT%TZ)" >> "$LOG_OUT"
echo "phase: QSB_RENDER_VISIBLE_WORKERS_AND_LIFTS_FIX_V1" >> "$LOG_OUT"
echo "" >> "$LOG_OUT"

# 1. URL selectedFloor recognition
audit_pass=$(curl -s "${URL}/api/dashboard/selected_floor_state_audit" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print('1' if d.get('url_param_recognized') else '0')" 2>/dev/null || echo 0)
check "url_floor_recognized" "$audit_pass" "selected_floor_state_audit.url_param_recognized"

# 2. worker_scene_state present
ws_total=$(curl -s "${URL}/api/dashboard/worker_scene_state" \
  | python3 -c "import json,sys;print(json.load(sys.stdin).get('canonical_total',0))" 2>/dev/null || echo 0)
check "worker_scene_state_canonical_>0" "$([ "$ws_total" -gt 0 ] && echo 1 || echo 0)" "canonical_total=$ws_total"

# 3. selected floor workers (Floor 42) exist or clear no-data reason
f42=$(curl -s "${URL}/api/workforce/room_assignments" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
br = d.get('by_floor_room', {}) or {}
f42 = br.get('floor_42_binance_trading', {}) or {}
print(sum(len(v) for v in f42.values()))" 2>/dev/null || echo 0)
check "floor_42_has_workers" "$([ "$f42" -gt 0 ] && echo 1 || echo 0)" "floor_42_workers=$f42"

# 4. lift_scene_state has 9 lifts
lifts=$(curl -s "${URL}/api/dashboard/lift_scene_state" \
  | python3 -c "import json,sys;print(json.load(sys.stdin).get('lift_count',0))" 2>/dev/null || echo 0)
check "lift_scene_state_count_=_9" "$([ "$lifts" = "9" ] && echo 1 || echo 0)" "lift_count=$lifts"

# 5. lift render health
lhealth=$(curl -s "${URL}/api/dashboard/lift_render_health" \
  | python3 -c "import json,sys;print('1' if json.load(sys.stdin).get('all_lifts_visible') else '0')" 2>/dev/null || echo 0)
check "all_9_lifts_visible" "$lhealth" "all_lifts_visible=$lhealth"

# 6. render budget explanation
budget=$(curl -s "${URL}/api/dashboard/worker_render_budget" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print('1' if d.get('explanation') and d.get('selected_floor_individual_workers_cap') else '0')" 2>/dev/null || echo 0)
check "render_budget_explained" "$budget" "explanation_and_cap_present"

# 7. Floor 42 interior has slots/stations
stations_f42=$(curl -s "${URL}/api/workforce/station_assignments" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
st = d.get('stations', {}) or {}
print(sum(1 for r in st.values() if isinstance(r,dict) and 'floor_42' in str(r.get('floor',''))))" 2>/dev/null || echo 0)
check "floor_42_stations_>0" "$([ "$stations_f42" -gt 0 ] && echo 1 || echo 0)" "floor_42_stations=$stations_f42"

# 8. default mode is NOT counts_only
default_mode=$(curl -s "${URL}/api/dashboard/scene_state" \
  | python3 -c "import json,sys;print(json.load(sys.stdin).get('view_mode_default',''))" 2>/dev/null || echo "")
check "default_mode_not_counts_only" "$([ "$default_mode" != "counts_only" ] && echo 1 || echo 0)" "default=$default_mode"

# 9. OpenClaw scene state exists (route + role)
oc_floor=$(curl -s "${URL}/api/openclaw/route" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('current_floor',''))" 2>/dev/null || echo "")
check "openclaw_route_has_current_floor" "$([ -n "$oc_floor" ] && echo 1 || echo 0)" "current_floor=$oc_floor"

# 10. ?floor=42 page loads
page_code=$(curl -s -o /dev/null -w "%{http_code}" "${URL}/?v=unified&floor=42")
check "floor_42_page_loads" "$([ "$page_code" = "200" ] && echo 1 || echo 0)" "http=$page_code"

# 11. qsb_render_visible.js asset exists
asset_code=$(curl -s -o /dev/null -w "%{http_code}" "${URL}/static/qsb_render_visible.js")
check "render_visible_js_asset_200" "$([ "$asset_code" = "200" ] && echo 1 || echo 0)" "http=$asset_code"

# 12. Index includes script tag for qsb_render_visible.js
incl=$(curl -s "${URL}/" | grep -c "qsb_render_visible.js" || true)
check "index_includes_render_visible_script" "$([ "$incl" -gt 0 ] && echo 1 || echo 0)" "matches=$incl"

# 13. Lift scene state has at least 1 idle or moving record (i.e. populated)
lift_pop=$(curl -s "${URL}/api/dashboard/lift_scene_state" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d.get('lifts',[])))" 2>/dev/null || echo 0)
check "lift_records_populated" "$([ "$lift_pop" -ge 9 ] && echo 1 || echo 0)" "records=$lift_pop"

# 14. worker_render_health has default view explanation
defview=$(curl -s "${URL}/api/dashboard/worker_render_health" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('default_view',''))" 2>/dev/null || echo "")
check "render_health_describes_default_view" "$([ -n "$defview" ] && [ "$defview" != "counts_only" ] && echo 1 || echo 0)" "default_view=$defview"

# 15. safety locks closed
safe=$(curl -s "${URL}/api/dashboard/worker_render_health" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('1' if d.get('real_money_live_trading_enabled') is False and d.get('openclaw_real_tool_execution_enabled') is False else '0')" 2>/dev/null || echo 0)
check "safety_locks_closed" "$safe" "real_money + openclaw_exec both False"

score=$(python3 -c "print(round(100.0 * $pass / $total, 1))")
echo "" >> "$LOG_OUT"
echo "score: ${score} (${pass}/${total})" >> "$LOG_OUT"
echo "failed:${failed:-none}" >> "$LOG_OUT"

# Write JSON registry
python3 - <<PYEOF
import json, time
payload = {
  "ok": True,
  "kind": "qsb_dashboard_visual_presence_check",
  "phase": "QSB_RENDER_VISIBLE_WORKERS_AND_LIFTS_FIX_V1",
  "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
  "passed": ${pass},
  "total": ${total},
  "score": float(${score}),
  "is_100_complete": ${pass} == ${total},
  "failed": "${failed}".strip().split() if "${failed}".strip() else [],
  "execution_allowed": False,
  "active_local_only": True,
  "advisory_only": True,
  "real_money_live_trading_enabled": False,
  "openclaw_real_tool_execution_enabled": False,
}
open("${REG_OUT}", "w").write(json.dumps(payload, indent=2))
PYEOF

cat "$LOG_OUT"
echo ""
echo "score=${score} (${pass}/${total})"
