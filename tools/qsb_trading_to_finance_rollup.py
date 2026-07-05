#!/usr/bin/env python3
"""qsb_trading_to_finance_rollup.py — sealed-packet ledger contract.

Every trade on F41 OANDA / F42 Binance / F43 Alpaca is rolled up into the
F44 Accounts master book via a sealed packet that travels by lift.

Packet schema:
  {
    "packet_id": "pkt_<sha8>",
    "kind": "trade_settlement",
    "origin_floor": 41|42|43,
    "destination_floor": 44,
    "lift": "trading_finance_lift",
    "trade": { venue, instrument, side, qty, entry_px, exit_px, pnl_usd, ts },
    "advisory_only": true,
    "real_money": false,
    "sealed_ts": "<utc iso>",
    "sealed_by": "trading_to_finance_rollup_v1"
  }

The receiving side (F44) appends to qsb_floor44_master_ledger.jsonl
and updates qsb_floor44_master_book.json (running balances).
"""
from __future__ import annotations
import json, hashlib, urllib.request, os, time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
REG  = ROOT / 'data/registries'
LEDGER = REG / 'qsb_floor44_master_ledger.jsonl'
BOOK   = REG / 'qsb_floor44_master_book.json'

def seal(packet):
    raw = json.dumps(packet, sort_keys=True).encode()
    return 'pkt_' + hashlib.sha256(raw).hexdigest()[:12]

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def emit_packet(origin, trade):
    p = {
        'packet_id': '',
        'kind': 'trade_settlement',
        'origin_floor': origin,
        'destination_floor': 44,
        'lift': 'trading_finance_lift',
        'trade': trade,
        'advisory_only': True,
        'real_money': False,
        'sealed_ts': utcnow(),
        'sealed_by': 'trading_to_finance_rollup_v1',
    }
    p['packet_id'] = seal(p)
    return p

def append_ledger(packet):
    with LEDGER.open('a') as f:
        f.write(json.dumps(packet) + '\n')

def update_book(packet):
    if BOOK.exists():
        book = json.loads(BOOK.read_text())
    else:
        book = {
            'ok': True,
            'kind': 'qsb_floor44_master_book',
            'venues': {},
            'total_packets': 0,
            'updated_ts': None,
            'advisory_only': True,
            'real_money': False,
        }
    v = book['venues'].setdefault(packet['trade']['venue'], {
        'pnl_usd': 0.0, 'trades_recorded': 0, 'last_trade_ts': None,
    })
    v['pnl_usd'] += packet['trade'].get('pnl_usd', 0.0)
    v['trades_recorded'] += 1
    v['last_trade_ts'] = packet['trade'].get('ts')
    book['total_packets'] = book.get('total_packets', 0) + 1
    book['updated_ts'] = utcnow()
    BOOK.write_text(json.dumps(book, indent=2))

def rollup_oanda():
    """Read F41 OANDA closed trades, emit a packet for each new one."""
    p = REG / 'qsb_floor41_oanda_closed_trades.json'
    if not p.exists(): return 0
    d = json.loads(p.read_text())
    trades = d.get('closed_trades', d.get('trades', []))
    if not isinstance(trades, list): return 0
    seen = _seen_ids(41)
    n = 0
    for t in trades:
        tid = str(t.get('trade_id') or t.get('id') or t.get('orderId',''))
        if not tid or tid in seen: continue
        pkt = emit_packet(41, {
            'venue': 'oanda_practice',
            'instrument': t.get('instrument','?'),
            'side': t.get('side', t.get('units', 0) > 0 and 'BUY' or 'SELL'),
            'qty': t.get('units') or t.get('quantity'),
            'entry_px': t.get('open_price') or t.get('entry'),
            'exit_px':  t.get('close_price') or t.get('exit'),
            'pnl_usd':  float(t.get('pnl_usd', t.get('realizedPL', 0)) or 0),
            'ts': t.get('close_time') or t.get('closed_at') or t.get('ts'),
            'trade_id': tid,
        })
        append_ledger(pkt); update_book(pkt); n += 1
    return n

def rollup_binance():
    """Find Binance settled rows from activity tail (round-trips with pnl)."""
    p = REG / 'qsb_tower_activity_tail.jsonl'
    if not p.exists(): return 0
    seen = _seen_ids(42)
    n = 0
    for ln in p.read_text().strip().split('\n'):
        try: r = json.loads(ln)
        except: continue
        if r.get('venue') != 'binance_testnet': continue
        if 'pnl_usdt' not in r: continue
        tid = r.get('ts')
        if tid in seen: continue
        pkt = emit_packet(42, {
            'venue': 'binance_testnet',
            'instrument': 'BTCUSDT',
            'side': r.get('side','ROUND_TRIP'),
            'qty': r.get('qty'),
            'entry_px': None,
            'exit_px':  None,
            'pnl_usd':  float(r.get('pnl_usdt',0) or 0),
            'ts': r.get('ts'),
            'trade_id': tid,
        })
        append_ledger(pkt); update_book(pkt); n += 1
    return n

def rollup_alpaca():
    """Read alpaca paper orders ledger, emit any unseen fill rows."""
    p = REG / 'qsb_floor43_alpaca_paper_orders.jsonl'
    if not p.exists(): return 0
    seen = _seen_ids(43)
    n = 0
    for ln in p.read_text().strip().split('\n'):
        try: r = json.loads(ln)
        except: continue
        tid = str(r.get('order_id') or r.get('id') or r.get('client_order_id') or r.get('ts'))
        if not tid or tid in seen: continue
        if r.get('status') in ('accepted','new','queued') and not r.get('filled_avg_price'):
            continue  # not settled yet
        pkt = emit_packet(43, {
            'venue': 'alpaca_paper',
            'instrument': r.get('symbol','?'),
            'side': r.get('side','?').upper(),
            'qty': float(r.get('filled_qty', r.get('qty', 0)) or 0),
            'entry_px': float(r.get('filled_avg_price') or 0),
            'exit_px':  None,
            'pnl_usd':  0.0,  # unrealized on fill; mark-to-market handled separately
            'ts': r.get('filled_at') or r.get('submitted_at'),
            'trade_id': tid,
        })
        append_ledger(pkt); update_book(pkt); n += 1
    return n

def _seen_ids(origin):
    if not LEDGER.exists(): return set()
    seen = set()
    for ln in LEDGER.read_text().strip().split('\n'):
        if not ln.strip(): continue
        try: p = json.loads(ln)
        except: continue
        if p.get('origin_floor') == origin:
            seen.add(str(p.get('trade',{}).get('trade_id') or ''))
    return seen

def main():
    n41 = rollup_oanda()
    n42 = rollup_binance()
    n43 = rollup_alpaca()
    print(f'OANDA  (F41 → F44): {n41} packets')
    print(f'Binance(F42 → F44): {n42} packets')
    print(f'Alpaca (F43 → F44): {n43} packets')
    if BOOK.exists():
        b = json.loads(BOOK.read_text())
        print(f'\nF44 master book:')
        for v, d in b.get('venues', {}).items():
            print(f'  {v:20s} pnl_usd={d["pnl_usd"]:+.4f}  trades={d["trades_recorded"]}')
        print(f'  total packets: {b.get("total_packets")}')

if __name__ == '__main__':
    main()
