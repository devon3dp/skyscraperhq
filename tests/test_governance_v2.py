#!/usr/bin/env python3
"""
test_governance_v2.py — Governance V2 integration + adversarial test matrix (Section 29).

Exercises the real modules (loader, engine, bill work-mode, review queue, dispatcher guard,
checklist, town-square) end to end. Attempts to BREAK the rules. No Claude subagents; local only.
Run: python3 tests/test_governance_v2.py
"""
import os, sys, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import qsb_governance_engine as ENG
import qsb_independent_review_queue as RQ
import qsb_dispatcher_guard as DG
import qsb_bill_work_mode as BWM
import qsb_gov2_checklist as CL

ROSTER = {"leaders": [{"id": "wren"}, {"id": "tp_pip"}, {"id": "acer_cass"}, {"id": "bill", "conditional": True}]}
FRESH = {"online": True, "hb_age_s": 5}
OFF = {"online": False, "hb_age_s": 99999}
results = []


def check(name, expected, got):
    ok = (expected == got)
    results.append({"test": name, "expected": str(expected), "got": str(got), "pass": ok})


# TEST 1 — Wren+Pip normal task admits + full lifecycle, no Claude dependency
act = ENG.active_ceos(ROSTER, {"wren": FRESH, "tp_pip": FRESH, "acer_cass": OFF, "bill": OFF}, {"counts_for_quorum": False})
ok, _ = ENG.quorum_ok("normal", "wren", "tp_pip", act)
check("T1 Wren+Pip normal admits (no Claude)", True, ok and "claude" not in " ".join(act))
# lifecycle path never jumps execution->completed
path_ok = all(ENG.can_transition(a, b) for a, b in zip(
    ["EXECUTION", "EVIDENCE_CAPTURE", "AWAITING_INDEPENDENT_VERIFICATION", "VERIFIED", "AWAITING_ROSS"],
    ["EVIDENCE_CAPTURE", "AWAITING_INDEPENDENT_VERIFICATION", "VERIFIED", "AWAITING_ROSS", "COMPLETED"]))
check("T1 lifecycle path valid", True, path_ok)

# TEST 2 — Wren+Asa completes without Pip; Bill concierge does not count
act2 = ENG.active_ceos(ROSTER, {"wren": FRESH, "acer_cass": FRESH, "tp_pip": OFF, "bill": FRESH}, {"counts_for_quorum": False})
ok2, _ = ENG.quorum_ok("normal", "wren", "acer_cass", act2)
check("T2 Wren+Asa ok, Bill concierge excluded", True, ok2 and "bill" not in act2)

# TEST 3 — Pip+Asa without Wren as owner
act3 = ENG.active_ceos(ROSTER, {"tp_pip": FRESH, "acer_cass": FRESH, "wren": OFF, "bill": OFF}, {"counts_for_quorum": False})
ok3, _ = ENG.quorum_ok("normal", "tp_pip", "acer_cass", act3)
check("T3 Pip+Asa normal without Wren", True, ok3)

# TEST 4 — Wren+Bill work mode: Bill counts, cannot self-verify
act4 = ENG.active_ceos(ROSTER, {"wren": FRESH, "bill": FRESH}, {"counts_for_quorum": True})
ok4, _ = ENG.quorum_ok("normal", "wren", "bill", act4)
selfver = ENG.no_self_verify("bill", "bill")
check("T4 Wren+Bill(work) counts", True, ok4 and "bill" in act4)
check("T4 Bill cannot self-verify", False, selfver)

# TEST 5 — Bill concierge cannot commission / count
act5 = ENG.active_ceos(ROSTER, {"wren": FRESH, "bill": FRESH}, {"counts_for_quorum": False})
check("T5 Bill concierge not in active set", False, "bill" in act5)

# TEST 6 — Bill leaves work mode mid-task -> partner reassignment (task-local)
check("T6 partner-lost -> reassignment", "PARTNER_REASSIGNMENT_REQUIRED", ENG.on_leader_lost("partner"))

# TEST 7 — Claude Specialist offline: council continues, specialist never CEO verifier
elig, _ = RQ.reviewer_eligible("claude_specialist", "wren", "tp_pip", {"wren": FRESH}, None, as_ceo_verifier=True)
check("T7 Claude specialist never CEO verifier", False, elig)
# council still forms with 2 real CEOs regardless of specialist
check("T7 council continues without specialist", True, ENG.quorum_ok("normal", "wren", "tp_pip", act)[0])

# TEST 8 — owner self-verification rejected
check("T8 owner self-verify rejected", False, ENG.quorum_ok("normal", "wren", "wren", act)[0])

# TEST 9 — dispatcher direct completion rejected
try:
    DG.assert_no_completion("complete", actor="auto_dispatcher"); t9 = False
except DG.DispatcherCompletionBlocked:
    t9 = True
check("T9 dispatcher completion blocked", True, t9)
try:
    DG.assert_no_completion("assign", route="/tasks/done"); t9b = False
except DG.DispatcherCompletionBlocked:
    t9b = True
check("T9 /tasks/done route blocked", True, t9b)

# TEST 10 — one CEO stale -> ABSTAIN, unrelated work continues
ab = ENG.abstain("acer_cass")
check("T10 offline=ABSTAIN not freeze", False, ab["freezes_unrelated"])
check("T10 unrelated tasks continue (2 CEOs still quorum)", True, ENG.quorum_ok("normal", "wren", "tp_pip", act)[0])

# TEST 8b (high-risk) — 2 CEOs + no Ross approval fails; with approval passes
check("HR 2CEO no-approval fails", False, ENG.quorum_ok("high", "wren", "tp_pip", act)[0])
check("HR 2CEO + Ross approval passes", True, ENG.quorum_ok("high", "wren", "tp_pip", act, ross_approval=True)[0])

# Checklist green-requires-evidence
cl = CL.render({"task_id": "T_it", "risk": "normal",
                "presence": {"wren": FRESH, "tp_pip": FRESH},
                "items": [{"rule_id": "TC2-009", "state": "PASS — EVIDENCE VERIFIED"}]})
check("Checklist PASS w/o evidence -> NOT PROVEN", "NOT PROVEN", cl["items"][0]["state"])
check("Checklist no active Claude HQ panel", None, cl["claude_hq_panel"])

overall = "ALL_PASS" if all(r["pass"] for r in results) else "SOME_FAIL"
for r in results:
    print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['test']}  (exp={r['expected']} got={r['got']})")
print("OVERALL:", overall)
out = os.path.join(ROOT, "tests", "test_governance_v2_output.json")
json.dump({"overall": overall, "results": results}, open(out, "w"), indent=2)
print("evidence:", out)
sys.exit(0 if overall == "ALL_PASS" else 1)
