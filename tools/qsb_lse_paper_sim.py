#!/usr/bin/env python3
"""qsb_lse_paper_sim.py — paper-trading sim for LSE FTSE 100 via Yahoo Finance.

No broker; this is a LOCAL paper ledger. Prices pulled from Yahoo's public quote
endpoint. Orders are filled at mid-spread + a 5bps slippage haircut.

Usage:
  python3 tools/qsb_lse_paper_sim.py prices VOD.L BP.L HSBA.L
  python3 tools/qsb_lse_paper_sim.py buy VOD.L --notional 50
  python3 tools/qsb_lse_paper_sim.py sell VOD.L --qty 5
  python3 tools/qsb_lse_paper_sim.py book
  python3 tools/qsb_lse_paper_sim.py pnl
"""
from __future__ import annotations
import argparse, json, urllib.request, urllib.parse, sys, time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
REG  = ROOT / 'data/registries'
LEDGER = REG / 'qsb_floor60_lse_paper_ledger.jsonl'
BOOK   = REG / 'qsb_floor60_lse_paper_book.json'

INITIAL_CASH_GBP = 100_000.0
SLIPPAGE_BPS = 5.0

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def fetch_quotes(symbols):
    """Pull quotes via yfinance (handles Yahoo auth internally)."""
    import yfinance as yf
    out = {}
    for s in symbols:
        try:
            tk = yf.Ticker(s)
            fi = tk.fast_info
            out[s] = {
                'symbol': s,
                'name': s,
                'price': fi.last_price,
                'currency': fi.currency or 'GBp',
                'pct': ((fi.last_price - fi.previous_close) / fi.previous_close * 100) if fi.previous_close else 0,
                'exchange': 'LSE',
                'market_state': 'REGULAR',
            }
        except Exception as e:
            out[s] = {'symbol': s, 'err': str(e)}
    return out

def book_load():
    if BOOK.exists():
        return json.loads(BOOK.read_text())
    return {
        'ok': True, 'kind':'qsb_floor60_lse_paper_book',
        'cash_gbp': INITIAL_CASH_GBP,
        'positions': {},
        'realized_pnl_gbp': 0.0,
        'updated_ts': None,
        'advisory_only': True,
        'real_money': False,
    }

def book_save(b):
    b['updated_ts'] = utcnow()
    BOOK.write_text(json.dumps(b, indent=2))

def append_ledger(row):
    with LEDGER.open('a') as f:
        f.write(json.dumps(row) + '\n')

def cmd_prices(syms):
    q = fetch_quotes(syms)
    for s in syms:
        r = q.get(s, {})
        # Yahoo returns GBp (pence) for most LSE tickers — divide by 100 if currency==GBp
        p = r.get('price')
        cur = r.get('currency','GBp')
        if p is not None and cur == 'GBp':
            disp = f'£{p/100:.4f} ({p:.2f}p)'
        else:
            disp = f'£{p}'
        print(f'  {s:8s} {r.get("name","?"):28s} {disp:>22s} {r.get("pct",0):+.2f}%  {r.get("market_state","?")}')

def buy(sym, notional=None, qty=None):
    q = fetch_quotes([sym]).get(sym)
    if not q: raise SystemExit(f'no quote for {sym}')
    px = q['price']
    if q.get('currency','GBp') == 'GBp':
        px_gbp = px / 100.0
    else:
        px_gbp = px
    slip_px = px_gbp * (1 + SLIPPAGE_BPS / 10000)
    if notional is not None:
        qty = int(notional / slip_px)
    cost = qty * slip_px
    book = book_load()
    if cost > book['cash_gbp']:
        raise SystemExit(f'insufficient cash: cost £{cost:.2f} > cash £{book["cash_gbp"]:.2f}')
    pos = book['positions'].get(sym, {'qty': 0, 'avg_px_gbp': 0.0})
    new_qty = pos['qty'] + qty
    pos['avg_px_gbp'] = ((pos['avg_px_gbp']*pos['qty']) + cost) / new_qty if new_qty else 0
    pos['qty'] = new_qty
    book['positions'][sym] = pos
    book['cash_gbp'] -= cost
    book_save(book)
    row = {'ts':utcnow(),'side':'BUY','symbol':sym,'qty':qty,'fill_px_gbp':slip_px,'cost_gbp':cost,'kind':'lse_paper_fill','advisory_only':True,'real_money':False}
    append_ledger(row)
    print(f'BUY  {sym:8s} qty={qty:>6d} @ £{slip_px:.4f}  cost £{cost:.2f}  cash now £{book["cash_gbp"]:.2f}')
    return row

