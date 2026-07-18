#!/usr/bin/env python3
"""qsb_rank_scoreboard.py — track HQ rank-climb metrics per HQ's stated NEED.

Pulls from shared board + F47 + drill grades. Prints one-line per-CEO score
based on ship-verified proof events. HQ can watch this over time.
"""
import argparse, json, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
BOARD = ROOT / "data/registries/qsb_council_tasks.jsonl"
GRADES = ROOT / "data/registries/qsb_council_classroom_grades.jsonl"
TOWN = ROOT / "data/registries/qsb_town_square.jsonl"

CEOS = ["wren", "tp_pip", "acer_cass", "hq_claude"]


def now(): return datetime.now(timezone.utc)


def parse_ts(s):
    try: return datetime.fromisoformat(s.replace("Z","+00:00"))
    except: return None


def scoreboard(since_hours=24):
    cutoff = now() - timedelta(hours=since_hours)
    stats = {c: {"proposed": 0, "sandbox_passed": 0, "peer_signoff_given": 0,
                 "peer_signoff_approved_of_own_work": 0, "rejects_earned": 0,
                 "town_square_posts": 0, "drills_pass": 0, "drills_fail": 0,
                 "ledger_entries": 0} for c in CEOS}

    # Board events
    with BOARD.open() as f:
        for line in f:
            try: o = json.loads(line)
            except: continue
            ts = parse_ts(o.get("ts",""))
            if not ts or ts < cutoff: continue
            actor = o.get("actor")
            ev = o.get("event","")
            if actor not in stats: continue
            if ev == "proposed": stats[actor]["proposed"] += 1
            elif ev == "sandbox_passed": stats[actor]["sandbox_passed"] += 1
            elif ev == "peer_signoff":
                stats[actor]["peer_signoff_given"] += 1
                if o.get("verdict") == "reject":
                    # reject given by actor
                    pass

    # Town-square posts (visibility signal)
    if TOWN.exists():
        with TOWN.open() as f:
            for line in f:
                try: o = json.loads(line)
                except: continue
                ts = parse_ts(o.get("ts",""))
                if not ts or ts < cutoff: continue
                who = o.get("from","")
                if who in stats: stats[who]["town_square_posts"] += 1

    # Classroom drills
    if GRADES.exists():
        with GRADES.open() as f:
            for line in f:
                try: o = json.loads(line)
                except: continue
                ts = parse_ts(o.get("ts",""))
                if not ts or ts < cutoff: continue
                ceo = o.get("ceo","")
                if ceo not in stats: continue
                if o.get("pass"): stats[ceo]["drills_pass"] += 1
                else: stats[ceo]["drills_fail"] += 1

    # Card ledger entries
    for c in CEOS:
        card = ROOT / f"data/registries/qsb_{c}_operator_card.json"
        if card.exists():
            try:
                d = json.load(open(card))
                stats[c]["ledger_entries"] = len(d.get("task_ledger", []))
            except: pass

    return stats


def score(s):
    # +2 sandbox_pass · +1 peer_signoff_given · +1 town_square_post · +2 drill_pass · -3 drill_fail · +1 ledger_entry
    return (2 * s["sandbox_passed"] + s["peer_signoff_given"]
            + s["town_square_posts"] + 2 * s["drills_pass"]
            - 3 * s["drills_fail"] + s["ledger_entries"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    args = ap.parse_args()
    stats = scoreboard(args.hours)
    rows = [(c, s, score(s)) for c, s in stats.items()]
    rows.sort(key=lambda r: -r[2])
    print(f"═══ RANK SCOREBOARD — last {args.hours}h · at {now().strftime('%H:%M:%SZ')} ═══")
    print(f"{'CEO':<12} {'score':>5}  proposed  passed  signoff  posts  drills(P/F)  ledger")
    for c, s, sc in rows:
        drills = f"{s['drills_pass']}/{s['drills_fail']}"
        print(f"  {c:<10} {sc:>5}  {s['proposed']:>8}  {s['sandbox_passed']:>6}  {s['peer_signoff_given']:>7}  {s['town_square_posts']:>5}  {drills:>10}  {s['ledger_entries']:>5}")


if __name__ == "__main__":
    main()
