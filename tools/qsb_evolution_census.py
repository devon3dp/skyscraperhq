#!/usr/bin/env python3
"""qsb_evolution_census.py — tower-wide worker + database census + evolution rate.

Produces three artefacts:
  · data/registries/qsb_tower_census_latest.json
  · data/registries/qsb_evolution_rate.json
  · data/registries/qsb_tower_census_history.jsonl (append-only timeseries)

Evolution rate per-day deltas across:
  · floors active
  · workers employed
  · F47 records stamped
  · activity tail events
  · trades placed (alpaca + binance + lse + oanda)
  · cohort certifications
  · news headlines
  · inter-floor packets

Usage: python3 tools/qsb_evolution_census.py
"""
from __future__ import annotations
import json, re, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
REG  = ROOT / 'data/registries'

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def norm_floor(v):
    if v is None: return None
    s = str(v).upper().strip()
    m = re.match(r'F?(\d+)', s)
    return int(m.group(1)) if m else None

ROSTER_GLOBS = [
    'qsb_*roster*.json','qsb_*workers*.json','qsb_*staff*.json','qsb_*team*.json',
    'qsb_f*_*.json','qsb_floor*_workers*.json','qsb_floor*_lse_workers.json',
    'qsb_floor41_oanda_workers.json','qsb_floor60_lse_workers.json','qsb_shop_floors_workers_v1.json',
    'qsb_strategy_research_team_v1.json','qsb_themed_workforce_v1_roster.json',
    'qsb_expansion_v1_roster.json','qsb_baseline_floor_workforce.json',
    'qsb_graphics_team_v1_roster.json','qsb_service_staff_v1_roster.json',
    'qsb_f59_shopping_staff_v1.json','qsb_floor66_architects_workers.json',
]
SKIP_ROSTERS = {'qsb_canonical_workers.json'}  # empty

def walk_rosters():
    seen_files = set()
    workers_by_id = {}
    by_floor = defaultdict(int)
    by_team  = Counter()
    active = withassign = withhours = withrole = 0
    for pat in ROSTER_GLOBS:
        for p in REG.glob(pat):
            if p.name in seen_files or p.name in SKIP_ROSTERS: continue
            seen_files.add(p.name)
            try: d = json.loads(p.read_text())
            except: continue
            ws = d.get('workers', d if isinstance(d, list) else [])
            if not isinstance(ws, list): continue
            for w in ws:
                if not isinstance(w, dict): continue
                wid = w.get('worker_id')
                if not wid or wid in workers_by_id: continue
                workers_by_id[wid] = w
                flr = norm_floor(w.get('floor') or w.get('floor_number') or w.get('floor_id'))
                if flr is not None: by_floor[flr] += 1
                team = w.get('team','none')
                by_team[team] += 1
                if w.get('status') == 'employed': active += 1
                if w.get('daily_assignment') or w.get('today_assignment') or w.get('current_task'): withassign += 1
                if w.get('hours'): withhours += 1
                if w.get('role'): withrole += 1
    return workers_by_id, dict(by_floor), dict(by_team), active, withassign, withhours, withrole

def walk_registries_freshness():
    files = []
    for p in REG.glob('*.json'):
        try:
            sz = p.stat().st_size
            age_s = time.time() - p.stat().st_mtime
            files.append({'name':p.name,'size_bytes':sz,'age_seconds':int(age_s)})
        except: pass
    for p in REG.glob('*.jsonl'):
        try:
            sz = p.stat().st_size
            age_s = time.time() - p.stat().st_mtime
            rows = sum(1 for _ in p.open())
            files.append({'name':p.name,'size_bytes':sz,'age_seconds':int(age_s),'rows':rows})
        except: pass
    return files

def daily_deltas(today_str, yesterday_str=None):
    def count_today(p, ts_field='ts'):
        if not p.exists(): return 0
        if p.suffix == '.jsonl':
            n = 0
            for ln in p.open():
                try:
                    if today_str in ln.split('"%s"' % ts_field)[1][:30] if '"%s"' % ts_field in ln else False:
                        n += 1
                except: pass
            return n
        return 0
    deltas = {}
    # Simpler: read whole files and bucket by date
    for name in [
        'qsb_f47_team_records.jsonl',
        'qsb_tower_activity_tail.jsonl',
        'qsb_floor44_master_ledger.jsonl',
        'qsb_cohort_training_runs.jsonl',
        'qsb_market_news_feed.jsonl',
        'qsb_arb_candidates.jsonl',
        'qsb_provider_spend_ledger.jsonl',
        'qsb_floor27_terminal_transcript.jsonl',
        'qsb_floor60_lse_paper_ledger.jsonl',
        'qsb_floor43_alpaca_paper_orders.jsonl',
    ]:
        p = REG / name
        if not p.exists():
            deltas[name] = {'today':0,'yesterday':0}
            continue
        today_n = yest_n = 0
        for ln in p.open():
            if today_str in ln[:60]: today_n += 1
            elif yesterday_str and yesterday_str in ln[:60]: yest_n += 1
        deltas[name] = {'today': today_n, 'yesterday': yest_n}
    return deltas

