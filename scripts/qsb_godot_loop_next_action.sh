#!/usr/bin/env bash
# qsb_godot_loop_next_action.sh — print the next planned patch from backlog.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"

python3 - <<PY
import json
from pathlib import Path
backlog = Path("${ROOT}/data/registries/qsb_godot_autonomous_loop_backlog.json")
if not backlog.exists():
    print("(no backlog yet)")
else:
    d = json.load(open(backlog))
    items = d.get("items", [])
    if not items:
        print("(backlog empty)")
    else:
        nxt = sorted(items, key=lambda x: ("P0P1P2P3".find(x.get("priority","P9")), -x.get("score_lift",0)))[0]
        print("NEXT ACTION:")
        print(f"  priority:    {nxt.get('priority','?')}")
        print(f"  description: {nxt.get('description','?')}")
        print(f"  target file: {nxt.get('target_file','?')}")
        print(f"  expected score lift: +{nxt.get('score_lift','?')}")
PY
