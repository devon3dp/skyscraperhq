"""Worker Directory V1 — single source of truth for the cockpit.

Returns every worker with badge + access card already attached.
Replaces the older floors.json `sim_worker_floor_XX` worker list as the
primary source for the dashboard.
"""

from datetime import datetime, timezone

from .safety_contract import stamp_safe
from .worker_registry  import workers as worker_list
from .identity_badges  import assign_badges
from .access_control   import access_card


def _now(): return datetime.now(timezone.utc).isoformat()


def directory():
    ws = (worker_list().get("workers") or [])
    ws = assign_badges(ws)   # ensures every worker has badge_id + short_code + access_level
    out = []
    for w in ws:
        card = access_card(w)
        out.append({
            "worker_id": w.get("id") or w.get("worker_id"),
            "badge_id": w.get("badge_id"),
            "display_name": w.get("display_name"),
            "short_code": w.get("short_code"),
            "department": w.get("department") or w.get("team"),
            "team":       w.get("team"),
            "floor_id":   w.get("floor_assignment"),
            "floor_name": w.get("floor_name"),
            "home_floor": w.get("floor_assignment"),
            "current_floor": w.get("current_floor") or w.get("floor_assignment"),
            "current_room":  w.get("current_room") or w.get("desk_assignment"),
            "current_lift_id": w.get("current_lift_id"),
            "role":  w.get("role"),
            "rank":  w.get("rank") or "worker",
            "employment_status": w.get("employment_status") or "active",
            "recruitment_stage": w.get("recruitment_stage") or w.get("stage"),
            "manager_id":      w.get("manager_id"),
            "zone_manager_id": w.get("zone_manager_id"),
            "overseer_id":     w.get("overseer_id"),
            "access_level": card["access_level"],
            "access_zones": card["access_zones"],
            "allowed_floors": card["allowed_floors"],
            "denied_floors":  card["denied_floors"],
            "allowed_rooms":  card["allowed_rooms"],
            "allowed_actions":   card["allowed_actions"],
            "forbidden_actions": card["forbidden_actions"],
            "model_access":      card["model_access"],
            "data_access":       card["data_access"],
            "trading_data_access": card["trading_data_access"],
            "openclaw_access":   card["openclaw_access"],
            "web_access":        card["web_access"],
            "audio_access":      card["audio_access"],
            "kernel_access":     card["kernel_access"],
            "airllm_access":     card["airllm_access"],
            "quantum_access":    card["quantum_access"],
            "accounting_access": card["accounting_access"],
            "heartbeat_ts":  w.get("heartbeat_ts"),
            "last_seen_ts":  w.get("heartbeat_ts"),
            "current_task":  w.get("current_task"),
            "route_target":  w.get("route_target"),
            "route_reason":  w.get("route_reason"),
            "last_packet":   w.get("last_packet"),
            "audit_count":   w.get("audit_count"),
            "openclaw_ready": w.get("openclaw_ready"),
            "openclaw_execution_enabled": False,
            "provider_access_enabled":    False,
            "autonomous_dispatch_enabled":False,
            "trading_execution_enabled":  False,
        })
    return stamp_safe({"ok": True, "ts": _now(),
                        "directory_count": len(out),
                        "directory": out})


def by_floor(floor_id):
    # Normalize accepted forms: "25" / "F25" / "f25" / "floor_25" / "Penthouse"
    if floor_id:
        fid = str(floor_id).strip()
        if fid.lower() == "penthouse":
            floor_id = "penthouse"
        elif fid.lower().startswith("floor_"):
            floor_id = fid.lower()
        elif fid.lower().startswith("f") and fid[1:].isdigit():
            n = int(fid[1:]);  floor_id = "penthouse" if n == 55 else f"floor_{n:02d}"
        elif fid.isdigit():
            n = int(fid);  floor_id = "penthouse" if n == 55 else f"floor_{n:02d}"
    d = directory()
    return stamp_safe({"ok": True, "ts": _now(),
                        "floor_id": floor_id,
                        "directory": [w for w in d["directory"] if w["floor_id"] == floor_id]})


def by_badge(badge_id):
    d = directory()
    match = [w for w in d["directory"] if w["badge_id"] == badge_id]
    if not match: return {"ok": False, "error": "badge_not_found", "badge_id": badge_id}
    return stamp_safe({"ok": True, "ts": _now(), "worker": match[0]})


def update_location(payload):
    """Local-only update of current_floor/current_room/current_lift_id.
    Does NOT execute movement — just records position. Used by tower_tick.
    """
    payload = payload or {}
    wid = payload.get("worker_id");
    if not wid: return {"ok": False, "error": "worker_id_required"}
    # Persist via the worker_registry tick mechanism
    from .worker_registry import assign as _rec_assign
    # We use assign() to update non-execution fields; never touches locks.
    floor = payload.get("current_floor")
    desk  = payload.get("current_room")
    return _rec_assign({"worker_id": wid,
                         "floor_assignment": floor if floor else None,
                         "desk_assignment":  desk  if desk  else None})
