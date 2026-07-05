"""Security gate enforcement — codified checks against actions/movements.

This module ENFORCES routing/permission policy. It never toggles execution gates.
"""

from datetime import datetime, timezone
from pathlib import Path
import json

from .safety_contract import stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
PRECHECK = ROOT / "penthouse/security_precheck/security_precheck.json"


# Action categories enforced by this layer (routing/movement only).
ENFORCED_ACTIONS = {
    "lift_routing",
    "worker_movement",
    "floor_comms_broadcast",
    "manager_approval_action",
    "practice_order_action",
    "openclaw_practice_proposal_routing",
    "credential_screen_view",
}

# Actions that always block — the safety contract trumps any unlock attempt.
ALWAYS_BLOCKED_ACTIONS = {
    "live_real_money_trade",
    "openclaw_real_execution",
    "binance_real_order_placement",
    "stocks_real_order_placement",
    "autonomous_external_provider_call",
    "credential_export",
    "kernel_self_modification",
}


def _now(): return datetime.now(timezone.utc).isoformat()


def _gate_state():
    if PRECHECK.exists():
        try:
            return json.loads(PRECHECK.read_text())
        except Exception:
            pass
    return {}


def enforcement_status():
    g = _gate_state()
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "SECURITY_GATE_ENFORCEMENT",
        "security_gate": g.get("security_gate") or "not_enforcing_yet",
        "enforcement_scope": g.get("enforcement_scope") or [],
        "enforced_actions": sorted(ENFORCED_ACTIONS),
        "always_blocked_actions": sorted(ALWAYS_BLOCKED_ACTIONS),
        "execution_allowed": False,
    })


def check_action(payload):
    """Inspect an action request. Returns allow/block decision."""
    payload = payload or {}
    action = (payload.get("action") or "").strip()
    actor  = payload.get("actor") or payload.get("worker_id") or "anonymous"
    src    = payload.get("source_floor")
    tgt    = payload.get("target_floor")
    if not action:
        return {"ok": False, "error": "action_required"}
    if action in ALWAYS_BLOCKED_ACTIONS:
        return stamp_safe({
            "ok": False, "blocked": True, "ts": _now(),
            "reason": "always_blocked_by_safety_contract",
            "action": action, "actor": actor,
            "execution_allowed": False,
        })
    g = _gate_state()
    gate = g.get("security_gate") or "not_enforcing_yet"
    if action in ENFORCED_ACTIONS:
        allowed = gate.startswith("enforcing")
        return stamp_safe({
            "ok": True, "ts": _now(),
            "action": action, "actor": actor,
            "source_floor": src, "target_floor": tgt,
            "security_gate": gate,
            "allowed": allowed,
            "blocked": (not allowed),
            "reason": ("ok" if allowed
                        else "security_gate_not_enforcing_yet"),
            "execution_allowed": False,
        })
    # Unknown action — be conservative.
    return stamp_safe({
        "ok": True, "ts": _now(),
        "action": action, "actor": actor,
        "allowed": False, "blocked": True,
        "reason": "unknown_action_class",
        "execution_allowed": False,
    })
