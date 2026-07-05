#!/usr/bin/env python3
"""qsb_purchase_request.py — Ross-authorised real-world purchase flow.

Flow:
  1. WREN proposes:    request_id, vendor, purpose, max_cost_gbp, justification
                       → status = 'awaiting_ross_approval'
  2. ROSS approves:    qsb_purchase_request.py approve <request_id>
                       → status = 'approved'
  3. WORKER executes:  qsb_purchase_request.py execute <request_id> --actual_cost_gbp N
                       → status = 'executed' + F44 ledger row
  4. RECEIPT recorded: qsb_purchase_request.py receipt <request_id> --note ... --receipt_url ...

Hard rules (enforced in code):
  · NO autonomous Wren spend — only proposes
  · NO execute without 'approved' status
  · Per-request cap: £100 default (raise per CLAUDE.md auth)
  · Per-day cap: £200 default
  · Every state change appended to qsb_purchase_request_ledger.jsonl
  · F44 master book updated on execute
"""
from __future__ import annotations
import argparse, json, sys, uuid
from pathlib import Path
from datetime import datetime, timezone, date

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
REG  = ROOT / 'data/registries'
LEDGER = REG / 'qsb_purchase_request_ledger.jsonl'
F44 = REG / 'qsb_floor44_master_book.json'
AUTH = REG / 'qsb_purchase_authorization.json'

DEFAULT_PER_REQUEST_CAP_GBP = 100.0
DEFAULT_PER_DAY_CAP_GBP = 200.0
DEFAULT_TOTAL_AVAILABLE_GBP = 0.0

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def load_auth():
    if AUTH.exists():
        return json.loads(AUTH.read_text())
    return {
        'ok': True, 'kind':'qsb_purchase_authorization',
        'per_request_cap_gbp': DEFAULT_PER_REQUEST_CAP_GBP,
        'per_day_cap_gbp': DEFAULT_PER_DAY_CAP_GBP,
        'total_available_gbp': DEFAULT_TOTAL_AVAILABLE_GBP,
        'authorized_vendors': ['namecheap.com','netlify.com','wise.com','stripe.com','squareup.com','aliexpress.com','alibaba.com'],
        'authorized_categories': ['domain','hosting','supplier_order','operations'],
        'updated_ts': None,
        'advisory_only': True,
    }

def save_auth(a):
    a['updated_ts'] = utcnow()
    AUTH.write_text(json.dumps(a, indent=2))

def all_requests():
    if not LEDGER.exists(): return []
    return [json.loads(l) for l in LEDGER.read_text().strip().split('\n') if l.strip()]

def append_event(req_id, kind, payload):
    row = {
        'ts': utcnow(), 'request_id': req_id, 'event_kind': kind,
        **payload,
        'advisory_only': True,
    }
    with LEDGER.open('a') as f:
        f.write(json.dumps(row) + '\n')

def get_latest_state(req_id):
    state = None
    for r in all_requests():
        if r.get('request_id') == req_id:
            state = r
    return state

def spent_today_gbp():
    today = date.today().isoformat()
    total = 0.0
    for r in all_requests():
        if r.get('event_kind') == 'executed' and r.get('ts','').startswith(today):
            total += float(r.get('actual_cost_gbp', 0) or 0)
    return total

