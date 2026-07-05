#!/usr/bin/env python3
"""qsb_message_board.py — tower-wide internal announcements."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from datetime import datetime, timezone

REG = Path('/vaults/nvme0/qsb_tower_v1/data/registries')
BOARD = REG / 'qsb_message_board.jsonl'

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def cmd_post(a):
    msg_id = f'msg_{int(datetime.now().timestamp())}'
    row = {'ts': utcnow(),'msg_id': msg_id,'title': a.title,'body': a.body,
           'priority': a.priority,'audience': a.audience,'posted_by': a.author}
    with BOARD.open('a') as f: f.write(json.dumps(row)+'\n')
    Path(REG, 'qsb_f47_team_records.jsonl').open('a').write(json.dumps({
        'ts': row['ts'],'kind':'message_board_post','role':'wren',
        'summary': f'{a.priority.upper()}: {a.title}','msg_id': msg_id,'advisory_only': True})+'\n')
    print(f'✓ posted {msg_id}: {a.title}')

def cmd_list(a):
    if not BOARD.exists(): print('(empty)'); return
    msgs = [json.loads(l) for l in BOARD.read_text().strip().split('\n') if l.strip()]
    for m in msgs[-a.limit:]:
        print(f'[{m["ts"][:19]}] [{m.get("priority","normal"):6s}] {m["title"]}')
        print(f'  {m["body"][:140]}...\n')

def cmd_latest(a):
    if not BOARD.exists(): print('(empty)'); return
    msgs = [json.loads(l) for l in BOARD.read_text().strip().split('\n') if l.strip()]
    if not msgs: return
    m = msgs[-1]
    print(f'LATEST: {m["title"]}\n  by {m.get("posted_by")} at {m["ts"]}\n\n{m["body"]}')

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('post'); p.add_argument('--title', required=True); p.add_argument('--body', required=True); p.add_argument('--priority', choices=['normal','high','critical'], default='normal'); p.add_argument('--audience', default='all'); p.add_argument('--author', default='wren')
    p = sub.add_parser('list'); p.add_argument('--limit', type=int, default=10)
    p = sub.add_parser('latest')
    a = ap.parse_args()
    {'post':cmd_post,'list':cmd_list,'latest':cmd_latest}[a.cmd](a)

if __name__ == '__main__':
    main()
