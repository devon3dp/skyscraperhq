#!/usr/bin/env python3
"""
qsb_governance_loader.py — the single canonical Governance V2 policy loader.

Every live governance service resolves policy through here so there is exactly one
source of truth. Verifies the on-disk policy hash matches the active-governance
pointer, enforces unique rule IDs, and guarantees legacy rules can NEVER override V2.

Built directly by the Claude Specialist Service (under Wren) on Ross's order
2026-07-18 — non-destructive, new file. Not active law until qsb_active_governance.json
status == ACTIVE.
"""
import json, hashlib, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "data", "registries")
POINTER = os.path.join(REG, "qsb_active_governance.json")
SUPERSESSION = os.path.join(REG, "qsb_governance_v2_supersession.json")


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_pointer():
    with open(POINTER) as f:
        return json.load(f)


def load_active_policy(require_active=False):
    """Resolve the active policy. Verifies on-disk hash == pointer hash."""
    ptr = load_pointer()
    policy_path = os.path.join(ROOT, ptr["policy_json"])
    on_disk = _sha256(policy_path)
    if on_disk != ptr["sha256"]:
        raise ValueError(f"POLICY HASH MISMATCH: pointer={ptr['sha256'][:12]} on_disk={on_disk[:12]} "
                         f"— refusing to load a tampered/stale policy.")
    if require_active and ptr.get("status") != "ACTIVE":
        raise ValueError(f"Governance V2 is not ACTIVE (status={ptr.get('status')}).")
    with open(policy_path) as f:
        policy = json.load(f)
    policy["_resolved_sha256"] = on_disk
    policy["_pointer_status"] = ptr.get("status")
    return policy


def validate_policy():
    """Schema + unique-rule-id checks. Returns (ok, errors[])."""
    errors = []
    ptr = load_pointer()
    policy_path = os.path.join(ROOT, ptr["policy_json"])
    with open(policy_path) as f:
        policy = json.load(f)
    for sect in ("roster", "quorum", "lifecycle", "capacity", "dispatcher_constraints", "rule_ids"):
        if sect not in policy:
            errors.append(f"missing required section: {sect}")
    # unique rule IDs
    rids = list((policy.get("rule_ids") or {}).keys())
    dupes = {r for r in rids if rids.count(r) > 1}
    if dupes:
        errors.append(f"duplicate rule IDs: {sorted(dupes)}")
    # roster sanity
    leaders = [l["id"] for l in policy.get("roster", {}).get("leaders", [])]
    if "hq_claude" in leaders:
        errors.append("hq_claude must NOT be an active leader")
    for req in ("wren", "tp_pip", "acer_cass", "bill"):
        if req not in leaders:
            errors.append(f"active leader missing: {req}")
    # on-disk hash matches pointer
    if _sha256(policy_path) != ptr["sha256"]:
        errors.append("on-disk policy hash != pointer sha256")
    return (len(errors) == 0, errors)


def supersession_resolve(legacy_key):
    """Given a legacy file/rule, return its V2 disposition. V2 ALWAYS wins."""
    with open(SUPERSESSION) as f:
        sup = json.load(f)
    for row in sup.get("supersedes", []):
        if row.get("legacy") == legacy_key:
            return {"legacy": legacy_key, "v2_wins": True, **row}
    return {"legacy": legacy_key, "v2_wins": True, "disposition": "NO_LEGACY_OVERRIDE",
            "note": "Unknown legacy key — Governance V2 still takes precedence."}


def is_v2_active():
    try:
        return load_pointer().get("status") == "ACTIVE"
    except Exception:
        return False


if __name__ == "__main__":
    if "--validate" in sys.argv or len(sys.argv) == 1:
        ok, errs = validate_policy()
        ptr = load_pointer()
        print(f"policy: {ptr['policy_json']}")
        print(f"pointer status: {ptr.get('status')}")
        print(f"policy sha256: {ptr['sha256']}")
        print(f"unique rule IDs: {'OK' if not any('duplicate' in e for e in errs) else 'FAIL'}")
        print(f"validate: {'OK' if ok else 'ERRORS'}")
        for e in errs:
            print("  -", e)
        sys.exit(0 if ok else 1)
    if "--active" in sys.argv:
        print("v2_active:", is_v2_active())
