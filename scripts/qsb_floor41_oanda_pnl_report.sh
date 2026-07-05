#!/usr/bin/env bash
# QSB Floor 41 OANDA — PnL Report
# Phase: QSB_FLOOR_41_OANDA_FULL_TRADING_FLOOR_REBUILD_V1

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
[ -f .env.oanda_practice ] && { set -a; . ./.env.oanda_practice; set +a; }

# Make sure registries are fresh.
python3 -m tower.qsb_floor41_oanda >/dev/null 2>&1 || true

python3 - <<'PY'
import json
from pathlib import Path
P = Path('data/registries')
pnl = json.loads((P / 'qsb_floor41_oanda_pnl.json').read_text())
open_t = json.loads((P / 'qsb_floor41_oanda_open_trades.json').read_text())
closed_t = json.loads((P / 'qsb_floor41_oanda_closed_trades.json').read_text())
print("QSB Floor 41 OANDA — PnL Report (paper/practice)")
print("=" * 56)
print(f"realized_pnl_total      : {pnl.get('realized_pnl_total',0):+.4f}")
print(f"unrealized_pnl_total    : {pnl.get('unrealized_pnl_total',0):+.4f}")
print(f"total_pnl               : {pnl.get('total_pnl',0):+.4f}")
print(f"open_trade_count        : {open_t.get('trade_count',0)}")
print(f"closed_trade_count      : {closed_t.get('trade_count',0)}")
print(f"closed_winners          : {pnl.get('closed_winners',0)}")
print(f"closed_losers           : {pnl.get('closed_losers',0)}")
print("")
print("Open trades:")
for t in (open_t.get('open_trades') or [])[-10:]:
    upnl = t.get('unrealized_pnl') or 0
    print(f"  {t['trade_id']}  {t['instrument']:<8} {t['direction']:<4} u={t['units']:>6}  "
          f"entry={t['entry_price']}  mark={t.get('mark_price','—')}  uPnL={upnl:+.4f}")
print("")
print("Last 10 closed trades:")
for c in (closed_t.get('closed_trades') or [])[-10:]:
    pnl_a = c.get('pnl_amount') or 0
    print(f"  {c['trade_id']}  {c['instrument']:<8} {c['direction']:<4} u={c['units']:>6}  "
          f"entry={c['entry_price']}  exit={c.get('exit_price','—')}  pnl={pnl_a:+.4f}  "
          f"reason='{c.get('close_reason','')[:20]}'")
print("")
print("locks: live_money=False · oanda_live=False · openclaw_exec=False")
PY