def cmd_propose(args):
    auth = load_auth()
    if args.max_cost_gbp > auth['per_request_cap_gbp']:
        print(f'BLOCKED: max_cost_gbp £{args.max_cost_gbp} > per_request_cap £{auth["per_request_cap_gbp"]}')
        return 1
    if args.vendor not in auth['authorized_vendors']:
        print(f'BLOCKED: vendor {args.vendor!r} not in authorized list: {auth["authorized_vendors"]}')
        return 1
    if args.category not in auth['authorized_categories']:
        print(f'BLOCKED: category {args.category!r} not in authorized list: {auth["authorized_categories"]}')
        return 1
    rid = 'pr_' + uuid.uuid4().hex[:10]
    append_event(rid, 'proposed', {
        'proposer':'wren', 'vendor': args.vendor, 'category': args.category,
        'purpose': args.purpose, 'max_cost_gbp': args.max_cost_gbp,
        'justification': args.justification, 'status':'awaiting_ross_approval',
    })
    print(f'PROPOSED {rid}')
    print(f'  vendor:   {args.vendor}')
    print(f'  category: {args.category}')
    print(f'  purpose:  {args.purpose}')
    print(f'  max £:    {args.max_cost_gbp:.2f}')
    print(f'  status:   awaiting_ross_approval')
    print(f'\nRoss to approve:  python3 tools/qsb_purchase_request.py approve {rid}')
    return 0

def cmd_approve(args):
    state = get_latest_state(args.request_id)
    if not state:
        print(f'NOT FOUND: {args.request_id}'); return 1
    if state.get('status') != 'awaiting_ross_approval':
        print(f'BLOCKED: status is {state.get("status")}, not awaiting_ross_approval'); return 1
    append_event(args.request_id, 'approved', {
        'approver':'ross','status':'approved',
        'note': args.note or '',
    })
    print(f'APPROVED {args.request_id} by Ross')
    print(f'\nWorker may now execute: python3 tools/qsb_purchase_request.py execute {args.request_id} --actual_cost_gbp N')
    return 0

def cmd_decline(args):
    state = get_latest_state(args.request_id)
    if not state: print(f'NOT FOUND'); return 1
    append_event(args.request_id, 'declined', {
        'approver':'ross','status':'declined','note': args.note or '',
    })
    print(f'DECLINED {args.request_id}')
    return 0

def cmd_execute(args):
    state = get_latest_state(args.request_id)
    if not state: print(f'NOT FOUND'); return 1
    if state.get('status') != 'approved':
        print(f'BLOCKED: status is {state.get("status")}, not approved'); return 1
    auth = load_auth()
    if args.actual_cost_gbp > auth['per_request_cap_gbp']:
        print(f'BLOCKED: actual_cost £{args.actual_cost_gbp} > per_request_cap £{auth["per_request_cap_gbp"]}')
        return 1
    today_total = spent_today_gbp()
    if today_total + args.actual_cost_gbp > auth['per_day_cap_gbp']:
        print(f'BLOCKED: would exceed per_day_cap. Spent today £{today_total:.2f} + new £{args.actual_cost_gbp:.2f} > cap £{auth["per_day_cap_gbp"]:.2f}')
        return 1
    if args.actual_cost_gbp > auth['total_available_gbp']:
        print(f'BLOCKED: actual_cost £{args.actual_cost_gbp} > total_available £{auth["total_available_gbp"]:.2f} on the ops float. Fund the float and re-run.')
        return 1
    append_event(args.request_id, 'executed', {
        'executor': args.executor or 'wren_worker',
        'actual_cost_gbp': args.actual_cost_gbp,
        'transaction_id': args.txn_id or '',
        'status':'executed',
    })
    # Decrement available float
    auth['total_available_gbp'] -= args.actual_cost_gbp
    save_auth(auth)
    # Update F44 master book
    if F44.exists():
        b = json.loads(F44.read_text())
    else:
        b = {'ok':True,'kind':'qsb_floor44_master_book','venues':{},'total_packets':0,'advisory_only':True}
    ops = b.setdefault('operational_spend', {'total_gbp':0.0,'rows':[]})
    ops['total_gbp'] += args.actual_cost_gbp
    ops['rows'].append({
        'ts': utcnow(), 'request_id': args.request_id,
        'vendor': state.get('vendor'), 'amount_gbp': args.actual_cost_gbp,
        'purpose': state.get('purpose'),
    })
    b['updated_ts'] = utcnow()
    F44.write_text(json.dumps(b, indent=2))
    print(f'EXECUTED {args.request_id} · £{args.actual_cost_gbp:.2f} spent')
    print(f'  ops float remaining: £{auth["total_available_gbp"]:.2f}')
    print(f'  F44 master book updated')
    return 0

