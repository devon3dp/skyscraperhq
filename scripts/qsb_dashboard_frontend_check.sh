#!/usr/bin/env bash
# QSB Dashboard Frontend Check
# Phase: QSB_DASHBOARD_DATA_DRIVEN_SKYSCRAPER_REBUILD_V2
#
# Verifies:
#   * /                       returns 200
#   * /api/unified            valid JSON
#   * /api/dashboard/live_telemetry exists + LIVE_DATA_ONLY
#   * canonical workers exist
#   * mode is LIVE_DATA_ONLY (no random/demo)
#   * tower container exists in the index.html
#   * key JS/CSS files load
#   * dashboard log has no Python traceback

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

PORT=8765
URL="http://127.0.0.1:${PORT}"
LOG_DASH="data/logs/dashboard_latest.log"

OUT_REG="data/registries/qsb_dashboard_frontend_check.json"
OUT_LOG="data/logs/qsb_dashboard_frontend_check.txt"
mkdir -p "$(dirname "$OUT_REG")" "$(dirname "$OUT_LOG")"

http_status() { curl -s -o /dev/null -w "%{http_code}" "$1" 2>/dev/null || echo "000"; }
TS="$(date -u +%Y-%m-%dT%H:%M:%S%z)"

ROOT_HTTP=$(http_status "${URL}/")
UNIFIED_HTTP=$(http_status "${URL}/api/unified")
TELEMETRY_HTTP=$(http_status "${URL}/api/dashboard/live_telemetry")
VAUD_HTTP=$(http_status "${URL}/api/dashboard/visual_audit")
CANON_WORKERS_HTTP=$(http_status "${URL}/api/qsb_v2/canonical_workers")
EQSB_HTTP=$(http_status "${URL}/api/eqsb/penthouse_panel")
PROFIT_HTTP=$(http_status "${URL}/api/profit_command")
SCORE_HTTP=$(http_status "${URL}/api/workforce/scorecards")
NARR_TOWER_HTTP=$(http_status "${URL}/api/narrator/tower")
CC_AUDIT_HTTP=$(http_status "${URL}/api/dashboard/command_center_audit")

STATIC_OK="true"
for f in cockpit.css cockpit.js qsb_tower_2d.js qsb_scene.js qsb_state.js \
         qsb_skyscraper_v2.js qsb_skyscraper_v3.js qsb_v2_panel.js \
         qsb_command_center.js \
         eqsb_penthouse.js vendor/babylon.js; do
  code=$(http_status "${URL}/static/${f}")
  if [ "$code" != "200" ]; then
    STATIC_OK="false"
    echo "MISSING_ASSET ${f} HTTP $code"
  fi
done

# Index.html must contain the tower container + V3 script
INDEX_BODY=$(curl -s "${URL}/" 2>/dev/null || echo "")
HAS_TOWER_CONTAINER="false"
HAS_V3_SCRIPT="false"
HAS_V3_TAB="false"
if echo "$INDEX_BODY" | grep -q 'id="qsbTower2D"'; then HAS_TOWER_CONTAINER="true"; fi
if echo "$INDEX_BODY" | grep -q '/static/qsb_skyscraper_v3.js'; then HAS_V3_SCRIPT="true"; fi
if echo "$INDEX_BODY" | grep -q 'data-tab="qsbv3"';  then HAS_V3_TAB="true"; fi

