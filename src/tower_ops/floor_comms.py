"""Floor Comms / Message Bus V1."""

from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import uuid

from .safety_contract import LOCKED_FALSE, stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_PATH = ROOT / "state/tower_ops/floor_messages.json"
LOG_PATH   = ROOT / "logs/tower_ops/floor_comms.jsonl"

_LOCK = threading.Lock()
MSG_TYPES = ("worker_report", "floor_manager_approval", "zone_manager_report",
              "risk_request", "accounts_request", "training_request",
              "maintenance_request", "security_alert", "trade_proposal",
              "practice_order_request", "practice_order_result",
              "kernel_message", "colonel_observation", "announcement")


def _now(): return datetime.now(timezone.utc).isoformat()


def _read():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        return {"messages": [], "ts": _now(), **LOCKED_FALSE}
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception: return {"messages": [], "ts": _now()}


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
    by_type = {}
    for m in st.get("messages") or []:
        by_type[m.get("type", "unknown")] = by_type.get(m.get("type", "unknown"), 0) + 1
    return stamp_safe({"ok": True, "ts": _now(),
                        "phase": "QSB_TOWER_V1.5",
                        "bus": "QSB Floor Comms Bus V1",
                        "message_types": list(MSG_TYPES),
                        "total_messages": len(st.get("messages") or []),
                        "by_type": by_type})


def messages(limit=100):
    st = _read()
    return stamp_safe({"ok": True, "ts": _now(),
                        "messages": (st.get("messages") or [])[-limit:],
                        "total": len(st.get("messages") or [])})


def floor_messages(floor_id, limit=30):
    st = _read()
    rows = [m for m in (st.get("messages") or []) if m.get("from_floor") == floor_id or m.get("to_floor") == floor_id]
    return stamp_safe({"ok": True, "ts": _now(),
                        "floor_id": floor_id,
                        "messages": rows[-limit:]})


def send(payload):
    payload = payload or {}
    mtype = payload.get("type") or "announcement"
    if mtype not in MSG_TYPES:
        return {"ok": False, "error": "invalid_type", "valid_types": list(MSG_TYPES)}
    msg = {
        "msg_id": "msg_" + uuid.uuid4().hex[:10],
        "ts": _now(),
        "type": mtype,
        "from_floor": payload.get("from_floor"),
        "to_floor":   payload.get("to_floor"),
        "from_worker_id": payload.get("from_worker_id"),
        "to_worker_id":   payload.get("to_worker_id"),
        "subject": (payload.get("subject") or "").strip()[:160],
        "body":    (payload.get("body") or "").strip()[:2000],
        "priority":payload.get("priority") or "normal",
        "execution_allowed": False,
    }
    with _LOCK:
        st = _read()
        st.setdefault("messages", []).append(msg)
        st["messages"] = st["messages"][-2000:]
        _write(st)
    _append_log({"event": "send", **{k: msg[k] for k in ("msg_id", "type", "from_floor", "to_floor")}})
    return stamp_safe({"ok": True, "ts": _now(), "message": msg})


def manager_approve(payload):
    payload = payload or {}
    return send({
        "type": "floor_manager_approval",
        "from_floor": payload.get("from_floor"),
        "to_floor":   payload.get("to_floor"),
        "subject":    f"Manager approval: {payload.get('subject') or ''}",
        "body":       f"Manager {payload.get('manager_id') or '—'} approved.",
        "priority":   "high",
    })


def colonel_broadcast(payload):
    payload = payload or {}
    return send({
        "type": "colonel_observation",
        "from_floor": "penthouse",
        "to_floor":   payload.get("to_floor") or "all",
        "subject":    payload.get("subject") or "Colonel broadcast",
        "body":       payload.get("body") or "Colonel observation broadcast.",
        "priority":   "high",
    })