def cmd_list(args):
    by_id = {}
    for r in all_requests():
        by_id[r['request_id']] = {**by_id.get(r['request_id'],{}), **r}
    status_filter = args.status
    rows = list(by_id.values())
    if status_filter:
        rows = [r for r in rows if r.get('status') == status_filter]
    if not rows:
        print('(no requests)')
        return 0
    print(f'{"request_id":<14s} {"status":<22s} {"vendor":<22s} {"max_gbp":>8s} {"purpose"}')
    print('-'*100)
    for r in sorted(rows, key=lambda x:x.get('ts','')):
        print(f"{r.get('request_id',''):<14s} {r.get('status',''):<22s} {r.get('vendor','')[:20]:<22s} £{r.get('max_cost_gbp',0):>7.2f} {r.get('purpose','')[:40]}")
    return 0

def cmd_fund(args):
    """Ross adds money to the ops float — represents transfer from his real account into the ops budget."""
    auth = load_auth()
    auth['total_available_gbp'] += args.amount_gbp
    save_auth(auth)
    append_event('fund', 'funded', {
        'amount_gbp': args.amount_gbp,
        'source': args.source or 'ross_personal',
        'new_balance_gbp': auth['total_available_gbp'],
    })
    print(f'FUNDED ops float +£{args.amount_gbp:.2f}')
    print(f'  new balance: £{auth["total_available_gbp"]:.2f}')
    return 0

def cmd_status(args):
    auth = load_auth()
    today_total = spent_today_gbp()
    print(f'=== F44 Purchase Authorization Status ===')
    print(f'  ops float balance:    £{auth["total_available_gbp"]:.2f}')
    print(f'  per-request cap:      £{auth["per_request_cap_gbp"]:.2f}')
    print(f'  per-day cap:          £{auth["per_day_cap_gbp"]:.2f}')
    print(f'  spent today:          £{today_total:.2f}')
    print(f'  authorized vendors:   {auth["authorized_vendors"]}')
    print(f'  authorized cats:      {auth["authorized_categories"]}')
    by_id = {}
    for r in all_requests():
        by_id[r['request_id']] = {**by_id.get(r['request_id'],{}), **r}
    pending = [r for r in by_id.values() if r.get('status') == 'awaiting_ross_approval']
    approved_not_executed = [r for r in by_id.values() if r.get('status') == 'approved']
    print(f'  pending Ross approval: {len(pending)}')
    print(f'  approved not executed: {len(approved_not_executed)}')

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('propose'); p.add_argument('--vendor', required=True); p.add_argument('--category', required=True); p.add_argument('--purpose', required=True); p.add_argument('--max_cost_gbp', type=float, required=True); p.add_argument('--justification', required=True)
    p = sub.add_parser('approve'); p.add_argument('request_id'); p.add_argument('-n','--note')
    p = sub.add_parser('decline'); p.add_argument('request_id'); p.add_argument('-n','--note')
    p = sub.add_parser('execute'); p.add_argument('request_id'); p.add_argument('--actual_cost_gbp', type=float, required=True); p.add_argument('--txn_id'); p.add_argument('--executor')
    p = sub.add_parser('list'); p.add_argument('--status')
    p = sub.add_parser('fund'); p.add_argument('--amount_gbp', type=float, required=True); p.add_argument('--source')
    p = sub.add_parser('status')
    a = ap.parse_args()
    return {'propose':cmd_propose,'approve':cmd_approve,'decline':cmd_decline,'execute':cmd_execute,'list':cmd_list,'fund':cmd_fund,'status':cmd_status}[a.cmd](a)

if __name__ == '__main__':
    sys.exit(main())
