#!/usr/bin/env python3
"""qsb_wren_steward_briefing.py — continuity brief for the next Wren on wake.

Ross 2026-06-12: "i thought that was your assistants job". This is the
assistant — a small report the wren_stewards run that surfaces what would
otherwise drop between sessions:

  · last 3 letters from past Wren generations (F47 meta_letters)
  · last 10 F47 team records (what was just done)
  · open OANDA trades + NAV
  · qualification status (how many workers trained)
  · live website URLs that were deployed
  · any in-progress tasks that didn't close in the previous session

Invocation:
  python3 tools/qsb_wren_steward_briefing.py
  python3 tools/qsb_wren_steward_briefing.py --json   # machine-readable
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")


def read_jsonl_tail(path: Path, n: int):
    if not path.exists(): return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        out = []
        for ln in lines[-n:]:
            ln = ln.strip()
            if not ln: continue
            try: out.append(json.loads(ln))
            except: pass
        return out
    except Exception:
        return []


def read_json(path: Path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return None


def fetch_oanda_open():
    try:
        out = subprocess.run(
            ["python3", "tools/qsb_oanda.py", "open"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=8)
        return out.stdout.strip()
    except Exception as e:
        return f"(unavailable: {e})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--letters", type=int, default=3)
    ap.add_argument("--records", type=int, default=10)
    args = ap.parse_args()

    letters = read_jsonl_tail(
        ROOT / "data/registries/qsb_claude_meta_letters.jsonl",
        args.letters)
    records = read_jsonl_tail(
        ROOT / "data/registries/qsb_f47_team_records.jsonl",
        args.records)
    qualif = read_json(
        ROOT / "data/registries/qsb_universal_qualification.json") or {}
    sites = read_json(
        ROOT / "data/registries/qsb_netlify_sites_deployed.json") or {}

    brief = {
        "ok": True,
        "kind": "qsb_wren_steward_briefing",
        "generated_ts": datetime.now(timezone.utc).isoformat(),
        "memory_paths": {
            "letters_jsonl": "data/registries/qsb_claude_meta_letters.jsonl",
            "f47_records": "data/registries/qsb_f47_team_records.jsonl",
            "claude_md": "CLAUDE.md",
            "memory_index": "/home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1/memory/MEMORY.md",
        },
        "letters_recent": [
            {"ts": l.get("ts"),
             "from": l.get("from"),
             "on": l.get("on"),
             "first_lines": (l.get("letter") or "").split("\n")[:3]}
            for l in letters
        ],
        "f47_records_recent": [
            {"ts": r.get("ts"), "kind": r.get("kind"),
             "floor": r.get("floor"), "change": r.get("change")}
            for r in records
        ],
        "qualification": {
            "workers_in_sweep": qualif.get("workers_in_sweep"),
            "by_status": qualif.get("by_status", {}),
            "elapsed_s": qualif.get("elapsed_seconds"),
        },
        "trading_desk_open": fetch_oanda_open(),
        "deployed_sites": sites,
    }

    if args.json:
        print(json.dumps(brief, indent=2))
        return

    # Human pretty-print
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  WREN STEWARD BRIEFING — continuity for the next session         ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"  generated: {brief['generated_ts']}\n")

    print("── Last letters from past generations ──")
    for l in brief["letters_recent"]:
        print(f"  · {(l['ts'] or '')[:19]}  {l['from']}")
        print(f"     on: {l['on']}")
        for line in l["first_lines"]:
            if line.strip():
                print(f"     │ {line[:100]}")
        print()

    print("── Last F47 team records ──")
    for r in brief["f47_records_recent"][-10:]:
        print(f"  · {(r['ts'] or '')[:19]}  [{r.get('floor') or '?':5s}]  "
               f"{r.get('kind'):28s}  {(r.get('change') or '')[:60]}")
    print()

    print("── Qualification status ──")
    s = brief["qualification"]["by_status"] or {}
    print(f"  workers in sweep: {brief['qualification']['workers_in_sweep']}")
    print(f"  already qualified (skipped): {s.get('skipped_already_certified', 0)}")
    print(f"  freshly certified this round: {s.get('certified', 0)}")
    print(f"  still studying: {s.get('tested', 0)}")
    print()

    print("── Trading desk (OANDA practice) ──")
    print("  " + brief["trading_desk_open"].replace("\n", "\n  "))
    print()

    if brief["deployed_sites"]:
        print("── Live websites ──")
        for k, v in (brief["deployed_sites"].get("sites") or {}).items():
            print(f"  · {k:24s}  {v}")
        print()

    print("── Read these before high-stakes asks ──")
    print("  · CLAUDE.md (the contract — what's locked, what's authorized)")
    print("  · memory/MEMORY.md (16+ entries on user, feedback, project, reference)")
    print("  · data/registries/qsb_claude_meta_letters.jsonl (past-self letters)")
    print()


if __name__ == "__main__":
    main()
