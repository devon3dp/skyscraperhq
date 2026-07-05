#!/usr/bin/env python3
"""qsb_specialist_certify.py — run the tier ladder on the trader cohort.

For every worker on trading-relevant floors (F41-45) plus the existing 12
"trader"-role workers, walk them through the tier ladder for each instrument
and each strategy. Stamp results to data/registries/qsb_specialist_certs.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

from tower.registry import Registry
from tower.cognitive_kernel.specialist_classroom import (
    ladder_certify, highest_tier_passed, privileges_for,
    list_strategies, list_tiers,
)


# What we want each worker to specialise in
INSTRUMENTS = ["EUR_USD", "GBP_USD", "USD_JPY"]
STRATEGIES = list_strategies()


def is_trader_candidate(w):
    if isinstance(w, dict):
        role = (w.get("role") or "").lower()
        home = str(w.get("home_floor") or "")
    else:
        role = getattr(w, "role", "").lower()
        home = str(getattr(w, "home_floor", ""))
    home_n = None
    if "floor_" in home:
        try: home_n = int(home.split("_")[1])
        except: pass
    elif home.isdigit():
        home_n = int(home)
    # Trading floors F41-45 OR role with trader/scout/spread/strategy/risk
    if home_n in (41, 42, 43, 44, 45): return True
    if any(k in role for k in ("trader", "scout", "spread", "strategy_researcher", "risk_sentinel", "market")):
        return True
    return False


def _now():
    return datetime.now(timezone.utc).isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="cap candidates processed")
    ap.add_argument("--instruments", default=",".join(INSTRUMENTS))
    ap.add_argument("--strategies",  default=",".join(STRATEGIES))
    args = ap.parse_args()

    instruments = [s.strip() for s in args.instruments.split(",") if s.strip()]
    strategies  = [s.strip() for s in args.strategies.split(",")  if s.strip()]

    print(f"[specialist] start {_now()}")
    print(f"  instruments: {instruments}")
    print(f"  strategies:  {strategies}")
    print(f"  tiers:       {list_tiers()}")

    reg = Registry()
    workers = [w for w in reg.workers() if is_trader_candidate(w)]
    print(f"  trader candidates in registry: {len(workers)}")
    if args.limit:
        workers = workers[:args.limit]

    by_tier = {t: 0 for t in list_tiers()}
    by_strategy = {s: 0 for s in strategies}
    masters = []
    rows = []
    for w in workers:
        wid = (w.get("worker_id") or w.get("id")) if isinstance(w, dict) else getattr(w, "worker_id", None)
        if not wid: continue
        for inst in instruments:
            for strat in strategies:
                certs = ladder_certify(wid, inst, strat)
                top = highest_tier_passed(certs)
                if top:
                    by_tier[top] = by_tier.get(top, 0) + 1
                    by_strategy[strat] = by_strategy.get(strat, 0) + 1
                if top == "Master":
                    masters.append({"worker_id": wid, "instrument": inst,
                                     "strategy": strat})
                rows.append({
                    "worker_id": wid, "instrument": inst, "strategy": strat,
                    "highest_tier": top,
                    "privileges": privileges_for(top),
                })

    out = {
        "ok": True,
        "kind": "qsb_specialist_certs_v1",
        "generated_ts": _now(),
        "instruments": instruments,
        "strategies": strategies,
        "candidates_scanned": len(workers),
        "total_certifications_attempted": len(rows),
        "passes_by_tier": by_tier,
        "passes_by_strategy": by_strategy,
        "master_count": len(masters),
        "masters_sample": masters[:30],
        "certs_sample": rows[:80],
        "policy": ("5-tier ladder × 6 strategies × 3 instruments. "
                   "Deterministic by (worker_id, instrument, strategy, tier). "
                   "Top tier reached unlocks tier privileges per "
                   "TIER_PRIVILEGES in specialist_classroom.py."),
        "real_money": False,
        "advisory_only": True,
    }
    path = ROOT / "data/registries/qsb_specialist_certs.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    # Summary
    print()
    print(f"  candidates: {len(workers)}")
    print(f"  certifications attempted: {len(rows)}")
    print(f"  passes by tier: {by_tier}")
    print(f"  passes by strategy: {by_strategy}")
    print(f"  Masters: {len(masters)}")
    if masters[:10]:
        print(f"  first Masters:")
        for m in masters[:6]:
            print(f"    {m['worker_id']:50s} {m['instrument']:7s} {m['strategy']}")
    print(f"  written → {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
