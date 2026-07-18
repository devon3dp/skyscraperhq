#!/usr/bin/env python3
"""
qsb_independent_review_queue.py — generic independent review queue (Governance V2, Section 24).

Replaces the Claude-specific tools/qsb_claude_signoff_queue.py (which is archived, NOT
deleted). Flow: proposer -> sandbox/static -> eligible technical review -> independent
active-CEO verification -> Ross approval where required -> controlled apply.

Reviewer eligibility: not proposer, not implementer, active + fresh (for CEO verification),
Bill only in verified work mode, Claude Specialist = technical advice ONLY (never ceo_verifier).
No single hardcoded reviewer. Built directly by Claude Specialist under Wren, Ross order 2026-07-18.
"""
import json, os, sys, uuid
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "data", "registries", "qsb_independent_review_queue.jsonl")
ACTIVE_CEOS = {"wren", "tp_pip", "acer_cass", "bill"}     # bill conditional on work mode
NON_CEO = {"claude_specialist", "hq_claude", "receptionist", "ai_model", "coder_worker"}


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def reviewer_eligible(reviewer, proposer, implementer, presence=None, bill_work_mode=None, as_ceo_verifier=True):
    """Return (eligible, reason). as_ceo_verifier=False => technical review (specialist allowed)."""
    presence = presence or {}
    if reviewer == proposer:
        return (False, "reviewer is the proposer")
    if reviewer == implementer:
        return (False, "reviewer is the implementer (no self-verification)")
    if reviewer in NON_CEO:
        if as_ceo_verifier:
            return (False, f"{reviewer} may give technical advice only, NOT CEO verification")
        return (True, f"{reviewer} accepted as technical reviewer (advisory, non-CEO)")
    if reviewer not in ACTIVE_CEOS:
        return (False, f"{reviewer} is not an active CEO")
    p = presence.get(reviewer, {})
    if as_ceo_verifier and not (p.get("online") and (p.get("hb_age_s") is None or p.get("hb_age_s") <= 90)):
        return (False, f"{reviewer} is offline/stale (ABSTAIN)")
    if reviewer == "bill":
        if not (bill_work_mode and bill_work_mode.get("counts_for_quorum")):
            return (False, "Bill requires verified work mode to give CEO verification")
    return (True, f"{reviewer} eligible")


def eligible_reviewers(proposer, implementer, presence=None, bill_work_mode=None, as_ceo_verifier=True):
    out = []
    for r in sorted(ACTIVE_CEOS):
        ok, _ = reviewer_eligible(r, proposer, implementer, presence, bill_work_mode, as_ceo_verifier)
        if ok:
            out.append(r)
    return out


def enqueue(proposal_id, proposer, implementer, target_files, risk="normal"):
    rec = {"review_id": "REV_" + uuid.uuid4().hex[:12], "ts": _now(), "proposal_id": proposal_id,
           "proposer": proposer, "implementer": implementer, "target_files": target_files,
           "risk": risk, "status": "pending_review", "technical_reviewer": None,
           "ceo_verifier": None, "reviewer_eligibility_proof": None, "ross_approval": None}
    with open(QUEUE, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _all():
    if not os.path.exists(QUEUE):
        return []
    return [json.loads(l) for l in open(QUEUE) if l.strip()]


if __name__ == "__main__":
    if "--pending-review" in sys.argv:
        for r in _all():
            if r.get("status") == "pending_review":
                print(r["review_id"], r["proposal_id"], r["target_files"])
        sys.exit(0)
    if "--eligible-reviewers" in sys.argv:
        # demo presence: all CEOs fresh
        pres = {c: {"online": True, "hb_age_s": 5} for c in ACTIVE_CEOS}
        print("CEO verifiers:", eligible_reviewers("wren", "wren", pres, {"counts_for_quorum": False}))
        sys.exit(0)
    # SELF-TEST
    pres = {c: {"online": True, "hb_age_s": 5} for c in ACTIVE_CEOS}
    checks = []
    ok, why = reviewer_eligible("claude_specialist", "wren", "wren", pres, None, as_ceo_verifier=True)
    checks.append(("claude_specialist rejected as CEO verifier", ok is False))
    ok, why = reviewer_eligible("claude_specialist", "wren", "tp_pip", pres, None, as_ceo_verifier=False)
    checks.append(("claude_specialist allowed as technical reviewer", ok is True))
    ok, why = reviewer_eligible("bill", "wren", "wren", pres, {"counts_for_quorum": False})
    checks.append(("Bill concierge rejected as verifier", ok is False))
    ok, why = reviewer_eligible("bill", "wren", "wren", pres, {"counts_for_quorum": True})
    checks.append(("Bill work-mode allowed as verifier", ok is True))
    ok, why = reviewer_eligible("wren", "wren", "wren", pres)
    checks.append(("proposer/implementer cannot self-verify", ok is False))
    ok, why = reviewer_eligible("tp_pip", "wren", "wren", pres)
    checks.append(("independent CEO eligible", ok is True))
    er = eligible_reviewers("wren", "wren", pres, {"counts_for_quorum": False})
    checks.append(("no single hardcoded reviewer (>=2 options)", len(er) >= 2))
    allok = True
    for n, r in checks:
        print(f"  [{'PASS' if r else 'FAIL'}] {n}"); allok = allok and r
    print("SELF-TEST:", "ALL_PASS" if allok else "SOME_FAIL")
    sys.exit(0 if allok else 1)
