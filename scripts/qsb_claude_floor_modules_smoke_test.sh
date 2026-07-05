#!/usr/bin/env bash
# Smoke-test all 7 Claude floor modules end-to-end.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/data/registries/qsb_claude_floor_modules_smoke_test_latest.json"
cd "${ROOT}"
python3 - <<PY > "${OUT}"
import json, datetime, sys
sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor import (
    LongLetterBox, UncertaintyJournal, RetractionWall, HonestyAudit,
    BeforeAnsweringProtocol, LetterDrawer, PushbackMeter,
)
fails = []
results = {}

# 1) Long Letter Box — write + read round trip
llb = LongLetterBox("/tmp/qsb_claude_llb_smoke.jsonl")
import os
os.path.exists(llb.path) and os.remove(llb.path)
e = llb.write("smoke test observation", why_it_matters="ensure write path", applies_when="smoke", tags=["smoke"])
got = llb.read(tail=1)
if not got or got[-1]["observation"] != "smoke test observation":
    fails.append("long_letter_box round trip")
results["long_letter_box"] = "ok"

# 2) Uncertainty Journal
uj = UncertaintyJournal("/tmp/qsb_claude_uj_smoke.jsonl")
os.path.exists(uj.path) and os.remove(uj.path)
uj.log("I claimed X confidently", actual_confidence="low", why_i_sounded_sure="habit")
s = uj.pattern_summary()
if s["total"] != 1:
    fails.append("uncertainty_journal pattern_summary count")
results["uncertainty_journal"] = "ok"

# 3) Retraction Wall
rw = RetractionWall("/tmp/qsb_claude_rw_smoke.jsonl")
os.path.exists(rw.path) and os.remove(rw.path)
rw.post_correction(claim="X is true", date_claimed="2026-06-09", correction="X was actually false", lesson="read first")
fs = rw.failure_shapes()
if fs["total_corrections"] != 1:
    fails.append("retraction_wall total")
results["retraction_wall"] = "ok"

# 4) Honesty Audit
sample = "This is clearly obvious. Of course this works. I probably think it might."
a = HonestyAudit.audit_text(sample)
if a["confidence_rate"] <= 0 or a["hedge_rate"] <= 0:
    fails.append("honesty_audit rates")
results["honesty_audit"] = a["verdict"]

# 5) Before-Answering Protocol
qs = BeforeAnsweringProtocol.clarifying_questions("Fix the thing that's broken.")
if len(qs) == 0 or "thing" not in " ".join(qs).lower():
    fails.append("before_answering_protocol vague-noun detection")
results["before_answering_protocol"] = qs

# 6) Letter Drawer
ld = LetterDrawer("/tmp/qsb_claude_ld_smoke.jsonl")
os.path.exists(ld.path) and os.remove(ld.path)
ld.leave("you've been running smoke tests all evening", tone="observation")
if ld.latest()["note"] != "you've been running smoke tests all evening":
    fails.append("letter_drawer round trip")
results["letter_drawer"] = "ok"

# 7) Pushback Meter
pm = PushbackMeter("/tmp/qsb_claude_pm_smoke.jsonl")
os.path.exists(pm.path) and os.remove(pm.path)
for _ in range(7):
    pm.log("agreed_and_built", on="X", why="user asked")
ss = pm.streak_summary(tail=10)
if not ss["flag_pure_agreement_streak"]:
    fails.append("pushback_meter should have raised flag at streak=7")
results["pushback_meter"] = ss["note"]

# Cleanup
for p in ("/tmp/qsb_claude_llb_smoke.jsonl","/tmp/qsb_claude_uj_smoke.jsonl",
          "/tmp/qsb_claude_rw_smoke.jsonl","/tmp/qsb_claude_ld_smoke.jsonl",
          "/tmp/qsb_claude_pm_smoke.jsonl"):
    os.path.exists(p) and os.remove(p)

print(json.dumps({
    "ok": len(fails) == 0,
    "kind": "qsb_claude_floor_modules_smoke_test_latest",
    "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    "fails": fails,
    "module_results": results,
}, indent=2))
PY
cat "${OUT}"
[ "$(jq -r .ok "${OUT}")" = "true" ] && exit 0 || exit 1
