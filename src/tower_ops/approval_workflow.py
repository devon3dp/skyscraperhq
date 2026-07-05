"""Manager / Accounts / Risk approval workflow for practice orders."""

from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import uuid

from .safety_contract import LOCKED_FALSE, stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_PATH = ROOT / "state/tower_ops/approvals.json"
LOG_PATH   = ROOT / "logs/tower_ops/approvals.jsonl"
_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


def _read():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        return {"approvals": [], "ts": _now(), **LOCKED_FALSE}
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception: return {"approvals": [], "ts": _now()}


def _write(d):
    d["ts"] = _now(); d.update(LOCKED_FALSE)
    STATE_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")


def _append_log(rec):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", _now()); rec["execution_allowed"] = False
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def status():
    st = _read()
    rows = st.get("approvals") or []
    by_status = {}
    for a in rows:
        by_status[a.get("status", "pending")] = by_status.get(a.get("status", "pending"), 0) + 1
    return stamp_safe({"ok": True, "ts": _now(),
                        "phase": "QSB_TOWER_V1.5",
                        "total_approvals": len(rows),
                        "by_status": by_status,
                        "policy": "Every approval is advisory metadata. "
                                   "Real OANDA practice orders still require manual_confirm on the order endpoint."})


def pending():
    st = _read()
    rows = [a for a in (st.get("approvals") or []) if a.get("status") == "pending"]
    return stamp_safe({"ok": True, "ts": _now(),
                        "pending": rows[-50:], "count": len(rows)})


def history():
    st = _read()
    return stamp_safe({"ok": True, "ts": _now(),
                        "approvals": (st.get("approvals") or [])[-200:]})


def create(payload):
    payload = payload or {}
    new = {
        "approval_id": "ap_" + uuid.uuid4().hex[:10],
        "ts": _now(),
        "kind": payload.get("kind") or "trade_proposal",
        "subject": (payload.get("subject") or "").strip()[:160],
        "instrument": payload.get("instrument"),
        "units":      payload.get("units"),
        "side":       payload.get("side"),
        "from_worker_id": payload.get("from_worker_id"),
        "manager_approved":  False,
        "accounts_approved": False,
        "risk_approved":     False,
        "status": "pending",
        "execution_allowed": False,
    }
    with _LOCK:
        st = _read()
        st.setdefault("approvals", []).append(new); _write(st)
    _append_log({"event": "create", "approval_id": new["approval_id"]})
    return stamp_safe({"ok": True, "ts": _now(), "approval": new})


def _grant(payload, key, log_event):
    payload = payload or {}; aid = payload.get("approval_id")
    if not aid: return {"ok": False, "error": "approval_id_required"}
    with _LOCK:
        st = _read()
        for a in (st.get("approvals") or []):
            if a.get("approval_id") == aid:
                a[key] = True
                a["last_updated"] = _now()
                if a.get("manager_approved") and a.get("accounts_approved") and a.get("risk_approved"):
                    a["status"] = "approved"
                _write(st)
                _append_log({"event": log_event, "approval_id": aid})
                return stamp_safe({"ok": True, "approval": a})
    return {"ok": False, "error": "approval_not_found"}


def manager_approve(payload):  return _grant(payload, "manager_approved",  "manager_approve")
def accounts_approve(payload): return _grant(payload, "accounts_approved", "accounts_approve")
def risk_approve(payload):     return _grant(payload, "risk_approved",     "risk_approve")


def reject(payload):
    payload = payload or {}; aid = payload.get("approval_id")
    with _LOCK:
        st = _read()
        for a in (st.get("approvals") or []):
            if a.get("approval_id") == aid:
                a["status"] = "rejected"; a["last_updated"] = _now()
                _write(st); _append_log({"event": "reject", "approval_id": aid})
                return stamp_safe({"ok": True, "approval": a})
    return {"ok": False, "error": "approval_not_found"}
