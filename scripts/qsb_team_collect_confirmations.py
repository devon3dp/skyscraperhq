#!/usr/bin/env python3
"""Read the latest roundtable consensus + each reviewer's response, print a confirmation table."""
import json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
state_path = ROOT / "data/registries/qsb_team_consensus_latest.json"

if not state_path.exists():
    print("no consensus yet — run qsb_team_delegate_task.sh first")
    raise SystemExit(1)

s = json.loads(state_path.read_text())
print(f"task: {s['task']}")
print(f"consensus: {s['consensus']}")
print(f"available reviewers: {s['available']}/{len(s['reviewers'])}")
print()
print(f"{'member':<20} {'model':<32} {'verdict':<26} {'wall_s':>8}")
print("-" * 90)
for r in s["results"]:
    print(f"{r['member']:<20} {r['model']:<32} {r['verdict']:<26} {r['wall_s']:>8}")
