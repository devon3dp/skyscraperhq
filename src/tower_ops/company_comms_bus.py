"""V2.0 company comms bus — single message stream for inter-floor comms.

Builds on top of V1.5 floor_comms; surfaces a company-wide view, broadcast
endpoint, and conference summary publisher.
"""

from datetime import datetime, timezone
from pathlib import Path
import json, uuid

from .safety_contract import stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
COMPANY_PATH = ROOT / "state/tower_ops/company_comms.json"
LOG_PATH = ROOT / "logs/tower_ops/company_comms.jsonl"


MESSAGE_TYPES = [
    "worker_report", "manager_report", "zone_report",
    "approval_request", "approval_granted", "approval_denied",
    "practice_order_request", "practice_order_result",
    "risk_alert", "accounts_report", "maintenance_alert",
    "security_alert", "IT_status", "training_update",
    "research_note", "conference_minutes", "colonel_directive",
    "kernel_summary",
]


def _now(): return datetime.now(timezone.utc).isoformat()


def _ensure():
    COMPANY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not COMPANY_PATH.exists():
        COMPANY_PATH.write_text(json.dumps({"messages": []}, indent=2))


def _load():
    _ensure()
    try: return json.loads(COMPANY_PATH.read_text())
    except Exception: return {"messages": []}


def _save(d):
    COMPANY_PATH.write_text(json.dumps(d, indent=2))


def _log(rec):
    _ensure()
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**rec, "ts": _now()}) + "\n")


def status():
    d = _load()
    msgs = d.get("messages") or []
    return stamp_safe({"ok": True, "ts": _now(),
                        "label": "COMPANY_COMMS_BUS_STATUS",
                        "message_types": MESSAGE_TYPES,
                        "message_count": len(msgs),
                        "active_routes": len({m.get("route") for m in msgs}),
                        "execution_allowed": False})


def company():
    d = _load()
    return stamp_safe({"ok": True, "ts": _now(),
                        "label": "COMPANY_COMMS_BUS",
                        "messages": (d.get("messages") or [])[-100:],
                        "message_count": len(d.get("messages") or []),
                        "active_routes": len({m.get("route") for m in (d.get("messages") or [])}),
                        "message_types": MESSAGE_TYPES,
                        "execution_allowed": False})


def floor_messages(payload_or_floor):
    floor = payload_or_floor
    if isinstance(floor, dict):
        floor = floor.get("floor")
    if floor is None:
        return {"ok": False, "error": "floor_required"}
    fid = floor if str(floor).startswith("floor_") else f"floor_{int(floor):02d}"
    d = _load()
    rows = [m for m in (d.get("messages") or [])
            if m.get("source") == fid or m.get("target") == fid]
    return stamp_safe({"ok": True, "ts": _now(),
                        "floor": fid, "messages": rows[-50:],
                        "execution_allowed": False})


def routes():
    d = _load()
    pairs = sorted({(m.get("source"), m.get("target"))
                     for m in (d.get("messages") or []) if m.get("source") and m.get("target")})
    return stamp_safe({"ok": True, "ts": _now(),
                        "label": "COMPANY_COMMS_ROUTES",
                        "route_count": len(pairs),
                        "routes": [{"source": s, "target": t} for s, t in pairs],
                        "execution_allowed": False})


def send(payload):
    payload = payload or {}
    mtype = payload.get("message_type") or payload.get("type")
    if mtype not in MESSAGE_TYPES:
        return {"ok": False, "error": "unknown_message_type", "message_type": mtype}
    src = payload.get("source"); tgt = payload.get("target")
    body = payload.get("body") or payload.get("text") or ""
    if not src or not tgt:
        return {"ok": False, "error": "source_and_target_required"}
    mid = "MSG-" + uuid.uuid4().hex[:10].upper()
    msg = {"id": mid, "ts": _now(),
           "type": mtype, "source": src, "target": tgt,
           "route": f"{src}->{tgt}",
           "body": body[:2000], "sealed": True}
    d = _load(); d["messages"].append(msg); _save(d)
    _log({"event": "send", "id": mid, "type": mtype, "route": msg["route"]})
    return stamp_safe({"ok": True, "ts": _now(), "message": msg,
                        "execution_allowed": False})


def broadcast(payload):
    payload = payload or {}
    mtype = payload.get("message_type") or "colonel_directive"
    if mtype not in MESSAGE_TYPES:
        return {"ok": False, "error": "unknown_message_type", "message_type": mtype}
    src = payload.get("source") or "tower_command"
    body = payload.get("body") or ""
    d = _load()
    msgs = []
    # Broadcast to floors 1-53
    for n in range(1, 54):
        tgt = f"floor_{n:02d}"
        mid = "MSG-" + uuid.uuid4().hex[:10].upper()
        msg = {"id": mid, "ts": _now(),
               "type": mtype, "source": src, "target": tgt,
               "route": f"{src}->{tgt}", "body": body[:2000], "sealed": True,
               "broadcast": True}
        d["messages"].append(msg); msgs.append(msg)
    _save(d)
    _log({"event": "broadcast", "type": mtype, "fan_out": len(msgs)})
    return stamp_safe({"ok": True, "ts": _now(),
                        "broadcast_count": len(msgs),
                        "type": mtype, "execution_allowed": False})


def conference_summary(payload):
    """Publishes a conference summary message on the bus, addressed to kernel."""
    payload = payload or {}
    mid = payload.get("meeting_id") or "unknown"
    text = payload.get("text") or "conference summary"
    return send({"message_type": "conference_minutes",
                  "source": "floor_51",
                  "target": "penthouse",
                  "body": f"[{mid}] {text}"})
