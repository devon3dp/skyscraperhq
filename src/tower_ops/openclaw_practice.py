"""OpenClaw Practice Mode V1.

OpenClaw may generate PRACTICE proposals. It cannot bypass the
oanda_practice_trading guards or set any execution flag. Every
proposal is queued for manual confirmation; nothing auto-executes.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import uuid

from .safety_contract import stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_PATH = ROOT / "state/tower_ops/openclaw_practice_proposals.json"
LOG_PATH   = ROOT / "logs/tower_ops/openclaw_practice_events.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


SAFETY_STAMP = {
    "execution_mode":                          "PRACTICE_ONLY",
    "openclaw_practice_mode_enabled":          True,
    "openclaw_real_execution_enabled":         False,
    "openclaw_execution_enabled":              False,
    "openclaw_real_tool_execution_enabled":    False,
    "autonomous_dispatch_enabled":             False,
    "live_dispatch_enabled":                   False,
    "live_trading_enabled":                    False,
    "real_order_execution_enabled":            False,
    "binance_order_execution_enabled":         False,
    "stock_order_execution_enabled":           False,
    "direct_provider_access":                  False,
    "external_provider_execution_enabled":     False,
    "fake_data":                               False,
}


def _read():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        return {"ts": _now(), "proposals": [], **SAFETY_STAMP}
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception: return {"ts": _now(), "proposals": [], **SAFETY_STAMP}


def _write(d):
    d["ts"] = _now(); d.update(SAFETY_STAMP)
    STATE_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")


def _append_log(rec):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", _now()); rec.update(SAFETY_STAMP)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def status():
    st = _read()
    by_status = {}
    for p in st.get("proposals") or []:
        by_status[p.get("status", "new")] = by_status.get(p.get("status", "new"), 0) + 1
    return stamp_safe({
        "ok": True, "ts": _now(),
        "phase": "QSB_TOWER_OPERATIONS_V4",
        "lane": "OpenClaw Practice Lane",
        "policy": "Proposals only. Manual confirmation required for OANDA practice routing. No real execution.",
        "proposal_count": len(st.get("proposals") or []),
        "by_status": by_status,
        "watching": ["pricing", "open_trades", "account_telemetry"],
        "allowed_routes": ["risk_review", "accounts_review", "floor_41_manager", "manual_confirm"],
        "forbidden": ["live_orders", "bypass_manual_confirm", "bypass_risk_guard",
                       "real_execution", "live_trading", "binance", "stocks"],
        **SAFETY_STAMP,
    })


def proposals():
    st = _read()
    return stamp_safe({"ok": True, "ts": _now(),
                        "proposals": st.get("proposals") or [],
                        **SAFETY_STAMP})


def practice_stream():
    """Live stream — pricing + recent proposals + safety footer."""
    from .oanda_practice_trading import pricing, open_trades, account
    return stamp_safe({
        "ok": True, "ts": _now(),
        "lane": "openclaw_practice_stream",
        "live_pricing": pricing(),
        "current_open_trades": (open_trades().get("trades") or [])[:5],
        "current_account":     account(),
        "recent_proposals":    (proposals().get("proposals") or [])[-10:],
        **SAFETY_STAMP,
    })


def create_practice_proposal(payload):
    payload = payload or {}
    inst = (payload.get("instrument") or "EUR_USD").upper()
    side = (payload.get("side") or "buy").lower()
    units = int(payload.get("units") or 100)
    rationale = (payload.get("rationale") or "OpenClaw observed signal").strip()
    new = {
        "proposal_id": "ocp_" + uuid.uuid4().hex[:10],
        "ts": _now(),
        "instrument": inst, "side": side, "units": units,
        "rationale": rationale,
        "status": "new",
        "route_history": ["created"],
        "manual_confirm_required": True,
        "mode": "PRACTICE_ONLY",
        "execution_allowed": False,
    }
    with _LOCK:
        st = _read()
        st.setdefault("proposals", []).append(new); _write(st)
        _append_log({"event": "create_practice_proposal", "proposal_id": new["proposal_id"]})
    return stamp_safe({"ok": True, "proposal": new, **SAFETY_STAMP})


def submit_to_oanda_practice_preview(payload):
    """Forward a proposal to /api/trading/oanda/practice_order_preview.
    Returns the preview result. Does NOT place an order. Manual confirm still required.
    """
    payload = payload or {}; pid = payload.get("proposal_id")
    with _LOCK:
        st = _read()
        proposal = next((p for p in (st.get("proposals") or []) if p.get("proposal_id") == pid), None)
        if not proposal: return {"ok": False, "error": "proposal_not_found"}
        proposal["status"] = "submitted_to_preview"
        proposal["route_history"].append("submitted_to_preview")
        _write(st)
    from .oanda_practice_trading import practice_order_preview
    prev = practice_order_preview({
        "mode": "PRACTICE_ONLY",
        "instrument": proposal["instrument"],
        "units":      proposal["units"],
        "side":       proposal["side"],
        "confirm_practice_order": False,
    })
    _append_log({"event": "submit_to_oanda_practice_preview",
                  "proposal_id": pid, "preview_ok": prev.get("ok")})
    return stamp_safe({"ok": True, "proposal_id": pid,
                        "preview": prev, **SAFETY_STAMP})
