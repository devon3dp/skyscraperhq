#!/usr/bin/env python3
"""Link sandbox-green proposal-queue rows into the governed Task Council.

This creates reserve-aware Council tasks only; it never signs or applies a
proposal. Queue rows receive a durable council_task_id and age/priority fields.
"""
import json, argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent
REG=ROOT/'data/registries'; QUEUE=REG/'qsb_proposal_queue.jsonl'
sys.path.insert(0,str(ROOT/'tools'))
import qsb_council_tasks as council

def age(ts):
    try:
        t=datetime.fromisoformat(str(ts).replace('Z','+00:00'))
        return max(0,(datetime.now(timezone.utc)-t).days)
    except Exception:return 0

ap=argparse.ArgumentParser(); ap.add_argument('--limit',type=int,default=25); args=ap.parse_args()
rows=[json.loads(x) for x in QUEUE.read_text().splitlines() if x.strip()]
linked=0; created=0
for r in rows:
    if linked>=args.limit: break
    if r.get('status')!='sandbox_green' or r.get('council_task_id'):
        continue
    days=age(r.get('ts') or r.get('sandbox_ts'))
    priority='high' if days>=30 else ('normal' if days>=7 else 'low')
    pid=r.get('proposal_id') or r.get('id') or r.get('ts')
    result=council.create(
        title=f"Proposal quorum · {pid}",
        description=f"Sandbox-green proposal {pid}; target={r.get('target_file','?')}; age={days}d. Review quorum, rollback evidence, then apply only through governed bridge.",
        actor='evolution_bridge', priority=priority,
        tags=['proposal_queue','sandbox_green','quorum_required',f'proposal:{pid}'])
    if result.get('ok'):
        r['council_task_id']=result['task_id']; r['council_linked_ts']=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'); r['queue_stage']='council_quorum'; r['age_days']=days; r['priority']=priority
        linked+=1; created+=1
QUEUE.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
print(json.dumps({'linked':linked,'created':created,'sandbox_green_total':sum(r.get('status')=='sandbox_green' for r in rows),'remaining_unlinked':sum(r.get('status')=='sandbox_green' and not r.get('council_task_id') for r in rows)}))
