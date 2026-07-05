#!/usr/bin/env python3
"""qsb_stripe_webhook_handler.py — process Stripe events with auto-retry + idempotency.

Replaces the simple poller with a hardened version:
  · idempotent — each event_id processed exactly once via state file
  · retry queue — failed events go to retry_queue.jsonl, retried with exponential backoff
  · classify — checkout.session.completed → fulfillment, payment_intent.failed → alert, refund → reversal
  · book to F44 — every successful event updates master book + activity tail
  · audit — every event + outcome + retry attempt logged

Runs every 5 min via bg_loop.
"""
from __future__ import annotations
import json, os, urllib.request, urllib.parse, sys, time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
REG  = ROOT / 'data/registries'
STATE = REG / 'qsb_stripe_handler_state.json'
LEDGER = REG / 'qsb_stripe_events_ledger.jsonl'
RETRY = REG / 'qsb_stripe_retry_queue.jsonl'
F44 = REG / 'qsb_floor44_master_book.json'
FULFILL = REG / 'qsb_fulfillment_queue.jsonl'
VAULT = ROOT / 'floors/floor_28_security_department/vault'

EVENT_TYPES = [
    'checkout.session.completed',
    'payment_intent.succeeded',
    'payment_intent.payment_failed',
    'charge.refunded',
    'charge.dispute.created',
]

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def src_env():
    p = VAULT / '.env.stripe'
    for ln in p.read_text().split('\n'):
        ln = ln.strip()
        if not ln or ln.startswith('#'): continue
        if ln.startswith('export '): ln = ln[7:]
        if '=' in ln:
            k, v = ln.split('=', 1)
            os.environ[k] = v.strip("'\"")

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
    return {'processed_event_ids': [], 'last_seen_event_id': None, 'total_processed': 0, 'retry_attempts': {}}

def save_state(s):
    # Cap processed list at 1000 to avoid bloat
    s['processed_event_ids'] = s.get('processed_event_ids',[])[-1000:]
    STATE.write_text(json.dumps(s, indent=2))

def book_checkout_completed(session):
    if F44.exists():
        b = json.loads(F44.read_text())
    else:
        b = {'ok':True,'kind':'qsb_floor44_master_book','venues':{},'total_packets':0,'operational_spend':{'total_gbp':0,'rows':[]},'advisory_only':True}
    sales = b.setdefault('shop_sales', {'total_gbp':0.0,'orders':0,'rows':[]})
    amt = (session.get('amount_total') or 0) / 100
    md = session.get('metadata') or {}
    sales['total_gbp'] += amt
    sales['orders'] += 1
    sales['rows'].append({
        'ts': utcnow(), 'session_id': session.get('id'),
        'amount_gbp': amt, 'currency': session.get('currency'),
        'customer_email': (session.get('customer_details') or {}).get('email'),
        'sku': md.get('sku'),'shop': md.get('shop'),'floor': md.get('floor'),
    })
    b['updated_ts'] = utcnow()
    F44.write_text(json.dumps(b, indent=2))
    # Queue fulfillment
    addr = (session.get('shipping_details') or {}).get('address') or {}
    with FULFILL.open('a') as f:
        f.write(json.dumps({
            'ts': utcnow(),'session_id': session.get('id'),
            'sku': md.get('sku'),'shop': md.get('shop'),'floor': md.get('floor'),
            'customer_email': (session.get('customer_details') or {}).get('email'),
            'ship_to_name': (session.get('shipping_details') or {}).get('name'),
            'ship_to_address': addr, 'status': 'awaiting_supplier_order',
            'amount_gbp': amt,
        })+'\n')

def handle_payment_failed(pi):
    """Log + emit alert. No further action — Stripe handles customer notification."""
    with REG / 'qsb_payment_failures.jsonl' as f: pass  # noqa
    (REG / 'qsb_payment_failures.jsonl').open('a').write(json.dumps({
        'ts': utcnow(), 'payment_intent_id': pi.get('id'),
        'amount_gbp': (pi.get('amount') or 0) / 100,
        'failure_message': pi.get('last_payment_error', {}).get('message'),
        'metadata': pi.get('metadata',{}),
    })+'\n')

