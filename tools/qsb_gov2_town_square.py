#!/usr/bin/env python3
"""
qsb_gov2_town_square.py — Governance V2 Task Council -> Town Square event bridge (Section 27).

Emits governed, structured task events to data/registries/qsb_gov2_task_events.jsonl AND posts a
human-readable summary to the EXISTING Town Square (via tools/qsb_town_square.post_to_town_square).
Every event carries a TRUTH_STATUS and the policy version+hash. Truth is never inflated:
QUEUED != DELIVERED != ACKNOWLEDGED != INSTALLED != VERIFIED.

Built directly by Claude Specialist under Wren, Ross order 2026-07-18. Non-destructive (new file,
appends to a new events log; posts to existing town square). Integrates existing surfaces, invents none.
"""
import json, os, sys, uuid
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
EVENTS = os.path.join(ROOT, "data", "registries", "qsb_gov2_task_events.jsonl")

EVENT_TYPES = {
    "TASK_CREATED", "TASK_ADMITTED", "TASK_OWNER_ASSIGNED", "TASK_PARTNER_ASSIGNED",
    "WORK_PACKAGE_ASSIGNED", "WORK_STARTED", "PROGRESS_UPDATE", "EVIDENCE_ADDED",
    "VERIFICATION_REQUESTED", "CORRECTION_REQUIRED", "TASK_VERIFIED", "AWAITING_ROSS",
    "TASK_COMPLETED", "TASK_REPORTED", "TASK_ARCHIVED", "TASK_PAUSED", "TASK_BLOCKED",
    "TASK_CANCEL_REQUESTED", "TASK_CANCELLED", "TASK_RESUMED", "OWNER_REASSIGNMENT_REQUIRED",
    "PARTNER_REASSIGNMENT_REQUIRED", "BILL_MODE_CHANGED", "POLICY_CHANGED",
    "WORKER_ONLINE", "WORKER_OFFLINE", "CLAUDE_SPECIALIST_ONLINE", "CLAUDE_SPECIALIST_OFFLINE",
}
TRUTH = {"OBSERVED", "VERIFIED", "REPORTED", "QUEUED", "UNKNOWN", "FAILED"}


def _policy():
    try:
        from qsb_governance_loader import load_pointer
        p = load_pointer()
        return p.get("proposed_version") or p.get("active_version"), p.get("sha256")
    except Exception:
        return "governance_v2", None


def emit_event(event_type, task_id, actor, actor_role, summary,
               evidence_path=None, truth_status="OBSERVED", post_town_square=True):
    et = (event_type or "").upper()
    if et not in EVENT_TYPES:
        raise ValueError(f"unknown event_type {event_type}")
    if truth_status not in TRUTH:
        raise ValueError(f"invalid truth_status {truth_status}")
    ver, sha = _policy()
    rec = {
        "EVENT_ID": "EVT_" + uuid.uuid4().hex[:12],
        "TIMESTAMP": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "TASK_ID": task_id, "ACTOR": actor, "ACTOR_ROLE": actor_role,
        "EVENT_TYPE": et, "SUMMARY": summary, "EVIDENCE_PATH": evidence_path,
        "POLICY_VERSION": ver, "POLICY_HASH": sha, "TRUTH_STATUS": truth_status,
    }
    with open(EVENTS, "a") as f:
        f.write(json.dumps(rec) + "\n")
    if post_town_square:
        try:
            from qsb_town_square import post_to_town_square
            post_to_town_square("task_council",
                                f"[{et}] {task_id} · {summary} · truth={truth_status}", to="council")
            rec["_town_square_posted"] = True
        except Exception as e:
            rec["_town_square_posted"] = False
            rec["_town_square_error"] = str(e)
    return rec


def tail(n=20):
    if not os.path.exists(EVENTS):
        return []
    return [json.loads(l) for l in open(EVENTS) if l.strip()][-n:]


if __name__ == "__main__":
    if "--tail" in sys.argv:
        for r in tail():
            print(r["TIMESTAMP"], r["EVENT_TYPE"], r["TASK_ID"], r["TRUTH_STATUS"], "-", r["SUMMARY"])
        sys.exit(0)
    # SELF-TEST
    checks = []
    r = emit_event("TASK_CREATED", "T_selftest", "wren", "owner", "gov2 self-test event",
                   truth_status="OBSERVED", post_town_square=False)
    checks.append(("event written with policy hash", bool(r["POLICY_HASH"]) and r["EVENT_TYPE"] == "TASK_CREATED"))
    try:
        emit_event("TOTALLY_FAKE", "T", "wren", "owner", "x", post_town_square=False); checks.append(("reject unknown event", False))
    except ValueError:
        checks.append(("reject unknown event", True))
    try:
        emit_event("TASK_CREATED", "T", "wren", "owner", "x", truth_status="DELIVERED", post_town_square=False)
        checks.append(("reject invalid truth_status (no QUEUED->DELIVERED inflation)", False))
    except ValueError:
        checks.append(("reject invalid truth_status (no QUEUED->DELIVERED inflation)", True))
    allok = True
    for n, res in checks:
        print(f"  [{'PASS' if res else 'FAIL'}] {n}"); allok = allok and res
    print("SELF-TEST:", "ALL_PASS" if allok else "SOME_FAIL")
    sys.exit(0 if allok else 1)
