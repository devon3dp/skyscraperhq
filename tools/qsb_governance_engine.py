#!/usr/bin/env python3
"""
qsb_governance_engine.py — Governance V2 Task Council rules engine (pure functions).

Implements the canonical lifecycle, two-active-CEO quorum, risk-scaling,
no-self-verification, ABSTAIN + task-local reassignment (no global freeze), and
dynamic capacity. No live-gate writes — this is the decision core the live Task
Council will call once Governance V2 is ACTIVE.

Built directly by the Claude Specialist Service (under Wren), Ross order 2026-07-18.
Non-destructive new file. Claude/AI models/receptionist/coder-workers NEVER count as CEOs.
"""

LIFECYCLE = [
    "INTAKE", "RISK_CLASSIFICATION", "ADMITTED",
    "OWNER_ASSIGNMENT_REQUIRED", "OWNER_ASSIGNED",
    "PARTNER_ASSIGNMENT_REQUIRED", "PARTNER_ASSIGNED",
    "RESEARCH", "BACKUP_GATE", "SAFETY_GATE", "EXECUTION",
    "EVIDENCE_CAPTURE", "AWAITING_INDEPENDENT_VERIFICATION",
    "CORRECTION_REQUIRED", "VERIFIED", "AWAITING_ROSS",
    "COMPLETED", "REPORTED", "ARCHIVED",
]
CONTROLLED = {
    "PAUSED", "BLOCKED", "OWNER_REASSIGNMENT_REQUIRED", "PARTNER_REASSIGNMENT_REQUIRED",
    "CANCEL_REQUESTED", "CANCEL_REVIEW", "CANCELLED", "RESUME_REQUESTED", "REOPENED",
    "FAILED_SAFE", "ROLLBACK_REQUIRED", "ROLLED_BACK",
}
# canonical forward transitions (plus correction loop)
_FORWARD = {LIFECYCLE[i]: LIFECYCLE[i + 1] for i in range(len(LIFECYCLE) - 1)}
_EXTRA = {
    ("AWAITING_INDEPENDENT_VERIFICATION", "CORRECTION_REQUIRED"),
    ("CORRECTION_REQUIRED", "EXECUTION"),
    ("VERIFIED", "AWAITING_ROSS"),
    ("AWAITING_ROSS", "COMPLETED"),
}

# identities that NEVER count as an active CEO
NON_CEO = {"claude_specialist", "hq_claude", "receptionist", "ai_model", "coder_worker"}


def can_transition(frm, to):
    if frm not in LIFECYCLE and frm not in CONTROLLED:
        return False
    # never jump straight from EXECUTION to COMPLETED
    if frm == "EXECUTION" and to == "COMPLETED":
        return False
    if _FORWARD.get(frm) == to:
        return True
    if (frm, to) in _EXTRA:
        return True
    # entering a controlled state from anywhere active is allowed
    if to in CONTROLLED:
        return True
    return False


def active_ceos(roster, presence, bill_work_mode):
    """Return the list of CEO ids currently counting toward quorum.
    roster: policy['roster']; presence: {id: {'online':bool,'hb_age_s':int}}
    bill_work_mode: dict from qsb_bill_work_mode (must expose counts_for_quorum)."""
    out = []
    for l in roster.get("leaders", []):
        cid = l["id"]
        if cid in NON_CEO:
            continue
        p = presence.get(cid, {})
        fresh = bool(p.get("online")) and (p.get("hb_age_s") is None or p.get("hb_age_s") <= 90)
        if l.get("conditional"):  # Bill
            if bill_work_mode and bill_work_mode.get("counts_for_quorum") and fresh:
                out.append(cid)
        elif fresh:
            out.append(cid)
    return out


def abstain(leader):
    return {"leader": leader, "state": "ABSTAIN — OFFLINE",
            "is_agreement": False, "is_rejection": False, "freezes_unrelated": False}


def no_self_verify(owner, verifier):
    """True if the pairing is allowed (owner != verifier)."""
    return owner is not None and verifier is not None and owner != verifier


