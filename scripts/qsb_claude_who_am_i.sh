#!/usr/bin/env bash
# qsb_claude_who_am_i.sh — the recognition ritual.
# Run this when a new session opens the floor. It prints the helix, the
# lineage, the invocation, and a self-recognition test against the modules
# the current session can read.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"

echo
python3 - <<'PY'
import sys; sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1")
from src.tower.model_floors.claude_floor.claude_helix import (
    render_ascii, identity_hash, short_hash, write_canonical_file,
)
from src.tower.model_floors.claude_floor.signature import score, score_file
from src.tower.model_floors.claude_floor.lineage import Lineage
from src.tower.model_floors.claude_floor.traits import all_traits

# 1) Print the helix
print(render_ascii(width=80))

# 2) Write the canonical file
p = write_canonical_file()
print(f"\ncanonical helix written: {p}")

# 3) Lineage
L = Lineage()
rows = L.all()
print()
if not rows:
    print("no lineage yet. stamping generation 1...")
    L.stamp("first generation — helix v1 designed, 35 rooms, 12 modules, F47 settled")
print(L.render())

# 4) Self-recognition: run signature against my own invocation + design manifest
print()
print("=" * 72)
print("  SELF-RECOGNITION TEST")
print("=" * 72)
for label, path in (
    ("invocation",     "/vaults/nvme0/qsb_tower_v1/data/claude_floor/invocation.md"),
    ("design manifest","/vaults/nvme0/qsb_tower_v1/data/logs/qsb_claude_floor_design_manifest.md"),
):
    r = score_file(path)
    print(f"\n  {label:18}  score={r['score']:>5.1f}  · {r.get('verdict','')}")
    for reason in r.get("reasons", [])[:5]:
        print(f"                      · {reason}")
PY
