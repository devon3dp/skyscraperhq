#!/usr/bin/env python3
"""qsb_stripe_order_poller.py — poll Stripe events for completed orders.

No public webhook needed — this calls Stripe's /v1/events endpoint, looks for
checkout.session.completed since last_seen_event_id, books each to F44,
queues fulfillment.

Runs every 5 min via bg_loop.
"""
from __future__ import annotations
import json, os, urllib.request, urllib.parse, sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
REG  = ROOT / 'data/registries'
STATE = REG / 'qsb_stripe_poller_state.json'
LEDGER = REG / 'qsb_stripe_orders_received.jsonl'
F44 = REG / 'qsb_floor44_master_book.json'
FULFILL = REG / 'qsb_fulfillment_queue.jsonl'
VAULT = ROOT / 'floors/floor_28_security_department/vault'

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def src_env():
    p = VAULT / '.env.stripe'
    if not p.exists(): return False
    for ln in p.read_text().split('\n'):
        ln = ln.strip()
        if not ln or ln.startswith('#'): continue
        if ln.startswith('export '): ln = ln[7:]
        if '=' in ln:
            k, v = ln.split('=', 1)
            os.environ[k] = v.strip("'\"")
    return True

def stripe_get(path, params=None):
    sk = os.environ['STRIPE_SECRET_KEY']
    if params:
        path = f'{path}?{urllib.parse.urlencode(params)}'
    req = urllib.request.Request(f'https://api.stripe.com{path}',
        headers={'Authorization': f'Bearer {sk}'})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {'last_event_id': None, 'orders_seen': 0}

def save_state(s):
    STATE.write_text(json.dumps(s, indent=2))

def book_to_f44(session):
    """Add order revenue + meta to F44 master book."""
    if F44.exists():
        b = json.loads(F44.read_text())
    else:
        b = {'ok':True,'kind':'qsb_floor44_master_book','venues':{},'total_packets':0,'operational_spend':{'total_gbp':0,'rows':[]},'advisory_only':True}
    sales = b.setdefault('shop_sales', {'total_gbp':0.0,'orders':0,'rows':[]})
    amount_gbp = (session.get('amount_total') or 0) / 100
    md = session.get('metadata') or {}
    sales['total_gbp'] += amount_gbp
    sales['orders'] += 1
    sales['rows'].append({
        'ts': utcnow(),
        'session_id': session.get('id'),
        'amount_gbp': amount_gbp,
        'currency': session.get('currency'),
        'customer_email': (session.get('customer_details') or {}).get('email'),
        'sku': md.get('sku'),
        'shop': md.get('shop'),
        'floor': md.get('floor'),
        'payment_status': session.get('payment_status'),
    })
    b['updated_ts'] = utcnow()
    F44.write_text(json.dumps(b, indent=2))

def queue_fulfillment(session):
    md = session.get('metadata') or {}
    addr = (session.get('shipping_details') or {}).get('address') or (session.get('customer_details') or {}).get('address') or {}
    with FULFILL.open('a') as f:
        f.write(json.dumps({
            'ts': utcnow(),
            'session_id': session.get('id'),
            'sku': md.get('sku'),
            'shop': md.get('shop'),
            'floor': md.get('floor'),
            'customer_email': (session.get('customer_details') or {}).get('email'),
            'ship_to_name': (session.get('shipping_details') or {}).get('name'),
            'ship_to_address': addr,
            'status': 'awaiting_supplier_order',
            'amount_gbp': (session.get('amount_total') or 0) / 100,
        })+'\n')

def main():
    if not src_env():
        print('no stripe env')
        return 1
    s = load_state()
    params = {'type':'checkout.session.completed', 'limit':100}
    if s.get('last_event_id'):
        params['starting_after'] = s['last_event_id']
    try:
        result = stripe_get('/v1/events', params)
    except Exception as e:
        print(f'  err: {e}')
        return 1
    events = result.get('data', [])
    if not events:
        print(f'  no new checkout.session.completed events (state: {s.get("orders_seen",0)} total seen)')
        return 0
    new_orders = 0
    for ev in events:
        session = ev.get('data',{}).get('object',{})
        if not session: continue
        with LEDGER.open('a') as f:
            f.write(json.dumps({'ts':utcnow(),'event_id':ev['id'],'session':session})+'\n')
        book_to_f44(session)
        queue_fulfillment(session)
        new_orders += 1
        s['last_event_id'] = ev['id']
    s['orders_seen'] = s.get('orders_seen', 0) + new_orders
    save_state(s)
    print(f'  ✓ {new_orders} new orders booked to F44 + fulfillment queue')

if __name__ == '__main__':
    sys.exit(main() or 0)
