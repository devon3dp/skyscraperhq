#!/usr/bin/env bash
# QSB Floor 41 OANDA — Health Check
# Phase: QSB_FLOOR_41_OANDA_FULL_TRADING_FLOOR_REBUILD_V1

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
[ -f .env.oanda_practice ] && { set -a; . ./.env.oanda_practice; set +a; }

URL=http://127.0.0.1:8765
OUT=data/registries/qsb_floor41_oanda_health_check.json
LOG=data/logs/qsb_floor41_oanda_health_check.txt
mkdir -p "$(dirname "$LOG")"

pass=0; total=0; failed=""
check() {
  total=$((total + 1))
  if [ "$2" = "1" ]; then pass=$((pass + 1)); echo "  ✓ $1 — $3" >> "$LOG"
  else failed="$failed $1"; echo "  ✗ $1 — $3" >> "$LOG"; fi
}

: > "$LOG"
echo "QSB Floor 41 OANDA Health · $(date -u +%FT%TZ)" >> "$LOG"

ENGINE=$(curl -s "${URL}/api/trading/oanda/floor41/engine" | python3 -c "import json,sys;print(json.load(sys.stdin).get('mode',''))" 2>/dev/null || echo "")
check engine_mode_valid "$([ "$ENGINE" = "oanda_practice_api" ] || [ "$ENGINE" = "paper_simulator" ] && echo 1 || echo 0)" "mode=$ENGINE"

LIVE=$(curl -s "${URL}/api/trading/oanda/floor41/engine" | python3 -c "import json,sys;d=json.load(sys.stdin);print('1' if d.get('live_money_enabled') is False and d.get('oanda_live_environment_allowed') is False else '0')" 2>/dev/null || echo 0)
check live_money_off "$LIVE" "live_money_enabled=false oanda_live_environment_allowed=false"

ACCT=$(curl -s "${URL}/api/trading/oanda/floor41/account" | python3 -c "import json,sys;d=json.load(sys.stdin);print('1' if d.get('account_id') else '0')" 2>/dev/null || echo 0)
check account_present "$ACCT" "account_id present"

PRICES=$(curl -s "${URL}/api/trading/oanda/floor41/prices" | python3 -c "import json,sys;print(json.load(sys.stdin).get('price_count',0))" 2>/dev/null || echo 0)
check prices_present "$([ "$PRICES" -ge 1 ] && echo 1 || echo 0)" "price_count=$PRICES"

ROOMS=$(curl -s "${URL}/api/trading/oanda/floor41/department_map" | python3 -c "import json,sys;print(json.load(sys.stdin).get('room_count',0))" 2>/dev/null || echo 0)
check rooms_13 "$([ "$ROOMS" = "13" ] && echo 1 || echo 0)" "room_count=$ROOMS"

WK=$(curl -s "${URL}/api/trading/oanda/floor41/workers" | python3 -c "import json,sys;print(json.load(sys.stdin).get('worker_count',0))" 2>/dev/null || echo 0)
check workers_12 "$([ "$WK" = "12" ] && echo 1 || echo 0)" "worker_count=$WK"

PNL=$(curl -s "${URL}/api/trading/oanda/floor41/pnl" | python3 -c "import json,sys;d=json.load(sys.stdin);print('1' if 'realized_pnl_total' in d and 'unrealized_pnl_total' in d and 'total_pnl' in d else '0')" 2>/dev/null || echo 0)
check pnl_fields_present "$PNL" "realized/unrealized/total"

OC=$(curl -s "${URL}/api/trading/oanda/floor41/openclaw" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('finding_count',0))" 2>/dev/null || echo 0)
check openclaw_findings "$([ "$OC" -ge 1 ] && echo 1 || echo 0)" "finding_count=$OC"

INT=$(curl -s "${URL}/api/trading/oanda/floor41/dashboard_interior" | python3 -c "import json,sys;d=json.load(sys.stdin);print('1' if d.get('rooms') and d.get('workers') else '0')" 2>/dev/null || echo 0)
check dashboard_interior_complete "$INT" "rooms+workers present in interior payload"

PAGE=$(curl -s -o /dev/null -w "%{http_code}" "${URL}/?v=unified&floor=41")
check page_loads "$([ "$PAGE" = "200" ] && echo 1 || echo 0)" "http=$PAGE"

score=$(python3 -c "print(round(100.0 * $pass / $total, 1))")
echo "" >> "$LOG"
echo "score: ${score} (${pass}/${total})" >> "$LOG"

python3 - <<PYEOF
import json, time
open("${OUT}", "w").write(json.dumps({
  "ok": True,
  "kind": "qsb_floor41_oanda_health_check",
  "phase": "QSB_FLOOR_41_OANDA_FULL_TRADING_FLOOR_REBUILD_V1",
  "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
  "passed": ${pass}, "total": ${total},
  "score": float(${score}),
  "failed": "${failed}".strip().split() if "${failed}".strip() else [],
  "execution_allowed": False,
  "live_money_enabled": False,
  "oanda_live_environment_allowed": False,
  "real_money_live_trading_enabled": False,
  "openclaw_real_tool_execution_enabled": False,
}, indent=2))
PYEOF

cat "$LOG"
echo ""
echo "score=${score} (${pass}/${total})"
