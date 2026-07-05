#!/usr/bin/env bash
# QSB Tower — Dashboard Health Check
# Phase: QSB_V2_FULL_SYSTEM_RECHECK_AND_DASHBOARD_REPAIR_V1
#
# Read-only. Verifies the dashboard is reachable and that the key
# endpoints + static assets return 2xx. Never enables execution.
# Writes:
#   data/registries/qsb_v2_full_system_recheck.json
#   data/logs/qsb_v2_full_system_recheck.txt

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

PORT=8765
URL="http://127.0.0.1:${PORT}"
OUT_REG="data/registries/qsb_v2_full_system_recheck.json"
OUT_LOG="data/logs/qsb_v2_full_system_recheck.txt"
mkdir -p "$(dirname "$OUT_REG")" "$(dirname "$OUT_LOG")"

TS="$(date -u +%Y-%m-%dT%H:%M:%S%z)"

# ── Probes (shell + curl) ────────────────────────────────────────────
PORT_LISTENING="false"
if ss -tln 2>/dev/null | grep -q ":${PORT} " ; then PORT_LISTENING="true"; fi

PID_RUNNING="false"
PID_FILE="data/runtime/dashboard.pid"
PID=""
if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || echo "")"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then PID_RUNNING="true"; fi
fi

http_status() {
  curl -s -o /dev/null -w "%{http_code}" "$1" || echo "000"
}

HTML_CODE=$(http_status "${URL}/")
UNIFIED_CODE=$(http_status "${URL}/api/unified")
EQSB_INTRO_CODE=$(http_status "${URL}/api/eqsb/introspection")
EQSB_PENT_CODE=$(http_status "${URL}/api/eqsb/penthouse_panel")
V2_PEN_CODE=$(http_status "${URL}/api/qsb_v2/penthouse_combined")
V2_OC_CODE=$(http_status "${URL}/api/qsb_v2/openclaw_state")
V2_PT_CODE=$(http_status "${URL}/api/qsb_v2/open_paper_trades")
V2_WK_CODE=$(http_status "${URL}/api/qsb_v2/canonical_workers")
V2_RC_CODE=$(http_status "${URL}/api/qsb_v2/worker_count_reconciliation")
V2_LR_CODE=$(http_status "${URL}/api/qsb_v2/trade_learning")
V2_SS_CODE=$(http_status "${URL}/api/qsb_v2/skyscraper_status")
STATIC_INDEX_CODE=$(http_status "${URL}/static/cockpit.css")
STATIC_TOWER2D_CODE=$(http_status "${URL}/static/qsb_tower_2d.js")
STATIC_SCENE_CODE=$(http_status "${URL}/static/qsb_scene.js")
STATIC_COCKPIT_CODE=$(http_status "${URL}/static/cockpit.js")
STATIC_EQSB_JS=$(http_status "${URL}/static/eqsb_penthouse.js")
STATIC_V2_OVERLAY=$(http_status "${URL}/static/qsb_skyscraper_v2.js")
STATIC_V2_PANEL=$(http_status "${URL}/static/qsb_v2_panel.js")
STATIC_BABYLON=$(http_status "${URL}/static/vendor/babylon.js")

