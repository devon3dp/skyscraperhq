#!/usr/bin/env python3
"""
qsb_gov2_checklist.py — Governance V2 live evidence checklist (Section 26).

Renders a task's checklist as JSON for the dashboards: four leader panels (WREN, PIP, ASA,
BILL) — NO Claude HQ active panel. Claude Specialist appears separately as an OPTIONAL
SPECIALIST SERVICE (non-voting). Green requires evidence: any PASS lacking an evidence_sha256
is downgraded to 'NOT PROVEN'. Header shows policy version + central/local hash + match.

Built directly by Claude Specialist under Wren, Ross order 2026-07-18. Non-destructive new file.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

ITEM_STATES = {"NOT STARTED", "IN PROGRESS", "PASS — EVIDENCE VERIFIED", "FAIL", "BLOCKED",
               "NOT PROVEN", "N/A — REASON REQUIRED", "AWAITING PEER", "AWAITING ROSS",
               "OFFLINE", "ABSTAIN", "CANCEL REQUESTED", "CANCEL REVIEW", "CANCELLED",
               "RESUME REQUESTED", "REASSIGNMENT REQUIRED"}


def _policy_header():
    try:
        from qsb_governance_loader import load_pointer, _sha256
        ptr = load_pointer()
        central = ptr.get("sha256")
        local = _sha256(os.path.join(ROOT, ptr["policy_json"]))
        return {"policy_version": ptr.get("proposed_version") or ptr.get("active_version"),
                "policy_status": ptr.get("status"),
                "central_policy_sha256": central, "local_policy_sha256": local,
                "policy_match": central == local}
    except Exception as e:
        return {"policy_version": "unknown", "error": str(e)}


def _bill_panel():
    try:
        from qsb_bill_work_mode import panel_state, status
        return {"identity": "bill", "display": "Bill", "state": panel_state(),
                "counts": status().get("counts_for_quorum", False)}
    except Exception as e:
        return {"identity": "bill", "display": "Bill", "state": "OFFLINE — NOT COUNTED", "error": str(e)}


def _grade(item):
    """Enforce green-requires-evidence: PASS with no evidence hash -> NOT PROVEN."""
    st = item.get("state", "NOT STARTED")
    if st == "PASS — EVIDENCE VERIFIED" and not item.get("evidence_sha256"):
        item = dict(item, state="NOT PROVEN", _downgraded="no evidence_sha256")
    if st not in ITEM_STATES and item.get("state") not in ITEM_STATES:
        item["state"] = "NOT STARTED"
    return item


def render(task):
    """task: {task_id, risk, presence{}, items[], claude_specialist{optional}}"""
    presence = task.get("presence", {})
    def ceo(cid, disp):
        p = presence.get(cid, {})
        online = bool(p.get("online")) and (p.get("hb_age_s") is None or p.get("hb_age_s") <= 90)
        return {"identity": cid, "display": disp, "state": "ONLINE" if online else "OFFLINE — ABSTAIN", "counts": online}
    panels = [ceo("wren", "Wren"), ceo("tp_pip", "Pip"), ceo("acer_cass", "Asa"), _bill_panel()]
    items = [_grade(dict(it)) for it in task.get("items", [])]
    green = sum(1 for it in items if it["state"] == "PASS — EVIDENCE VERIFIED")
    not_proven = sum(1 for it in items if it["state"] == "NOT PROVEN")
    return {
        "task_id": task.get("task_id"),
        "risk": task.get("risk", "normal"),
        "header": _policy_header(),
        "leader_panels": panels,
        "claude_hq_panel": None,  # RETIRED — never shown as active
        "specialist_panel": {"identity": "claude_specialist", "display": "Claude Specialist Floor",
                             "kind": "OPTIONAL SPECIALIST SERVICE", "counts": False,
                             "available": task.get("claude_specialist", {}).get("available", True)},
        "items": items,
        "summary": {"total": len(items), "green_evidenced": green, "not_proven": not_proven},
    }


if __name__ == "__main__":
    sample = {
        "task_id": "T_demo", "risk": "normal",
        "presence": {"wren": {"online": True, "hb_age_s": 4}, "tp_pip": {"online": True, "hb_age_s": 8},
                     "acer_cass": {"online": False}},
        "items": [
            {"rule_id": "TC2-003", "requirement": "two distinct active CEOs", "responsible": "wren",
             "role": "owner", "mandatory": True, "evidence_type": "log", "evidence_location": "tests/x.txt",
             "evidence_sha256": "abc123", "verifier": "tp_pip", "state": "PASS — EVIDENCE VERIFIED", "blocking_effect": "blocks"},
            {"rule_id": "TC2-009", "requirement": "evidence required", "responsible": "wren", "role": "owner",
             "mandatory": True, "state": "PASS — EVIDENCE VERIFIED", "blocking_effect": "blocks"},  # NO hash -> must downgrade
        ],
    }
    out = render(sample)
    checks = []
    checks.append(("no active Claude HQ panel", out["claude_hq_panel"] is None))
    checks.append(("Claude Specialist separate + non-voting", out["specialist_panel"]["counts"] is False))
    checks.append(("4 leader panels (Wren/Pip/Asa/Bill)", [p["identity"] for p in out["leader_panels"]] == ["wren", "tp_pip", "acer_cass", "bill"]))
    checks.append(("PASS w/o evidence -> NOT PROVEN", out["items"][1]["state"] == "NOT PROVEN"))
    checks.append(("PASS w/ evidence stays green", out["items"][0]["state"] == "PASS — EVIDENCE VERIFIED"))
    checks.append(("policy hash shown", "central_policy_sha256" in out["header"]))
    allok = True
    for n, r in checks:
        print(f"  [{'PASS' if r else 'FAIL'}] {n}"); allok = allok and r
    print("SELF-TEST:", "ALL_PASS" if allok else "SOME_FAIL")
    sys.exit(0 if allok else 1)
