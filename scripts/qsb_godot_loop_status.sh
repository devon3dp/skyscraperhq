#!/usr/bin/env bash
# qsb_godot_loop_status.sh — show current loop state + score.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"

python3 - <<PY
import json, os
from pathlib import Path
ROOT = Path("${ROOT}")

def load(name):
    p = ROOT / "data/registries" / name
    if not p.exists(): return {}
    try: return json.load(open(p))
    except: return {}

state = load("qsb_godot_autonomous_loop_state.json")
score = load("qsb_godot_autonomous_loop_score.json")
gates_chk = load("qsb_godot_production_readiness_gate_check.json")
backlog = load("qsb_godot_autonomous_loop_backlog.json")

print("============================================================")
print("  QSB Godot · Autonomous Production Loop · Status")
print("============================================================")
print(f"  current iteration:   {state.get('iteration', 0)}")
print(f"  total iterations:    {state.get('total_iterations_run', 0)}")
print(f"  loop status:         {state.get('status', 'unknown')}")
print(f"  reason_for_stop:     {state.get('reason_for_stop', '—')}")
print(f"  last launch_status:  {state.get('last_launch_status', '—')}")
print()
print(f"  gates passed:        {gates_chk.get('passed', '—')} / {gates_chk.get('total', '—')}")
print(f"  gates partial:       {gates_chk.get('partial', '—')}")
print(f"  gates failed:        {gates_chk.get('failed', '—')}")
print(f"  current score:       {gates_chk.get('score', '—')} / 100")
print()
items = backlog.get("items", [])
if items:
    print(f"  backlog ({len(items)} items):")
    for i in items[:6]:
        print(f"    · [{i.get('priority','?')}] {i.get('description','?')}")
PY
