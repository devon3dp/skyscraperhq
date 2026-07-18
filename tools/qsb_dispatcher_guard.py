#!/usr/bin/env python3
"""
qsb_dispatcher_guard.py — dispatcher safety (Governance V2, Section 25).

Dispatchers may discover/classify/recommend/admit/assign/notify/collect-progress/
request-verification. Dispatchers may NOT complete, close, self-verify, fabricate
evidence, or bypass Ross approval. This shared guard is imported by every dispatcher;
any completion attempt raises DispatcherCompletionBlocked and is logged.

Built directly by Claude Specialist under Wren, Ross order 2026-07-18. Non-destructive.
"""
import json, os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "registries", "qsb_dispatcher_block_audit.jsonl")

ALLOWED = {"discover", "classify", "recommend_owner", "recommend_partner", "admit",
           "assign", "notify", "collect_progress", "request_verification"}
FORBIDDEN = {"complete", "done", "close", "mark_complete", "self_verify",
             "set_status_done", "set_status_completed", "fabricate_evidence", "bypass_ross"}
FORBIDDEN_ROUTES = {"/tasks/complete", "/tasks/done"}
FORBIDDEN_STATUS = {"done", "completed"}


class DispatcherCompletionBlocked(Exception):
    pass


def _log(action, detail):
    rec = {"ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
           "blocked_action": action, "detail": detail}
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def assert_no_completion(action, *, route=None, status=None, actor="dispatcher"):
    """Raise if a dispatcher attempts to complete/close a task. Call at every dispatcher action."""
    a = (action or "").lower().replace("-", "_").replace(" ", "_")
    if a in FORBIDDEN or route in FORBIDDEN_ROUTES or (status and status.lower() in FORBIDDEN_STATUS):
        _log(action, {"route": route, "status": status, "actor": actor})
        raise DispatcherCompletionBlocked(
            f"BLOCKED: dispatcher '{actor}' attempted completion/close (action={action}, "
            f"route={route}, status={status}). Only an independent active-CEO verifier may complete a task.")
    return True


def is_allowed(action):
    a = (action or "").lower().replace("-", "_").replace(" ", "_")
    return a in ALLOWED


if __name__ == "__main__":
    checks = []
    for bad in ("complete", "mark_complete", "self_verify"):
        try:
            assert_no_completion(bad); checks.append((f"block {bad}", False))
        except DispatcherCompletionBlocked:
            checks.append((f"block {bad}", True))
    try:
        assert_no_completion("assign", route="/tasks/complete"); checks.append(("block /tasks/complete route", False))
    except DispatcherCompletionBlocked:
        checks.append(("block /tasks/complete route", True))
    try:
        assert_no_completion("assign", status="done"); checks.append(("block status=done", False))
    except DispatcherCompletionBlocked:
        checks.append(("block status=done", True))
    # allowed actions pass
    ok = True
    try:
        assert_no_completion("assign"); assert_no_completion("request_verification")
    except DispatcherCompletionBlocked:
        ok = False
    checks.append(("allowed actions pass", ok))
    allok = True
    for n, r in checks:
        print(f"  [{'PASS' if r else 'FAIL'}] {n}"); allok = allok and r
    print("SELF-TEST:", "ALL_PASS" if allok else "SOME_FAIL")
    import sys
    sys.exit(0 if allok else 1)