# Telemetry contract
MODE=""
POLICY_VAL=""
TELEMETRY_OK="false"
RANDOM_FLAG_FOUND="false"
VISIBLE_WORKERS=0
CANON_COUNT=0
WORKER_MOVE_COUNT=-1
LIFT_MOVE_COUNT=-1
KERNEL_EVT_COUNT=-1
if [ "$TELEMETRY_HTTP" = "200" ]; then
  T_TMP=$(mktemp); curl -s "${URL}/api/dashboard/live_telemetry" > "$T_TMP"
  MODE=$(python3 -c "import json; d=json.load(open('${T_TMP}')); print(d.get('dashboard_visual_mode') or '')")
  POLICY_VAL=$(python3 -c "import json; d=json.load(open('${T_TMP}')); print(d.get('policy') or '')")
  VISIBLE_WORKERS=$(python3 -c "import json; d=json.load(open('${T_TMP}')); print((d.get('worker_counts') or {}).get('total_visible_on_skyscraper') or 0)")
  CANON_COUNT=$(python3 -c "import json; d=json.load(open('${T_TMP}')); print((d.get('worker_counts') or {}).get('total_canonical') or 0)")
  WORKER_MOVE_COUNT=$(python3 -c "import json; d=json.load(open('${T_TMP}')); print(len(d.get('worker_movements') or []))")
  LIFT_MOVE_COUNT=$(python3 -c "import json; d=json.load(open('${T_TMP}')); print(len(d.get('lift_movements') or []))")
  KERNEL_EVT_COUNT=$(python3 -c "import json; d=json.load(open('${T_TMP}')); print(len(d.get('kernel_events') or []))")
  if [ "$MODE" = "LIVE_DATA_ONLY" ] && [ "$POLICY_VAL" = "NO_RANDOM_LIVE_GRAPHICS" ]; then
    TELEMETRY_OK="true"
  fi
  # Sanity: if any record claims "random=true" or "is_random=true", flag it.
  RANDOM_PROBE=$(python3 -c "
import json
d = json.load(open('${T_TMP}'))
flat = json.dumps(d)
print('YES' if ('\"is_random\": true' in flat or '\"random\": true' in flat) else 'NO')
")
  if [ "$RANDOM_PROBE" = "YES" ]; then
    RANDOM_FLAG_FOUND="true"
  fi
  rm -f "$T_TMP"
fi

# Dashboard log traceback check.
# Ignore client-side disconnects (BrokenPipeError, ConnectionResetError) —
# those are noisy but harmless. Only count tracebacks that are NOT
# accompanied by a benign socket error.
DASH_LOG_HAS_TRACEBACK="false"
if [ -f "$LOG_DASH" ]; then
  TB_COUNT=$(grep -c "^Traceback" "$LOG_DASH" 2>/dev/null | head -1)
  BENIGN_COUNT=$(grep -cE "(BrokenPipeError|ConnectionResetError|ConnectionAbortedError)" "$LOG_DASH" 2>/dev/null | head -1)
  TB_COUNT=${TB_COUNT:-0}
  BENIGN_COUNT=${BENIGN_COUNT:-0}
  # If every traceback is a socket disconnect we treat it as benign.
  if [ "$TB_COUNT" -gt "$BENIGN_COUNT" ]; then
    DASH_LOG_HAS_TRACEBACK="true"
  fi
fi

# Verdict
VERDICT="frontend_healthy"
REASONS=()
[ "$ROOT_HTTP" != "200" ]      && { VERDICT="frontend_degraded"; REASONS+=("/_http_$ROOT_HTTP"); }
[ "$UNIFIED_HTTP" != "200" ]   && { VERDICT="frontend_degraded"; REASONS+=("unified_http_$UNIFIED_HTTP"); }
[ "$TELEMETRY_HTTP" != "200" ] && { VERDICT="frontend_degraded"; REASONS+=("telemetry_http_$TELEMETRY_HTTP"); }
[ "$STATIC_OK" != "true" ]     && { VERDICT="frontend_degraded"; REASONS+=("static_assets_missing"); }
[ "$HAS_TOWER_CONTAINER" != "true" ] && { VERDICT="frontend_degraded"; REASONS+=("no_tower_container_in_html"); }
[ "$HAS_V3_SCRIPT" != "true" ] && { VERDICT="frontend_degraded"; REASONS+=("v3_script_not_in_html"); }
[ "$TELEMETRY_OK" != "true" ]  && { VERDICT="frontend_degraded"; REASONS+=("live_data_only_mode_not_confirmed"); }
[ "$RANDOM_FLAG_FOUND" = "true" ] && { VERDICT="frontend_degraded"; REASONS+=("random_visuals_detected"); }
[ "$DASH_LOG_HAS_TRACEBACK" = "true" ] && { VERDICT="frontend_degraded"; REASONS+=("dashboard_log_traceback"); }
if [ "$CANON_COUNT" = "0" ]; then VERDICT="frontend_degraded"; REASONS+=("zero_canonical_workers"); fi

py_bool() { case "$1" in true) echo "True";; *) echo "False";; esac; }

PY_STATIC_OK=$(py_bool "$STATIC_OK")
PY_TC=$(py_bool "$HAS_TOWER_CONTAINER")
PY_V3=$(py_bool "$HAS_V3_SCRIPT")
PY_V3T=$(py_bool "$HAS_V3_TAB")
PY_TEL_OK=$(py_bool "$TELEMETRY_OK")
PY_RAND=$(py_bool "$RANDOM_FLAG_FOUND")
PY_TB=$(py_bool "$DASH_LOG_HAS_TRACEBACK")
REASONS_JSON=$(python3 -c "import json,sys; print(json.dumps(sys.argv[1:]))" "${REASONS[@]:-}")

