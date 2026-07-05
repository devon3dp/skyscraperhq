"""Worker narration — produces the spoken script when the operator clicks a worker."""

from datetime import datetime, timezone
from pathlib import Path
import json
import re

from .safety_contract import stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SELECTED_PATH = ROOT / "state/tower_ops/worker_selected.json"


def _now(): return datetime.now(timezone.utc).isoformat()


def _ensure(): SELECTED_PATH.parent.mkdir(parents=True, exist_ok=True)


def _floor_name_for(floor_id):
    if not floor_id: return "an unspecified floor"
    try:
        from .org_schema import FLOOR_TO_DEPARTMENT
        return FLOOR_TO_DEPARTMENT.get(floor_id, floor_id.replace("_", " ").title())
    except Exception:
        return floor_id.replace("_", " ").title()


def _find_worker(identifier):
    if not identifier:
        return None
    from .worker_directory import directory
    d = directory().get("directory") or []
    for w in d:
        if w.get("worker_id") == identifier or w.get("badge_id") == identifier:
            return w
    # case-insensitive fallback for display_name
    low = identifier.lower()
    for w in d:
        if (w.get("display_name") or "").lower() == low:
            return w
    return None


def _route_text(w):
    rt = w.get("route_target")
    rr = w.get("route_reason")
    if rt and rr:
        return f"I am moving to {rt.replace('_',' ')} to {rr}."
    if rt:
        return f"I am moving to {rt.replace('_',' ')}."
    if w.get("current_room"):
        return f"I am currently at {w['current_room'].replace('_',' ')}."
    return "I am at my home desk."


def _join(items):
    items = [i for i in (items or []) if i]
    if not items: return "nothing"
    if len(items) == 1: return items[0]
    return ", ".join(items[:-1]) + ", and " + items[-1]


def _allowed_summary(w):
    actions = w.get("allowed_actions") or []
    return _join(actions[:4]) if actions else "read tower telemetry"


def _forbidden_summary(w):
    forbidden = w.get("forbidden_actions") or []
    return _join(forbidden[:4]) if forbidden else "execute live orders or bypass guards"


def narration_for(identifier):
    w = _find_worker(identifier)
    if not w:
        return {"ok": False, "error": "worker_not_found", "identifier": identifier}
    badge = w.get("badge_id") or "unknown badge"
    name  = w.get("display_name") or w.get("worker_id") or "this worker"
    dept  = w.get("department")  or "no department"
    floor_id = w.get("current_floor") or w.get("floor_id") or w.get("home_floor")
    floor_name = _floor_name_for(floor_id)
    task  = w.get("current_task") or "monitoring the floor"
    manager = w.get("manager_id") or "the floor manager"
    overseer = w.get("overseer_id") or "the tower overseer"
    access  = _allowed_summary(w)
    forbidden = _forbidden_summary(w)
    route_text = _route_text(w)
    spoken = (
        f"I am {name}, badge {badge}. "
        f"I am assigned to {floor_name}. "
        f"My department is {dept}. "
        f"My current task is {task}. "
        f"I report to {manager} and {overseer}. "
        f"I am allowed to {access}. "
        f"I cannot {forbidden}. "
        f"{route_text}"
    )
    return stamp_safe({
        "ok": True, "ts": _now(),
        "worker_id": w.get("worker_id"),
        "badge_id":  badge,
        "display_name": name,
        "spoken_text": spoken,
        "voice_summary": {
            "job":          dept,
            "current_task": task,
            "route":        route_text,
            "access":       access,
            "forbidden":    forbidden,
            "home_floor":   floor_id,
            "manager":      manager,
            "overseer":     overseer,
        },
        "method": "browser_web_speech_synthesis",
        "execution_allowed": False,
    })


def speak(payload):
    """Browser is responsible for SpeechSynthesis. This endpoint returns the script."""
    payload = payload or {}
    return narration_for(payload.get("id") or payload.get("worker_id") or payload.get("badge_id"))


def select(payload):
    _ensure()
    payload = payload or {}
    wid = payload.get("id") or payload.get("worker_id") or payload.get("badge_id")
    if not wid:
        return {"ok": False, "error": "id_required"}
    w = _find_worker(wid)
    if not w:
        return {"ok": False, "error": "worker_not_found", "identifier": wid}
    rec = {"ts": _now(),
           "worker_id": w.get("worker_id"),
           "badge_id":  w.get("badge_id"),
           "display_name": w.get("display_name")}
    SELECTED_PATH.write_text(json.dumps(rec, indent=2))
    return stamp_safe({"ok": True, **rec, "execution_allowed": False})


def selected():
    _ensure()
    if SELECTED_PATH.exists():
        try:
            return stamp_safe({"ok": True, **json.loads(SELECTED_PATH.read_text()),
                                "execution_allowed": False})
        except Exception:
            pass
    return stamp_safe({"ok": True, "worker_id": None, "execution_allowed": False})
