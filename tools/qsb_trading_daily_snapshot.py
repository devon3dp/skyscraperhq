#!/usr/bin/env python3
"""qsb_trading_daily_snapshot.py — append a row to each venue's daily archive.

Per-day file: data/archives/trading/YYYY-MM-DD_<venue>.jsonl
Captures: balance, open positions, pnl, prices snapshot.

Run multiple times per day; appends. Daily diff is computed from first vs last row.
"""
from __future__ import annotations
import json, os, time, urllib.request, hmac, hashlib
from pathlib import Path
from datetime import datetime, timezone, date

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
VAULT = ROOT / 'floors/floor_28_security_department/vault'
ARCHIVE_DIR = ROOT / 'data/archives/trading'
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def today_str():
    return date.today().isoformat()

def append_row(venue, row):
    p = ARCHIVE_DIR / f'{today_str()}_{venue}.jsonl'
    with p.open('a') as f:
        f.write(json.dumps(row) + '\n')

def src(name):
    p = VAULT / name
    if p.exists():
        for ln in p.read_text().split('\n'):
            ln = ln.strip()
            if not ln or ln.startswith('#'): continue
            if ln.startswith('export '): ln = ln[7:]
            if '=' in ln:
                k, v = ln.split('=', 1)
                os.environ[k] = v.strip("'\"")

def snap_oanda():
    src('.env.oanda_practice')
    tok = os.environ.get('OANDA_API_TOKEN','')
    acct = os.environ.get('OANDA_ACCOUNT_ID','')
    if not tok or not acct: return False
    req = urllib.request.Request(f'https://api-fxpractice.oanda.com/v3/accounts/{acct}/summary', headers={'Authorization':'Bearer '+tok})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=8).read()).get('account', {})
        row = {
            'ts': utcnow(), 'venue':'oanda_practice',
            'balance': float(d.get('balance', 0)),
            'currency': d.get('currency'),
            'nav': float(d.get('NAV', 0)),
            'unrealized_pl': float(d.get('unrealizedPL', 0)),
            'open_trades': int(d.get('openTradeCount', 0)),
            'open_positions': int(d.get('openPositionCount', 0)),
            'margin_used': float(d.get('marginUsed', 0)),
            'margin_avail': float(d.get('marginAvailable', 0)),
        }
        append_row('oanda_practice', row)
        return True
    except Exception as e:
        append_row('oanda_practice', {'ts': utcnow(), 'venue':'oanda_practice', 'err': str(e)})
        return False

def snap_binance():
    src('.env.binance_testnet')
    k = os.environ.get('QSB_BINANCE_TESTNET_API_KEY','')
    s = os.environ.get('QSB_BINANCE_TESTNET_API_SECRET','')
    if not k or not s: return False
    ts = int(time.time()*1000); q = f'timestamp={ts}'
    sig = hmac.new(s.encode(), q.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(f'https://testnet.binance.vision/api/v3/account?{q}&signature={sig}', headers={'X-MBX-APIKEY':k})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=8).read())
        row = {
            'ts': utcnow(), 'venue':'binance_testnet',
            'can_trade': d.get('canTrade'),
            'balances': {b['asset']:{'free':b['free'],'locked':b['locked']} for b in d.get('balances',[]) if float(b['free']) + float(b['locked']) > 0 and b['asset'] in ('BTC','ETH','BNB','ADA','SOL','USDT','USDC')},
        }
        # Add prices for held assets
        prices = {}
        for sym in ['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','SOLUSDT']:
            try:
                p = json.loads(urllib.request.urlopen(f'https://testnet.binance.vision/api/v3/ticker/price?symbol={sym}', timeout=5).read())
                prices[sym] = float(p['price'])
            except: pass
        row['prices'] = prices
        append_row('binance_testnet', row)
        return True
    except Exception as e:
        append_row('binance_testnet', {'ts': utcnow(), 'venue':'binance_testnet', 'err': str(e)})
        return False

def snap_alpaca():
    src('.env.alpaca_paper')
    k = os.environ.get('ALPACA_API_KEY',''); s = os.environ.get('ALPACA_API_SECRET','')
    if not k or not s: return False
    hdr = {'APCA-API-KEY-ID':k,'APCA-API-SECRET-KEY':s}
    try:
        acc = json.loads(urllib.request.urlopen(urllib.request.Request('https://paper-api.alpaca.markets/v2/account', headers=hdr), timeout=8).read())
        pos = json.loads(urllib.request.urlopen(urllib.request.Request('https://paper-api.alpaca.markets/v2/positions', headers=hdr), timeout=8).read())
        clk = json.loads(urllib.request.urlopen(urllib.request.Request('https://paper-api.alpaca.markets/v2/clock', headers=hdr), timeout=8).read())
        row = {
            'ts': utcnow(), 'venue':'alpaca_paper',
            'equity': float(acc.get('equity', 0)),
            'cash': float(acc.get('cash', 0)),
            'buying_power': float(acc.get('buying_power', 0)),
            'long_market_value': float(acc.get('long_market_value', 0)),
            'positions_count': len(pos),
            'positions': [{'sym':p['symbol'],'qty':p['qty'],'avg':p['avg_entry_price'],'mv':p['market_value'],'upl':p['unrealized_pl']} for p in pos[:30]],
            'market_open': clk.get('is_open'),
            'next_open': clk.get('next_open'),
        }
        append_row('alpaca_paper', row)
        return True
    except Exception as e:
        append_row('alpaca_paper', {'ts': utcnow(), 'venue':'alpaca_paper', 'err': str(e)})
        return False

def daily_diff(venue):
    p = ARCHIVE_DIR / f'{today_str()}_{venue}.jsonl'
    if not p.exists(): return None
    lines = [l for l in p.read_text().strip().split('\n') if l.strip()]
    if len(lines) < 2: return None
    first = json.loads(lines[0]); last = json.loads(lines[-1])
    return {'first_ts':first.get('ts'),'last_ts':last.get('ts'),'rows':len(lines),'first':first,'last':last}

if __name__ == '__main__':
    o = snap_oanda(); b = snap_binance(); a = snap_alpaca()
    print(f'oanda snap: {o}, binance snap: {b}, alpaca snap: {a}')
    for v in ('oanda_practice','binance_testnet','alpaca_paper'):
        p = ARCHIVE_DIR / f'{today_str()}_{v}.jsonl'
        if p.exists():
            print(f'  archive/{p.name}: {len(p.read_text().strip().split(chr(10)))} rows')