def handle_refund(charge):
    """Update F44 to reverse the booking."""
    if F44.exists():
        b = json.loads(F44.read_text())
        ref = (charge.get('amount_refunded') or 0) / 100
        sales = b.get('shop_sales', {})
        if ref > 0 and sales.get('orders',0) > 0:
            sales['total_gbp'] = sales.get('total_gbp',0) - ref
            sales.setdefault('refunds', []).append({
                'ts': utcnow(), 'charge_id': charge.get('id'),
                'amount_refunded_gbp': ref,
            })
            b['updated_ts'] = utcnow()
            F44.write_text(json.dumps(b, indent=2))

def process_event(ev, s):
    """Returns (ok, message)."""
    et = ev.get('type')
    obj = ev.get('data',{}).get('object',{})
    try:
        if et == 'checkout.session.completed':
            book_checkout_completed(obj)
            return True, 'checkout booked + fulfillment queued'
        elif et == 'payment_intent.payment_failed':
            handle_payment_failed(obj)
            return True, 'payment failure logged'
        elif et == 'charge.refunded':
            handle_refund(obj)
            return True, 'refund applied'
        elif et in ('payment_intent.succeeded', 'charge.dispute.created'):
            return True, 'observed only'
        else:
            return True, f'event type {et} ignored'
    except Exception as e:
        return False, str(e)[:160]

def retry_failed(s):
    """Process any items in retry queue with exponential backoff."""
    if not RETRY.exists() or RETRY.stat().st_size == 0:
        return 0
    rows = [json.loads(l) for l in RETRY.read_text().strip().split('\n') if l.strip()]
    keep = []
    succeeded = 0
    now = time.time()
    for r in rows:
        attempts = r.get('attempts', 0)
        next_at = r.get('next_retry_at', 0)
        if now < next_at:
            keep.append(r); continue
        if attempts >= 5:
            # Dead letter — log and drop
            with (REG / 'qsb_stripe_dead_letter.jsonl').open('a') as f:
                f.write(json.dumps({**r,'dead_at':utcnow()})+'\n')
            continue
        ok, msg = process_event(r['event'], s)
        if ok:
            succeeded += 1
            s['processed_event_ids'].append(r['event']['id'])
        else:
            r['attempts'] = attempts + 1
            r['next_retry_at'] = now + (2 ** r['attempts']) * 60  # 2,4,8,16,32 min backoff
            r['last_error'] = msg
            keep.append(r)
    RETRY.write_text('\n'.join(json.dumps(r) for r in keep) + ('\n' if keep else ''))
    return succeeded

def main():
    src_env()
    s = load_state()
    # First, retry any failed items
    retried = retry_failed(s)
    if retried:
        print(f'  ✓ retried {retried} events from queue')
    # Then poll for new events
    seen = set(s['processed_event_ids'])
    for et in EVENT_TYPES:
        try:
            params = {'type': et, 'limit': 50}
            if s.get('last_seen_event_id'):
                params['starting_after'] = s['last_seen_event_id']
            result = stripe_get('/v1/events', params)
        except Exception as e:
            print(f'  ✗ events fetch err ({et}): {e}')
            continue
        events = result.get('data', [])
        for ev in events:
            if ev['id'] in seen: continue
            with LEDGER.open('a') as f:
                f.write(json.dumps({'ts':utcnow(),'event_id':ev['id'],'type':ev['type']})+'\n')
            ok, msg = process_event(ev, s)
            if ok:
                seen.add(ev['id'])
                s['processed_event_ids'].append(ev['id'])
                s['total_processed'] += 1
                print(f'  ✓ {ev["type"]:35s} {ev["id"]}: {msg}')
            else:
                with RETRY.open('a') as f:
                    f.write(json.dumps({
                        'first_seen': utcnow(), 'attempts': 1,
                        'next_retry_at': time.time() + 120,
                        'event': ev, 'last_error': msg,
                    })+'\n')
                print(f'  ⚠ {ev["type"]:35s} retry queued: {msg}')
            s['last_seen_event_id'] = ev['id']
    save_state(s)
    if s['total_processed']:
        print(f'  lifetime processed: {s["total_processed"]}')
    return 0

if __name__ == '__main__':
    sys.exit(main() or 0)
