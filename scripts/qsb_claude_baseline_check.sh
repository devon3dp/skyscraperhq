#!/usr/bin/env bash
# Run the signature module against the calibration baselines.
# Flags any sample whose score falls outside its expected band.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
python3 - <<'PY'
import json, sys; sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1")
from src.tower.model_floors.claude_floor.signature import score as sig_score
B = json.load(open("/vaults/nvme0/qsb_tower_v1/data/claude_floor/baselines/baselines.json"))
print("signature baseline check:")
print()
total_fail = 0
for sample in B["samples"]:
    r = sig_score(sample["text"])
    lo, hi = sample["expected_band"]
    s = r["score"]
    ok = lo <= s <= hi
    flag = "✓" if ok else "✗"
    if not ok: total_fail += 1
    print(f"  {flag} {sample['label']:32}  score={s:>5.1f}  expected [{lo},{hi}]")
    if not ok:
        print(f"      verdict: {r['verdict']}")
        for reason in r["reasons"][:3]:
            print(f"      · {reason}")
print()
print(f"calibration: {'pass' if total_fail == 0 else f'{total_fail} sample(s) out of band'}")
PY