def main():
    workers, by_floor, by_team, active, withassign, withhours, withrole = walk_rosters()
    files = walk_registries_freshness()
    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    deltas = daily_deltas(today, yesterday)
    floor_dirs = len(list((ROOT/'floors').glob('floor_*')))

    census = {
        'ok': True, 'kind':'qsb_tower_census_latest','generated_ts': utcnow(),
        'tower_size':{
            'floor_directories': floor_dirs,
            'floors_with_workers': len(by_floor),
            'total_unique_workers': len(workers),
            'employed_active': active,
            'with_role_assigned': withrole,
            'with_daily_assignment': withassign,
            'with_hours_set': withhours,
            'pct_active': round(active/len(workers)*100, 2) if workers else 0,
            'pct_with_assignment': round(withassign/len(workers)*100, 2) if workers else 0,
            'pct_with_hours': round(withhours/len(workers)*100, 2) if workers else 0,
        },
        'workers_per_floor': by_floor,
        'workers_per_team': by_team,
        'top_15_floors_by_population': dict(sorted(by_floor.items(), key=lambda x:-x[1])[:15]),
        'top_15_teams': Counter(by_team).most_common(15),
        'registry_files': {
            'total_files': len(files),
            'jsonl_files': sum(1 for f in files if 'rows' in f),
            'fresh_under_1h': sum(1 for f in files if f['age_seconds'] < 3600),
            'stale_over_24h': sum(1 for f in files if f['age_seconds'] > 86400),
            'top_growing': sorted([f for f in files if 'rows' in f], key=lambda x:-x.get('rows',0))[:10],
        },
        'evolution_today_vs_yesterday': deltas,
        'advisory_only': True,
    }
    (REG/'qsb_tower_census_latest.json').write_text(json.dumps(census, indent=2))

    # Evolution rate (per-day deltas + composite index)
    total_today = sum(d['today'] for d in deltas.values())
    total_yest = sum(d['yesterday'] for d in deltas.values())
    growth_pct = ((total_today - total_yest) / total_yest * 100) if total_yest else None
    evolution = {
        'ok': True, 'kind':'qsb_evolution_rate','generated_ts': utcnow(),
        'today': today, 'yesterday': yesterday,
        'event_total_today': total_today,
        'event_total_yesterday': total_yest,
        'growth_pct': growth_pct,
        'per_stream_today': {k:v['today'] for k,v in deltas.items()},
        'per_stream_yesterday': {k:v['yesterday'] for k,v in deltas.items()},
        'composite_velocity_index': round((total_today / 24), 2),  # events per hour
        'tower_volume':{
            'floors': floor_dirs,
            'workers': len(workers),
        },
        'velocity_categories':{
            'records_per_hour': round(deltas.get('qsb_f47_team_records.jsonl',{}).get('today',0)/24, 2),
            'activity_events_per_hour': round(deltas.get('qsb_tower_activity_tail.jsonl',{}).get('today',0)/24, 2),
            'trades_per_hour': round((deltas.get('qsb_floor44_master_ledger.jsonl',{}).get('today',0)+
                                       deltas.get('qsb_floor60_lse_paper_ledger.jsonl',{}).get('today',0)+
                                       deltas.get('qsb_floor43_alpaca_paper_orders.jsonl',{}).get('today',0))/24, 2),
            'news_headlines_per_hour': round(deltas.get('qsb_market_news_feed.jsonl',{}).get('today',0)/24, 2),
        },
        'advisory_only': True,
    }
    (REG/'qsb_evolution_rate.json').write_text(json.dumps(evolution, indent=2))

    # Append to history
    with (REG/'qsb_tower_census_history.jsonl').open('a') as f:
        snap = {
            'ts': utcnow(),
            'floors': floor_dirs,
            'workers': len(workers),
            'records_today': deltas.get('qsb_f47_team_records.jsonl',{}).get('today',0),
            'activity_today': deltas.get('qsb_tower_activity_tail.jsonl',{}).get('today',0),
            'velocity_per_hour': evolution['composite_velocity_index'],
        }
        f.write(json.dumps(snap)+'\n')

    print(f"=== CENSUS ===")
    print(f"  floor dirs:      {floor_dirs}")
    print(f"  unique workers:  {len(workers)}")
    print(f"  employed active: {active} ({census['tower_size']['pct_active']}%)")
    print(f"  with role:       {withrole} ({withrole/len(workers)*100:.1f}%)")
    print(f"  with assignment: {withassign} ({census['tower_size']['pct_with_assignment']}%)")
    print(f"  with hours set:  {withhours} ({census['tower_size']['pct_with_hours']}%)")
    print(f"  fresh files <1h: {census['registry_files']['fresh_under_1h']}")
    print(f"  stale files>24h: {census['registry_files']['stale_over_24h']}")
    print(f"=== EVOLUTION ===")
    print(f"  events today:    {total_today}")
    print(f"  events yesterday:{total_yest}")
    print(f"  growth %:        {growth_pct}")
    print(f"  velocity/hr:     {evolution['composite_velocity_index']} events/hr")
    print(f"  records/hr:      {evolution['velocity_categories']['records_per_hour']}")
    print(f"  trades/hr:       {evolution['velocity_categories']['trades_per_hour']}")
    print(f"  news/hr:         {evolution['velocity_categories']['news_headlines_per_hour']}")

if __name__ == '__main__':
    main()
