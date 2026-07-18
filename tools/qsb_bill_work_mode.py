#!/usr/bin/env python3
"""
qsb_bill_work_mode.py — Bill's concierge/work-mode engine (Governance V2, Section 22).

Bill is Ross's Executive Concierge by DEFAULT. Bill counts as an active CEO ONLY in
verified work mode: mode==work AND enabled AND endpoint_probe_ok AND heartbeat fresh
(<=90s) AND lease not expired AND not suspended. Default after restart = concierge
unless a valid unexpired lease exists.

Built directly by Claude Specialist Service (under Wren), Ross order 2026-07-18.
Non-destructive. State: data/registries/qsb_bill_work_mode.json.
"""
import json, os, sys, uuid
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "data", "registries", "qsb_bill_work_mode.json")


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _load():
    with open(STATE) as f:
        return json.load(f)


def _save(s):
    with open(STATE, "w") as f:
        json.dump(s, f, indent=2)


def _recompute(s):
    """Compute heartbeat age + counts_for_quorum from the six required conditions."""
    now = _now()
    hb = _parse(s.get("last_heartbeat"))
    s["heartbeat_age_seconds"] = int((now - hb).total_seconds()) if hb else None
    lease = _parse(s.get("lease_expires_at"))
    lease_ok = bool(lease and lease > now)
    conds = {
        "mode_work": s.get("mode") == "work",
        "enabled": bool(s.get("enabled")),
        "endpoint_probe_ok": bool(s.get("endpoint_probe_ok")),
        "heartbeat_fresh": s.get("heartbeat_age_seconds") is not None and s["heartbeat_age_seconds"] <= 90,
        "not_suspended": not s.get("suspended"),
        "lease_valid": lease_ok,
    }
    s["counts_for_quorum"] = all(conds.values())
    s["_quorum_conditions"] = conds
    return s


def status():
    return _recompute(_load())


def enable(activator, reason, task_ids=None, lease_seconds=3600):
    s = _load()
    now = _now()
    s.update({
        "mode": "work", "enabled": True, "activated_by": activator,
        "activated_at": _iso(now), "lease_expires_at": _iso(now.fromtimestamp(now.timestamp() + lease_seconds, timezone.utc)),
        "last_heartbeat": _iso(now), "suspended": False,
        "current_task_ids": task_ids or [], "reason": reason,
        "audit_event_id": "GOV2_BILL_" + uuid.uuid4().hex[:12],
    })
    s = _recompute(s)
    _save(s)
    return s


def disable():
    s = _load()
    s.update({"mode": "concierge", "enabled": False, "lease_expires_at": None,
              "current_task_ids": [], "reason": "Returned to concierge mode"})
    s = _recompute(s)
    _save(s)
    return s


def heartbeat(endpoint_ok=None):
    s = _load()
    s["last_heartbeat"] = _iso(_now())
    if endpoint_ok is not None:
        s["endpoint_probe_ok"] = bool(endpoint_ok)
    s = _recompute(s)
    _save(s)
    return s


def renew(lease_seconds=3600):
    s = _load()
    now = _now()
    s["lease_expires_at"] = _iso(datetime.fromtimestamp(now.timestamp() + lease_seconds, timezone.utc))
    s = _recompute(s)
    _save(s)
    return s


def panel_state():
    """Dashboard Bill-panel string."""
    s = status()
    if s.get("suspended"):
        return "SUSPENDED — NOT COUNTED"
    if s.get("mode") != "work" or not s.get("enabled"):
        return "CONCIERGE MODE — NOT COUNTED"
    lease = _parse(s.get("lease_expires_at"))
    if not (lease and lease > _now()):
        return "WORK MODE EXPIRED — NOT COUNTED"
    hb = s.get("heartbeat_age_seconds")
    if not s.get("endpoint_probe_ok") or hb is None or hb > 90:
        return "OFFLINE — NOT COUNTED"
    return "WORK MODE — ACTIVE CEO"


if __name__ == "__main__":
    if "--status" in sys.argv:
        print(json.dumps(status(), indent=2)); sys.exit(0)
    if "--enable" in sys.argv:
        print(json.dumps(enable("ross", "cli enable"), indent=2)); sys.exit(0)
    if "--disable" in sys.argv:
        print(json.dumps(disable(), indent=2)); sys.exit(0)
    if "--heartbeat" in sys.argv:
        print(json.dumps(heartbeat(True), indent=2)); sys.exit(0)
    if "--renew" in sys.argv:
        print(json.dumps(renew(), indent=2)); sys.exit(0)
    # SELF-TEST (non-destructive: snapshot + restore)
    import copy
    orig = _load()
    try:
        checks = []
        disable()
        checks.append(("concierge -> not counted", status()["counts_for_quorum"] is False))
        checks.append(("concierge panel", panel_state() == "CONCIERGE MODE — NOT COUNTED"))
        enable("ross", "selftest", lease_seconds=3600)
        heartbeat(True)
        checks.append(("work+fresh+lease -> counted", status()["counts_for_quorum"] is True))
        checks.append(("work panel", panel_state() == "WORK MODE — ACTIVE CEO"))
        renew(-10)  # expire lease
        checks.append(("expired lease -> not counted", status()["counts_for_quorum"] is False))
        allok = True
        for n, r in checks:
            print(f"  [{'PASS' if r else 'FAIL'}] {n}"); allok = allok and r
        print("SELF-TEST:", "ALL_PASS" if allok else "SOME_FAIL")
    finally:
        _save(orig)  # restore original concierge default
    sys.exit(0)
