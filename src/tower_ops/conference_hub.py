"""V2.0 Conference Hub — boardroom + 9 conference rooms hosted on Floor 51
(Executive Council Department, repurposed for inter-floor meetings)."""

from datetime import datetime, timezone
from pathlib import Path
import json, uuid

from .safety_contract import stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
ROOMS_PATH = ROOT / "state/tower_ops/conference_rooms.json"
MEETINGS_PATH = ROOT / "state/tower_ops/meetings.json"
MINUTES_PATH = ROOT / "state/tower_ops/meeting_minutes.json"
LOG_PATH = ROOT / "logs/tower_ops/conference_hub.jsonl"

CONFERENCE_FLOOR_ID = "floor_51"
CONFERENCE_FLOOR_NUMBER = 51
CONFERENCE_FLOOR_NAME = "Conference Hub & Executive Council"

ROOMS = [
    "Main Boardroom",
    "Trading Strategy Conference Room",
    "Risk Accounts Approval Room",
    "OpenClaw Practice Review Room",
    "Research Briefing Room",
    "Training Review Room",
    "Kernel Liaison Room",
    "Colonel Observation Gallery",
    "Emergency War Room",
]

MEETING_TYPES = [
    "daily_tower_standup",
    "trading_practice_review",
    "risk_accounts_approval",
    "worker_training_review",
    "openclaw_practice_review",
    "dashboard_quality_review",
    "incident_review",
    "kernel_briefing",
    "colonel_briefing",
]


def _now(): return datetime.now(timezone.utc).isoformat()


def _ensure():
    for p in (ROOMS_PATH, MEETINGS_PATH, MINUTES_PATH, LOG_PATH):
        p.parent.mkdir(parents=True, exist_ok=True)
    if not ROOMS_PATH.exists():
        ROOMS_PATH.write_text(json.dumps({
            "floor_id": CONFERENCE_FLOOR_ID, "floor_number": CONFERENCE_FLOOR_NUMBER,
            "floor_name": CONFERENCE_FLOOR_NAME,
            "rooms": [{"name": r, "occupants": [], "status": "ready"} for r in ROOMS],
            "ts": _now(),
        }, indent=2))
    if not MEETINGS_PATH.exists():
        MEETINGS_PATH.write_text(json.dumps({"meetings": []}, indent=2))
    if not MINUTES_PATH.exists():
        MINUTES_PATH.write_text(json.dumps({"minutes": []}, indent=2))


def _log(rec):
    _ensure()
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**rec, "ts": _now()}) + "\n")


def _load(p, fallback):
    if p.exists():
        try: return json.loads(p.read_text())
        except Exception: pass
    return fallback


def status():
    _ensure()
    rooms = _load(ROOMS_PATH, {"rooms": []}).get("rooms") or []
    meetings = _load(MEETINGS_PATH, {"meetings": []}).get("meetings") or []
    active = [m for m in meetings if m.get("status") == "active"]
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "CONFERENCE_HUB_STATUS",
        "floor_id": CONFERENCE_FLOOR_ID,
        "floor_number": CONFERENCE_FLOOR_NUMBER,
        "floor_name": CONFERENCE_FLOOR_NAME,
        "room_count": len(rooms),
        "rooms": rooms,
        "meeting_types": MEETING_TYPES,
        "meetings_total": len(meetings),
        "meetings_active": len(active),
        "execution_allowed": False,
    })


def meetings():
    return stamp_safe({"ok": True, "ts": _now(),
                        "meetings": _load(MEETINGS_PATH, {"meetings": []}).get("meetings") or [],
                        "execution_allowed": False})


def live():
    _ensure()
    meetings_data = _load(MEETINGS_PATH, {"meetings": []}).get("meetings") or []
    active = [m for m in meetings_data if m.get("status") == "active"]
    rooms = _load(ROOMS_PATH, {"rooms": []}).get("rooms") or []
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "CONFERENCE_HUB_LIVE",
        "active_meetings": active,
        "active_meeting_count": len(active),
        "rooms": rooms,
        "execution_allowed": False,
    })


