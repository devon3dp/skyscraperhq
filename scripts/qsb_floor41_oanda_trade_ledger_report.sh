#!/usr/bin/env bash
# QSB Floor 41 OANDA — Trade Ledger Report
# Phase: QSB_FLOOR_41_OANDA_FULL_TRADING_FLOOR_REBUILD_V1

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

LEDGER=data/logs/qsb_floor41_oanda_trade_ledger.jsonl
EVENTS=data/logs/qsb_floor41_oanda_events.jsonl

echo "QSB Floor 41 OANDA — Trade Ledger Report"
echo "========================================"
if [ -f "$LEDGER" ]; then
  echo "ledger entries: $(wc -l < "$LEDGER")"
  echo ""
  echo "Last 20 ledger entries:"
  tail -n 20 "$LEDGER" | python3 -c "
import json, sys
for line in sys.stdin:
  try:
    d = json.loads(line)
  except Exception:
    continue
  print(f'  {d.get(\"event\",\"?\")[:14]:<14} '
        f'{d.get(\"trade_id\",\"?\")[:14]:<14} '
        f'{d.get(\"instrument\",\"?\")[:8]:<8} '
        f'{d.get(\"direction\",\"\")[:4]:<4} '
        f'u={d.get(\"units\",\"?\")} '
        f'pnl={d.get(\"pnl_amount\",\"-\")} '
        f'ts={d.get(\"opened_ts\",d.get(\"closed_ts\",d.get(\"ts\",\"\")))[:19]}')
"
else
  echo "no ledger file yet ($LEDGER)"
fi
echo ""
if [ -f "$EVENTS" ]; then
  echo "event log entries: $(wc -l < "$EVENTS")"
fi
echo ""
echo "locks: live_money=False · oanda_live=False · openclaw_exec=False"
