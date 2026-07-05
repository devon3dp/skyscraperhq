"""Correction report formatter — turns the loop state into the panel data."""

from datetime import datetime, timezone
from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


def panel_state():
    from . import correction_loop as CL
    from .not_working import report as _nw
    from .tower_audit import latest as _al
    latest = CL.latest()
    nw = _nw()
    al = _al()
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "CORRECTION_LOOP_PANEL_STATE",
        "current_audit_score": (al or {}).get("score"),
        "critical_issues":     [it for it in (nw.get("items") or [])
                                 if (it.get("severity") or "").upper() == "FAIL"],
        "warnings":            [it for it in (nw.get("items") or [])
                                 if (it.get("severity") or "").upper() == "WARN"],
        "ui_gaps":             nw.get("items") or [],
        "flow_gaps":           [],
        "orphaned_files":      [],
        "unwired_modules":     [],
        "last_actions":        (latest or {}).get("actions_applied") or [],
        "next_actions":        ((latest or {}).get("safe_to_apply_inventory") or {}).get("safe_to_apply_automatically", []),
        "needs_ross_decision": ((latest or {}).get("safe_to_apply_inventory") or {}).get("needs_ross_decision", []),
        "execution_allowed":   False,
    })