def start_meeting(payload):
    _ensure()
    payload = payload or {}
    mtype = (payload.get("meeting_type") or "daily_tower_standup").strip()
    if mtype not in MEETING_TYPES:
        return {"ok": False, "error": "unknown_meeting_type", "meeting_type": mtype}
    room = payload.get("room") or ROOMS[0]
    if room not in ROOMS:
        return {"ok": False, "error": "unknown_room", "room": room}
    agenda = payload.get("agenda") or [f"Standup for {mtype}"]
    attendees = payload.get("attendees") or []
    mid = "MTG-" + uuid.uuid4().hex[:10].upper()
    rec = {
        "meeting_id": mid,
        "meeting_type": mtype,
        "room": room,
        "agenda": agenda,
        "attendees": attendees,
        "status": "active",
        "started_ts": _now(),
        "ended_ts": None,
        "speaker": None,
        "decisions_pending": [],
    }
    data = _load(MEETINGS_PATH, {"meetings": []})
    data["meetings"].append(rec)
    MEETINGS_PATH.write_text(json.dumps(data, indent=2))
    _log({"event": "start_meeting", "meeting_id": mid, "type": mtype, "room": room})
    return stamp_safe({"ok": True, "ts": _now(),
                        "meeting_id": mid, "meeting": rec,
                        "execution_allowed": False})


def add_worker(payload):
    payload = payload or {}
    mid = payload.get("meeting_id"); wid = payload.get("worker_id")
    if not mid or not wid:
        return {"ok": False, "error": "meeting_id_and_worker_id_required"}
    data = _load(MEETINGS_PATH, {"meetings": []})
    found = False
    for m in data["meetings"]:
        if m.get("meeting_id") == mid:
            attendees = m.setdefault("attendees", [])
            if wid not in attendees: attendees.append(wid)
            found = True; break
    if not found:
        return {"ok": False, "error": "meeting_not_found", "meeting_id": mid}
    MEETINGS_PATH.write_text(json.dumps(data, indent=2))
    _log({"event": "add_worker", "meeting_id": mid, "worker_id": wid})
    return stamp_safe({"ok": True, "ts": _now(),
                        "meeting_id": mid, "added_worker_id": wid,
                        "execution_allowed": False})


def end_meeting(payload):
    payload = payload or {}
    mid = payload.get("meeting_id")
    if not mid: return {"ok": False, "error": "meeting_id_required"}
    data = _load(MEETINGS_PATH, {"meetings": []})
    found = False
    for m in data["meetings"]:
        if m.get("meeting_id") == mid:
            m["status"] = "ended"; m["ended_ts"] = _now()
            found = True; break
    if not found:
        return {"ok": False, "error": "meeting_not_found", "meeting_id": mid}
    MEETINGS_PATH.write_text(json.dumps(data, indent=2))
    _log({"event": "end_meeting", "meeting_id": mid})
    return stamp_safe({"ok": True, "ts": _now(), "meeting_id": mid,
                        "execution_allowed": False})


def record_minutes(payload):
    payload = payload or {}
    mid = payload.get("meeting_id")
    text = payload.get("text") or ""
    if not mid or not text:
        return {"ok": False, "error": "meeting_id_and_text_required"}
    data = _load(MINUTES_PATH, {"minutes": []})
    rec = {"meeting_id": mid, "ts": _now(), "text": text[:4000]}
    data["minutes"].append(rec)
    MINUTES_PATH.write_text(json.dumps(data, indent=2))
    _log({"event": "record_minutes", "meeting_id": mid, "length": len(text)})
    return stamp_safe({"ok": True, "ts": _now(), "minute": rec,
                        "execution_allowed": False})


def send_floor_to_conference(payload):
    """Floor sends representatives to a meeting."""
    payload = payload or {}
    mid = payload.get("meeting_id")
    floor = payload.get("floor")
    if not mid or floor is None:
        return {"ok": False, "error": "meeting_id_and_floor_required"}
    try:
        from .worker_directory import by_floor
        floor_id = floor if str(floor).startswith("floor_") else f"floor_{int(floor):02d}"
        workers = by_floor(floor_id).get("directory") or []
        added = []
        for w in workers[:3]:  # send first three as representatives
            r = add_worker({"meeting_id": mid, "worker_id": w.get("worker_id")})
            if r.get("ok"): added.append(w.get("worker_id"))
        return stamp_safe({"ok": True, "ts": _now(), "meeting_id": mid,
                            "floor": floor_id, "representatives": added,
                            "execution_allowed": False})
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