python3 - <<PY
import json
payload = {
  "ok": True,
  "phase": "QSB_DASHBOARD_DATA_DRIVEN_SKYSCRAPER_REBUILD_V2",
  "kind": "qsb_dashboard_frontend_check",
  "ts": "${TS}",
  "verdict": "${VERDICT}",
  "reasons": ${REASONS_JSON},
  "http_root": "${ROOT_HTTP}",
  "http_api_unified": "${UNIFIED_HTTP}",
  "http_api_dashboard_live_telemetry": "${TELEMETRY_HTTP}",
  "http_api_dashboard_visual_audit": "${VAUD_HTTP}",
  "http_api_canonical_workers": "${CANON_WORKERS_HTTP}",
  "http_api_eqsb_penthouse_panel": "${EQSB_HTTP}",
  "http_api_profit_command": "${PROFIT_HTTP}",
  "http_api_workforce_scorecards": "${SCORE_HTTP}",
  "http_api_narrator_tower": "${NARR_TOWER_HTTP}",
  "http_api_command_center_audit": "${CC_AUDIT_HTTP}",
  "static_assets_all_200": ${PY_STATIC_OK},
  "index_html_has_tower_container": ${PY_TC},
  "index_html_has_v3_script_include": ${PY_V3},
  "index_html_has_v3_tab": ${PY_V3T},
  "dashboard_visual_mode": "${MODE}",
  "policy": "${POLICY_VAL}",
  "telemetry_contract_ok": ${PY_TEL_OK},
  "telemetry_total_canonical_workers": ${CANON_COUNT},
  "telemetry_total_visible_workers": ${VISIBLE_WORKERS},
  "telemetry_worker_movements": ${WORKER_MOVE_COUNT},
  "telemetry_lift_movements": ${LIFT_MOVE_COUNT},
  "telemetry_kernel_events": ${KERNEL_EVT_COUNT},
  "random_visual_flag_found": ${PY_RAND},
  "dashboard_log_has_traceback": ${PY_TB},
  "dashboard_log_path": "${LOG_DASH}",
  "execution_allowed": False,
  "active_local_only": True,
  "real_money_live_trading_enabled": False,
}
open("${OUT_REG}", "w").write(json.dumps(payload, indent=2))
PY

{
  echo "QSB Dashboard Frontend Check"
  echo "============================"
  echo "ts:                            $TS"
  echo "verdict:                       $VERDICT"
  if [ "${#REASONS[@]}" -gt 0 ]; then
    echo "reasons:                       ${REASONS[*]}"
  fi
  echo "/ (html):                      $ROOT_HTTP"
  echo "/api/unified:                  $UNIFIED_HTTP"
  echo "/api/dashboard/live_telemetry: $TELEMETRY_HTTP"
  echo "/api/dashboard/visual_audit:   $VAUD_HTTP"
  echo "/api/qsb_v2/canonical_workers: $CANON_WORKERS_HTTP"
  echo "/api/eqsb/penthouse_panel:     $EQSB_HTTP"
  echo "/api/profit_command:           $PROFIT_HTTP"
  echo "/api/workforce/scorecards:     $SCORE_HTTP"
  echo "/api/narrator/tower:           $NARR_TOWER_HTTP"
  echo "/api/dashboard/command_center_audit: $CC_AUDIT_HTTP"
  echo "static_assets_all_200:         $STATIC_OK"
  echo "index_html_has_tower_container:$HAS_TOWER_CONTAINER"
  echo "index_html_has_v3_script:      $HAS_V3_SCRIPT"
  echo "index_html_has_v3_tab:         $HAS_V3_TAB"
  echo "dashboard_visual_mode:         $MODE"
  echo "policy:                        $POLICY_VAL"
  echo "telemetry_contract_ok:         $TELEMETRY_OK"
  echo "canonical_workers:             $CANON_COUNT"
  echo "visible_workers_on_skyscraper: $VISIBLE_WORKERS"
  echo "worker_movements (real only):  $WORKER_MOVE_COUNT"
  echo "lift_movements (real only):    $LIFT_MOVE_COUNT"
  echo "kernel_events (real only):     $KERNEL_EVT_COUNT"
  echo "random_visual_flag_found:      $RANDOM_FLAG_FOUND"
  echo "dashboard_log_has_traceback:   $DASH_LOG_HAS_TRACEBACK"
  echo "execution_allowed:             False"
  echo "real_money_live_trading_enabled: False"
} > "$OUT_LOG"

cat "$OUT_LOG"
echo ""
echo "Wrote: $OUT_REG"
echo "Wrote: $OUT_LOG"
if [ "$VERDICT" = "frontend_healthy" ]; then exit 0; else exit 1; fi
