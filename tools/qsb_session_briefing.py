#!/usr/bin/env python3
"""qsb_session_briefing.py — generate a session briefing for new conversations.

Reads recent F47 records, current state, open loops, recent advisor input.
Writes a single markdown brief Wren reads at start of next session.

Usage:
  qsb_session_briefing.py             # generate + print briefing
  qsb_session_briefing.py --save      # save to data/registries/qsb_session_briefing.md
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
REG  = ROOT / 'data/registries'

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--save', action='store_true')
    a = ap.parse_args()
    
    out = ['# QSB Tower · Session Briefing', '',
           f'*Generated {utcnow()}*', '']
    
    # Tower state from canonical endpoint
    import urllib.request
    try:
        with urllib.request.urlopen('http://localhost:8765/api/tower/state', timeout=3) as r:
            state = json.loads(r.read())
        out.append('## State Today')
        out.append(f'- Floors: **{state["floors_count"]}**')
        out.append(f'- Workers: **{state["workers_unique"]:,}**')
        out.append(f'- Certified: **{state["certified_traders"]}**')
        o = state['oanda_practice']
        out.append(f'- OANDA: £{o["realized_gbp"]} realized · {o["open_trades"]} open · {o["closed_trades"]} closed')
        out.append(f'- LSE F60: £{state["lse_paper"]["cash_gbp"]:,.2f} · {state["lse_paper"]["position_count"]} positions')
        out.append(f'- F44 packets: {state["f44_master_book"]["total_packets"]} · venues {state["f44_master_book"]["venues_count"]}')
        out.append(f'- F47 records today: **{state["f47_records_today"]}**')
        out.append(f'- Ops float: £{state["ops_float_gbp"]}')
        out.append(f'- Provider spend: ${state["provider_spend_today_usd"]} / $5.00')
    except Exception as e:
        out.append(f'## State (dashboard offline: {e})')
    
    out.append('')
    
    # Last 8 F47 records
    f47 = REG / 'qsb_f47_team_records.jsonl'
    if f47.exists():
        recent = [json.loads(l) for l in f47.read_text().strip().split('\n')[-12:] if l.strip()]
        out.append('## Last 12 actions (F47)')
        for r in recent:
            out.append(f'- **[{r.get("ts","?")[11:19]}]** `{r.get("kind","?")}` — {(r.get("summary","") or "")[:140]}')
        out.append('')
    
    # Open purchase requests + ops float
    auth = REG / 'qsb_purchase_authorization.json'
    if auth.exists():
        try:
            a_data = json.loads(auth.read_text())
            out.append('## Money')
            out.append(f'- Ops float: £{a_data.get("total_available_gbp", 0):.2f}')
            out.append(f'- Per-request cap: £{a_data.get("per_request_cap_gbp", 100):.2f}')
            out.append(f'- Per-day cap: £{a_data.get("per_day_cap_gbp", 200):.2f}')
            out.append('')
        except: pass
    
    # Owned domains
    dom = REG / 'qsb_owned_domains_v1.json'
    if dom.exists():
        try:
            d = json.loads(dom.read_text())
            out.append('## Owned Domains')
            for x in d.get('domains',[]):
                out.append(f'- {x["domain"]} · £{x.get("cost_gbp_approx","?")} · {x.get("role","?")}')
            out.append('')
        except: pass
    
    # Public state
    out.append('## Public State')
    out.append('- Public tunnel: https://exterior-these-ambassador-regions.trycloudflare.com')
    out.append('- GitHub repo: https://github.com/devon3dp/skyscraperhq (private)')
    out.append('- Stripe: LIVE + verified (test mode in tower)')
    out.append('- Netlify: deploy pending Ross click')
    out.append('')
    
    out.append('## Open Loops')
    out.append('- DNS records → Namecheap for skyscraperhq.uk')
    out.append('- Stripe LIVE secret key → flip 150 Payment Links live')
    out.append('- Ticker UI rebuild (in progress)')
    out.append('- Template packets in /api/unified (need replacement)')
    
    txt = '\n'.join(out)
    if a.save:
        (REG / 'qsb_session_briefing.md').write_text(txt)
        print(f'✓ saved to {REG}/qsb_session_briefing.md')
    else:
        print(txt)

if __name__ == '__main__':
    main()
