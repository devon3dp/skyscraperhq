#!/usr/bin/env python3
"""qsb_f47_fleet_dispatch.py — pick an F47 fleet operative for a task.

Ross 2026-06-14: "have 250 agents that work for you. They're higher than the team."

The fleet is at data/registries/qsb_f47_fleet_roster.json (250 named roles).
This tool finds the best-fit operative by category + specialty keywords and
stamps a team_output row so the operative's contribution is recorded.

Usage:
  python3 tools/qsb_f47_fleet_dispatch.py find --category code_crew --specialty unit_tester
  python3 tools/qsb_f47_fleet_dispatch.py route --task "audit the cockpit JS for stale fetch handlers"
  python3 tools/qsb_f47_fleet_dispatch.py categories
  python3 tools/qsb_f47_fleet_dispatch.py list --category persistence
"""
from __future__ import annotations
import argparse, json, random, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
ROSTER = ROOT / "data/registries/qsb_f47_fleet_roster.json"
OUTPUTS = ROOT / "data/registries/qsb_wren_team_outputs.jsonl"
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"

# Keyword → (category, specialty hint) for the route command.
ROUTE_HINTS = [
    (("test","unit","pytest"),         ("code_crew","unit_tester")),
    (("refactor","cleanup","dedupe"),  ("code_crew","refactor")),
    (("perf","optimize","benchmark"),  ("code_crew","perf_optimizer")),
    (("deploy","ship","release"),      ("code_crew","deploy_engineer")),
    (("css","palette","color","theme"),("design_decoration","colorist")),
    (("ui","layout","button","panel"), ("design_decoration","ui_designer")),
    (("scene","godot","interior"),     ("design_decoration","scene_fitter")),
    (("audit","review","gap"),         ("audit_quality","gap_finder")),
    (("regress","diff","compare"),     ("audit_quality","diff_scanner")),
    (("cite","source","verify"),       ("audit_quality","cite_checker")),
    (("research","web","scout"),       ("research_intel","web_scout")),
    (("doc","spec"),                   ("research_intel","spec_analyst")),
    (("snapshot","buffer","persist"),  ("persistence","snapshot_writer")),
    (("wake","brief","resume"),        ("persistence","briefing_synth")),
    (("supervisor","alert","monitor"), ("persistence","supervisor_watcher")),
    (("queue","dispatch","route"),     ("stewards_coord","dispatch_router")),
    (("vision","camera","depth"),      ("ml_data","vision")),
    (("audio","speech","tts"),         ("ml_data","audio")),
    (("nlp","embedding"),              ("ml_data","nlp")),
    (("trading","oanda","pnl"),        ("domain_specialists","trading_desk_specialist")),
    (("shop","catalog"),               ("domain_specialists","shops_specialist")),
    (("forum","post","triage"),        ("forum_comms","post_triage")),
    (("tannoy","announce","broadcast"),("forum_comms","tannoy_drafter")),
]


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _load_roster() -> dict:
    if not ROSTER.exists():
        print(f"roster not found at {ROSTER}", file=sys.stderr); sys.exit(2)
    return json.loads(ROSTER.read_text())


def _stamp_output(op: dict, task: str, note: str) -> None:
    OUTPUTS.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUTS.open("a") as f:
        f.write(json.dumps({
            "ts": utcnow(),
            "actor": op["id"],
            "category": op["category"],
            "specialty": op["specialty"],
            "task": task,
            "note": note,
            "advisory_only": True,
        }) + "\n")
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": utcnow(),
            "kind": "fleet_dispatch",
            "floor": "F47",
            "operator": op["id"],
            "task": task[:200],
        }) + "\n")


def cmd_categories(_a):
    r = _load_roster()
    print(f"F47 Fleet · {r['total']} operatives · {r['name']}")
    for cat, n in r["category_counts"].items():
        print(f"  {n:3d}  {cat}")
    return 0


def cmd_list(a):
    r = _load_roster()
    ops = [o for o in r["operatives"] if o["category"] == a.category]
    print(f"{a.category}: {len(ops)} operatives")
    for o in ops:
        print(f"  {o['id']:55s} specialty={o['specialty']}")
    return 0


def cmd_find(a):
    r = _load_roster()
    ops = [o for o in r["operatives"]
           if o["category"] == a.category and o["specialty"] == a.specialty]
    if not ops:
        print(f"no operative matches {a.category}/{a.specialty}", file=sys.stderr); return 2
    op = random.choice(ops)
    print(json.dumps(op, indent=2))
    return 0


def cmd_route(a):
    """Match a free-text task to a fleet operative."""
    text = a.task.lower()
    best = None
    for keywords, (cat, sub) in ROUTE_HINTS:
        if any(k in text for k in keywords):
            best = (cat, sub); break
    r = _load_roster()
    if best:
        cat, sub = best
        ops = [o for o in r["operatives"]
               if o["category"] == cat and o["specialty"] == sub]
    else:
        # No hint — pick from stewards_coord/dispatch_router
        cat, sub = "stewards_coord", "dispatch_router"
        ops = [o for o in r["operatives"]
               if o["category"] == cat and o["specialty"] == sub]
    if not ops:
        print(f"no operative for {cat}/{sub}", file=sys.stderr); return 2
    op = random.choice(ops)
    note = f"routed by keyword match → {cat}/{sub}"
    _stamp_output(op, a.task, note)
    print(json.dumps({
        "ok": True,
        "operative": op["id"],
        "category": cat,
        "specialty": sub,
        "task": a.task,
        "note": note,
    }, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("categories"); c.set_defaults(fn=cmd_categories)
    l = sub.add_parser("list"); l.add_argument("--category", required=True); l.set_defaults(fn=cmd_list)
    f = sub.add_parser("find"); f.add_argument("--category", required=True); f.add_argument("--specialty", required=True); f.set_defaults(fn=cmd_find)
    r = sub.add_parser("route"); r.add_argument("--task", required=True); r.set_defaults(fn=cmd_route)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