def quorum_ok(risk, owner, verifier, active_list, ross_approval=False, extra_ceos=None):
    """Governance V2 quorum. Returns (ok, reason)."""
    risk = (risk or "normal").lower()
    active = set(active_list or [])
    if owner not in active:
        return (False, f"owner {owner} is not an active CEO")
    if not no_self_verify(owner, verifier):
        return (False, "owner cannot verify their own work (owner == verifier)")
    if verifier not in active:
        return (False, f"verifier {verifier} is not an active CEO")
    distinct = {owner, verifier} | set(extra_ceos or [])
    if risk == "normal":
        return (len(distinct & active) >= 2, "need 2 distinct active CEOs")
    if risk in ("high", "high_risk", "high-risk"):
        if len(distinct & active) >= 3:
            return (True, "3 active CEOs")
        if len(distinct & active) >= 2 and ross_approval:
            return (True, "2 active CEOs + Ross approval")
        return (False, "high-risk needs 3 CEOs OR 2 CEOs + Ross approval")
    if risk == "critical":
        if not ross_approval:
            return (False, "critical needs Ross explicit approval")
        return (len(distinct & active) >= 2, "critical needs Ross approval + >=1 independent verifier")
    return (False, f"unknown risk {risk}")


def on_leader_lost(role):
    """Task-local reassignment — never a global freeze."""
    if role == "owner":
        return "OWNER_REASSIGNMENT_REQUIRED"
    if role in ("partner", "verifier"):
        return "PARTNER_REASSIGNMENT_REQUIRED"
    return "BLOCKED"


def capacity(active_ceo_count):
    return {"system_max": min(active_ceo_count * 3, 12), "per_ceo_max": 3}


def can_complete(task):
    """Completion gate: all evidence + independent verifier + report present."""
    reasons = []
    if not task.get("checklist_all_pass"):
        reasons.append("mandatory checklist not all PASS")
    if not task.get("evidence_hashes"):
        reasons.append("no evidence hashes recorded")
    if not no_self_verify(task.get("owner"), task.get("ceo_verifier")):
        reasons.append("verifier is the owner (self-verification)")
    if task.get("risk") in ("high", "high_risk", "critical") and not task.get("ross_approval"):
        reasons.append("risk requires Ross approval")
    if not task.get("final_report"):
        reasons.append("no final report")
    return (len(reasons) == 0, reasons)


if __name__ == "__main__":
    # SELF-TEST — real assertions, printed PASS/FAIL
    R = {"leaders": [
        {"id": "wren"}, {"id": "tp_pip"}, {"id": "acer_cass"},
        {"id": "bill", "conditional": True}]}
    fresh = {"online": True, "hb_age_s": 5}
    off = {"online": False, "hb_age_s": 9999}
    checks = []
    # 2-CEO normal ok
    act = active_ceos(R, {"wren": fresh, "tp_pip": fresh, "acer_cass": off, "bill": off},
                      {"counts_for_quorum": False})
    ok, why = quorum_ok("normal", "wren", "tp_pip", act)
    checks.append(("2-CEO normal admits", ok is True))
    # owner==verifier rejected
    ok, why = quorum_ok("normal", "wren", "wren", act)
    checks.append(("owner self-verify rejected", ok is False))
    # Bill concierge excluded
    act2 = active_ceos(R, {"wren": fresh, "bill": fresh}, {"counts_for_quorum": False})
    checks.append(("Bill concierge not counted", "bill" not in act2))
    # Bill work-mode counted
    act3 = active_ceos(R, {"wren": fresh, "bill": fresh}, {"counts_for_quorum": True})
    checks.append(("Bill work-mode counted", "bill" in act3))
    # one offline -> ABSTAIN not freeze
    ab = abstain("acer_cass")
    checks.append(("offline = ABSTAIN not freeze", ab["freezes_unrelated"] is False))
    # capacity math
    checks.append(("capacity 2 CEOs = 6", capacity(2)["system_max"] == 6))
    checks.append(("capacity 4 CEOs = 12", capacity(4)["system_max"] == 12))
    # no EXECUTION->COMPLETED
    checks.append(("no EXECUTION->COMPLETED", can_transition("EXECUTION", "COMPLETED") is False))
    checks.append(("EVIDENCE->AWAITING_VERIFY ok", can_transition("EVIDENCE_CAPTURE", "AWAITING_INDEPENDENT_VERIFICATION") is True))
    allok = True
    for name, res in checks:
        print(f"  [{'PASS' if res else 'FAIL'}] {name}")
        allok = allok and res
    print("SELF-TEST:", "ALL_PASS" if allok else "SOME_FAIL")
    import sys
    sys.exit(0 if allok else 1)