def sell(sym, qty=None, notional=None):
    book = book_load()
    pos = book['positions'].get(sym)
    if not pos or pos['qty'] <= 0:
        raise SystemExit(f'no position in {sym}')
    q = fetch_quotes([sym]).get(sym)
    px = q['price']
    px_gbp = px/100.0 if q.get('currency','GBp')=='GBp' else px
    slip_px = px_gbp * (1 - SLIPPAGE_BPS/10000)
    if notional is not None:
        qty = int(notional/slip_px)
    qty = min(qty or pos['qty'], pos['qty'])
    proceeds = qty * slip_px
    pnl = (slip_px - pos['avg_px_gbp']) * qty
    pos['qty'] -= qty
    if pos['qty'] == 0: del book['positions'][sym]
    book['cash_gbp'] += proceeds
    book['realized_pnl_gbp'] = book.get('realized_pnl_gbp',0) + pnl
    book_save(book)
    row = {'ts':utcnow(),'side':'SELL','symbol':sym,'qty':qty,'fill_px_gbp':slip_px,'proceeds_gbp':proceeds,'pnl_gbp':pnl,'kind':'lse_paper_fill','advisory_only':True,'real_money':False}
    append_ledger(row)
    print(f'SELL {sym:8s} qty={qty:>6d} @ £{slip_px:.4f}  proceeds £{proceeds:.2f}  realized PnL £{pnl:+.2f}')
    return row

def book_cmd():
    book = book_load()
    print(f'\n=== F60 LSE Paper Book ===')
    print(f'cash:        £{book["cash_gbp"]:,.2f}')
    print(f'realized PnL: £{book.get("realized_pnl_gbp",0):+,.2f}')
    if book['positions']:
        syms = list(book['positions'].keys())
        quotes = fetch_quotes(syms)
        eq_val = 0.0
        for s, p in book['positions'].items():
            qq = quotes.get(s, {})
            px = qq.get('price') or 0
            px_gbp = px/100.0 if qq.get('currency','GBp')=='GBp' else px
            mv = p['qty'] * px_gbp
            upl = (px_gbp - p['avg_px_gbp']) * p['qty']
            eq_val += mv
            print(f'  {s:8s} qty={p["qty"]:>6d} avg=£{p["avg_px_gbp"]:.4f} mv=£{mv:.2f} upl=£{upl:+.2f}')
        equity = book['cash_gbp'] + eq_val
        print(f'equity:      £{equity:,.2f} (cash + positions £{eq_val:,.2f})')
    print(f'updated:     {book.get("updated_ts")}')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: qsb_lse_paper_sim.py prices SYMS... | buy SYM --notional N | sell SYM --qty N | book')
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == 'prices':
        cmd_prices(sys.argv[2:])
    elif cmd == 'buy':
        ap = argparse.ArgumentParser()
        ap.add_argument('symbol'); ap.add_argument('--notional', type=float); ap.add_argument('--qty', type=int)
        a = ap.parse_args(sys.argv[2:])
        buy(a.symbol, notional=a.notional, qty=a.qty)
    elif cmd == 'sell':
        ap = argparse.ArgumentParser()
        ap.add_argument('symbol'); ap.add_argument('--qty', type=int); ap.add_argument('--notional', type=float)
        a = ap.parse_args(sys.argv[2:])
        sell(a.symbol, qty=a.qty, notional=a.notional)
    elif cmd == 'book':
        book_cmd()