# ── /api/unified key checks via python -------------------------------------
UNIFIED_JSON_VALID="false"
HAS_KERNEL="false"; HAS_FLOORS="false"; HAS_QSB_V2="false"; HAS_EQSB_KEYS="false"
FLOOR_COUNT=0; QSB_V2_PHASE=""
if [ "$UNIFIED_CODE" = "200" ]; then
  UNIFIED_TMP=$(mktemp)
  curl -s "${URL}/api/unified" > "$UNIFIED_TMP"
  UNIFIED_JSON_VALID=$(python3 -c "
import json, sys
try:
    d = json.load(open('${UNIFIED_TMP}'))
    print('true')
except Exception:
    print('false')
")
  if [ "$UNIFIED_JSON_VALID" = "true" ]; then
    HAS_KERNEL=$(python3 -c "import json; d=json.load(open('${UNIFIED_TMP}')); print('true' if d.get('kernel') else 'false')")
    HAS_FLOORS=$(python3 -c "import json; d=json.load(open('${UNIFIED_TMP}')); print('true' if isinstance(d.get('floors'), list) and len(d['floors']) > 0 else 'false')")
    HAS_QSB_V2=$(python3 -c "import json; d=json.load(open('${UNIFIED_TMP}')); print('true' if d.get('qsb_v2') else 'false')")
    FLOOR_COUNT=$(python3 -c "import json; d=json.load(open('${UNIFIED_TMP}')); print(len(d.get('floors') or []))")
    QSB_V2_PHASE=$(python3 -c "import json; d=json.load(open('${UNIFIED_TMP}')); print((d.get('qsb_v2') or {}).get('phase') or '')")
  fi
  rm -f "$UNIFIED_TMP"
fi

EQSB_PENT_OK="false"
if [ "$EQSB_PENT_CODE" = "200" ]; then
  EQSB_TMP=$(mktemp)
  curl -s "${URL}/api/eqsb/penthouse_panel" > "$EQSB_TMP"
  EQSB_PENT_OK=$(python3 -c "
import json
try:
    d = json.load(open('${EQSB_TMP}'))
    print('true' if d.get('identity') else 'false')
except Exception:
    print('false')
")
  rm -f "$EQSB_TMP"
fi

V2_PEN_OK="false"
if [ "$V2_PEN_CODE" = "200" ]; then
  V2_TMP=$(mktemp)
  curl -s "${URL}/api/qsb_v2/penthouse_combined" > "$V2_TMP"
  V2_PEN_OK=$(python3 -c "
import json
try:
    d = json.load(open('${V2_TMP}'))
    ok = bool(d.get('openclaw') and d.get('paper_trading') and d.get('workers'))
    print('true' if ok else 'false')
except Exception:
    print('false')
")
  rm -f "$V2_TMP"
fi

# Verdict
if [ "$PORT_LISTENING" = "true" ] && [ "$HTML_CODE" = "200" ] \
   && [ "$UNIFIED_CODE" = "200" ] && [ "$UNIFIED_JSON_VALID" = "true" ] \
   && [ "$HAS_KERNEL" = "true" ] && [ "$HAS_FLOORS" = "true" ] \
   && [ "$HAS_QSB_V2" = "true" ] && [ "$STATIC_TOWER2D_CODE" = "200" ] \
   && [ "$STATIC_INDEX_CODE" = "200" ] && [ "$STATIC_COCKPIT_CODE" = "200" ]; then
  VERDICT="dashboard_healthy"
else
  VERDICT="dashboard_degraded"
fi

# Helper: convert lower-case shell bool ('true'/'false') to Python literal
py_bool() { case "$1" in true) echo "True";; *) echo "False";; esac; }

# ── Write registry JSON --------------------------------------------------
PY_PORT_LISTENING=$(py_bool "$PORT_LISTENING")
PY_PID_RUNNING=$(py_bool "$PID_RUNNING")
PY_UNIFIED_JSON_VALID=$(py_bool "$UNIFIED_JSON_VALID")
PY_HAS_KERNEL=$(py_bool "$HAS_KERNEL")
PY_HAS_FLOORS=$(py_bool "$HAS_FLOORS")
PY_HAS_QSB_V2=$(py_bool "$HAS_QSB_V2")
PY_EQSB_PENT_OK=$(py_bool "$EQSB_PENT_OK")
PY_V2_PEN_OK=$(py_bool "$V2_PEN_OK")

python3 - <<PY
import json
payload = {
  "ok": True,
  "phase": "QSB_V2_FULL_SYSTEM_RECHECK_AND_DASHBOARD_REPAIR_V1",
  "kind": "qsb_v2_full_system_recheck",
  "ts": "${TS}",
  "verdict": "${VERDICT}",
  "port": ${PORT},
  "port_listening": ${PY_PORT_LISTENING},
  "pid_file_present_and_running": ${PY_PID_RUNNING},
  "pid": "${PID}",
  "http_html_root": "${HTML_CODE}",
  "http_api_unified": "${UNIFIED_CODE}",
  "http_api_eqsb_introspection": "${EQSB_INTRO_CODE}",
  "http_api_eqsb_penthouse_panel": "${EQSB_PENT_CODE}",
  "http_api_qsb_v2_penthouse_combined": "${V2_PEN_CODE}",
  "http_api_qsb_v2_openclaw_state": "${V2_OC_CODE}",
  "http_api_qsb_v2_open_paper_trades": "${V2_PT_CODE}",
  "http_api_qsb_v2_canonical_workers": "${V2_WK_CODE}",
  "http_api_qsb_v2_worker_count_reconciliation": "${V2_RC_CODE}",
  "http_api_qsb_v2_trade_learning": "${V2_LR_CODE}",
  "http_api_qsb_v2_skyscraper_status": "${V2_SS_CODE}",
  "http_static_cockpit_css": "${STATIC_INDEX_CODE}",
  "http_static_cockpit_js": "${STATIC_COCKPIT_CODE}",
  "http_static_tower_2d_js": "${STATIC_TOWER2D_CODE}",
  "http_static_qsb_scene_js": "${STATIC_SCENE_CODE}",
  "http_static_eqsb_penthouse_js": "${STATIC_EQSB_JS}",
  "http_static_qsb_skyscraper_v2_js": "${STATIC_V2_OVERLAY}",
  "http_static_qsb_v2_panel_js": "${STATIC_V2_PANEL}",
  "http_static_vendor_babylon_js": "${STATIC_BABYLON}",
  "unified_json_valid": ${PY_UNIFIED_JSON_VALID},
  "unified_has_kernel": ${PY_HAS_KERNEL},
  "unified_has_floors": ${PY_HAS_FLOORS},
  "unified_floor_count": ${FLOOR_COUNT},
  "unified_has_qsb_v2": ${PY_HAS_QSB_V2},
  "unified_qsb_v2_phase": "${QSB_V2_PHASE}",
  "eqsb_penthouse_ok": ${PY_EQSB_PENT_OK},
  "qsb_v2_penthouse_ok": ${PY_V2_PEN_OK},
  "execution_allowed": False,
  "active_local_only": True,
  "real_money_live_trading_enabled": False,
}
open("${OUT_REG}", "w").write(json.dumps(payload, indent=2))
PY

# ── Human log -----------------------------------------------------------
{
  echo "QSB V2 Dashboard Health Check"
  echo "============================="
  echo "ts:                       $TS"
  echo "verdict:                  $VERDICT"
  echo "port_listening:           $PORT_LISTENING (port $PORT)"
  echo "pid_running:              $PID_RUNNING (pid $PID)"
  echo "/ (html):                 $HTML_CODE"
  echo "/api/unified:             $UNIFIED_CODE (json_valid=$UNIFIED_JSON_VALID kernel=$HAS_KERNEL floors=$HAS_FLOORS qsb_v2=$HAS_QSB_V2 floor_count=$FLOOR_COUNT)"
  echo "/api/eqsb/penthouse_panel:$EQSB_PENT_CODE (eqsb_panel_ok=$EQSB_PENT_OK)"
  echo "/api/qsb_v2/penthouse_combined: $V2_PEN_CODE (qsb_v2_ok=$V2_PEN_OK)"
  echo "/api/qsb_v2/openclaw_state:        $V2_OC_CODE"
  echo "/api/qsb_v2/open_paper_trades:     $V2_PT_CODE"
  echo "/api/qsb_v2/canonical_workers:     $V2_WK_CODE"
  echo "/api/qsb_v2/worker_count_reconciliation: $V2_RC_CODE"
  echo "/api/qsb_v2/trade_learning:        $V2_LR_CODE"
  echo "/api/qsb_v2/skyscraper_status:     $V2_SS_CODE"
  echo "/static/cockpit.css:               $STATIC_INDEX_CODE"
  echo "/static/cockpit.js:                $STATIC_COCKPIT_CODE"
  echo "/static/qsb_tower_2d.js:           $STATIC_TOWER2D_CODE"
  echo "/static/qsb_scene.js:              $STATIC_SCENE_CODE"
  echo "/static/eqsb_penthouse.js:         $STATIC_EQSB_JS"
  echo "/static/qsb_skyscraper_v2.js:      $STATIC_V2_OVERLAY"
  echo "/static/qsb_v2_panel.js:           $STATIC_V2_PANEL"
  echo "/static/vendor/babylon.js:         $STATIC_BABYLON"
  echo "execution_allowed:                 False"
  echo "real_money_live_trading_enabled:   False"
} > "$OUT_LOG"

cat "$OUT_LOG"
echo ""
echo "Wrote: $OUT_REG"
echo "Wrote: $OUT_LOG"
if [ "$VERDICT" = "dashboard_healthy" ]; then
  exit 0
else
  exit 1
fi
