#!/usr/bin/env python3
"""qsb_code_crew_spawn.py — spawns Wren's 100-worker Code Development Crew on F47.

Roles (100):
  1  Crew Lead
 10  Architecture Reviewers
 10  Style/Lint Watchers
 10  Test-Coverage Watchers
 10  Audit Stampers
 10  Documentation Watchers
 10  Refactor Spotters
 10  Backlog Keepers
 10  Forgotten-Item Sniffers
 10  Live-Commentary Broadcasters
  9  Pair Programmers

Writes data/registries/qsb_wren_code_crew_roster.json (the canonical roster).
"""
from __future__ import annotations
import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

REG = Path("/vaults/nvme0/qsb_tower_v1/data/registries")
ROSTER = REG / "qsb_wren_code_crew_roster.json"

NOW = datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

ROLES = [
    ("crew_lead",                "Crew Lead — coordinates the entire code crew, reports to Wren",                                            1),
    ("architect_reviewer",       "Architecture Reviewer — examines new code for fit with tower architecture",                                10),
    ("style_lint_watcher",       "Style/Lint Watcher — catches obvious syntax/style/format issues live",                                     10),
    ("test_coverage_watcher",    "Test-Coverage Watcher — notices when new code lands without a paired test",                                10),
    ("audit_stamper",            "Audit Stamper — writes every code touch to qsb_wren_code_crew_activity.jsonl",                              10),
    ("documentation_watcher",    "Documentation Watcher — flags undocumented public functions/endpoints/APIs",                                10),
    ("refactor_spotter",         "Refactor Spotter — identifies duplicated patterns and code smells",                                         10),
    ("backlog_keeper",           "Backlog Keeper — maintains the open-items list so Wren knows what's pending",                               10),
    ("forgotten_item_sniffer",   "Forgotten-Item Sniffer — checks every prior promise was delivered (Wren's main blind spot)",                10),
    ("live_commentary_broadcaster","Live-Commentary Broadcaster — speaks the running commentary to Ross via the dashboard",                  10),
    ("pair_programmer",          "Pair Programmer — general code support; co-thinks problems with Wren",                                       9),
]

def main():
    roster = []
    idx = 0
    for role_key, role_desc, n in ROLES:
        for k in range(n):
            idx += 1
            wid = "F47.CODE.%03d" % idx
            roster.append({
                "worker_id": wid,
                "role": role_key,
                "role_description": role_desc,
                "team": "wren_code_crew_v1",
                "floor": "F47",
                "department": "Wren's Code Development Crew",
                "reports_to": "F47.CODE.001" if role_key != "crew_lead" else "Wren",
                "spawn_ts": NOW,
                "status": "active",
                "advisory_only": True,
                "responsibilities": role_desc,
            })

    out = {
        "ok": True,
        "kind": "qsb_wren_code_crew_roster",
        "phase": "QSB_TOWER_V1_5_CODE_DEV_CREW_SPAWN_V1",
        "team": "wren_code_crew_v1",
        "team_name": "Wren's Code Development Crew",
        "floor": "F47",
        "department": "Wren's Code Development Crew",
        "lead": "F47.CODE.001",
        "spawned_ts": NOW,
        "total": len(roster),
        "advisory_only": True,
        "purpose": "Watch every code change Wren makes, catch what she forgets, maintain the backlog, talk to Ross live, never let work fall through the cracks.",
        "workers": roster,
    }

    ROSTER.write_text(json.dumps(out, indent=2))
    print(f"✓ wrote {len(roster)} workers → {ROSTER}")
    print(f"  Crew Lead: F47.CODE.001")
    print(f"  Roles: {len(ROLES)}")
    for role_key, _, n in ROLES:
        print(f"    {role_key:30}  {n}")

if __name__ == "__main__":
    main()
