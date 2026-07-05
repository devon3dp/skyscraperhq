#!/usr/bin/env python3
"""qsb_oanda_position_monitor.py — monitor + close OANDA positions.

Rules (conservative, configurable):
  - Close position if unrealized PnL > +0.3% of margin used (take profit)
  - Close position if unrealized PnL < -0.5% of margin used (stop loss)
  - Otherwise: leave open + log heartbeat
"""
from __future__ import annotations
import json, os, urllib.request, urllib.parse, sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
REG  = ROOT / 'data/registries'
LOG = REG / 'qsb_oanda_position_monitor.jsonl'
VAULT = ROOT / 'floors/floor_28_security_department/vault'

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def src_env():
    p = VAULT / '.env.oanda_practice'
    for ln in p.read_text().split('\n'):
        ln = ln.strip()
        if ln.startswith('export '): ln = ln[7:]
        if '=' in ln:
            k, v = ln.split('=', 1)
            os.environ[k] = v.strip("'\"")

def oanda(path, method='GET', body=None):
    tok = os.environ['OANDA_API_TOKEN']
    acct = os.environ['OANDA_ACCOUNT_ID']
    url = f'https://api-fxpractice.oanda.com{path}'.replace('{accountID}', acct)
    headers = {'Authorization': 'Bearer ' + tok}
    if body:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(body).encode()
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

def main():
    src_env()
    trades = oanda('/v3/accounts/{accountID}/openTrades').get('trades', [])
    if not trades:
        print('  no open OANDA trades')
        return 0
    closed = 0
    skipped = 0
    for t in trades:
        tid = t['id']
        units = float(t.get('currentUnits', 0))
        open_px = float(t.get('price', 0))
        upl = float(t.get('unrealizedPL', 0))
        margin = float(t.get('marginUsed', 1)) or 1
        upl_pct = (upl / margin) * 100  # PnL as % of margin
        inst = t.get('instrument', '?')
        # Close winners > +0.3%, stops < -0.5%
        should_close = upl_pct > 0.3 or upl_pct < -0.5
        action = 'CLOSE' if should_close else 'HOLD'
        row = {'ts':utcnow(),'trade_id':tid,'instrument':inst,'units':units,
               'open_price':open_px,'unrealizedPL':upl,'upl_pct_of_margin':upl_pct,
               'action':action}
        if should_close:
            try:
                resp = oanda(f'/v3/accounts/{{accountID}}/trades/{tid}/close', method='PUT', body={'units':'ALL'})
                fill = resp.get('orderFillTransaction', {})
                row['close_price'] = fill.get('price')
                row['realized_pnl'] = fill.get('pl')
                closed += 1
                print(f'  ✓ CLOSED {inst:12s} tid={tid} upl_pct={upl_pct:+.3f}% realized_pl={fill.get("pl","?")}')
            except Exception as e:
                row['close_err'] = str(e)[:120]
                print(f'  ✗ CLOSE FAIL {inst}: {row["close_err"]}')
        else:
            skipped += 1
        with LOG.open('a') as f:
            f.write(json.dumps(row)+'\n')
    print(f'\n  summary: {closed} closed, {skipped} still open')
    return 0

if __name__ == '__main__':
    sys.exit(main())
