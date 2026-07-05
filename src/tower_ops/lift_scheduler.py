"""Lift scheduler V5 — lifts carry workers along their actual routes."""

from datetime import datetime, timezone
from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


LIFT_DEFS = [
    {"lift_id": "LIFT-01", "name": "Low-Rise Main"},
    {"lift_id": "LIFT-02", "name": "Mid-Rise Main"},
    {"lift_id": "LIFT-03", "name": "High-Rise Main"},
    {"lift_id": "LIFT-04", "name": "Express Penthouse"},
    {"lift_id": "LIFT-05", "name": "Trading Express"},
    {"lift_id": "LIFT-06", "name": "Models Lift"},
    {"lift_id": "LIFT-07", "name": "Governance Lift"},
    {"lift_id": "LIFT-08", "name": "Service Lift"},
    {"lift_id": "LIFT-09", "name": "Kernel Liaison"},
]


def _floor_num(s):
    if s == "penthouse": return 55
    import re; m = re.match(r"^floor_(\d{1,2})$", s or ""); return int(m.group(1)) if m else 0


def live():
    from .live_worker_routes import live_routes
    routes = (live_routes().get("worker_routes") or [])
    # Group passengers by assigned lift
    by_lift = {L["lift_id"]: [] for L in LIFT_DEFS}
    for r in routes:
        if r.get("status") == "inside_lift" and r.get("lift_id") in by_lift:
            by_lift[r["lift_id"]].append({
                "worker_id":    r["worker_id"],
                "badge_id":     r["badge_id"],
                "short_code":   (r.get("badge_id") or "").split("-")[-2:] and "-".join((r.get("badge_id") or "").split("-")[-2:]),
                "display_name": r["display_name"],
                "from_floor":   r["current_floor"],
                "to_floor":     r["target_floor"],
            })
    out = []
    for L in LIFT_DEFS:
        passengers = by_lift.get(L["lift_id"], [])
        cur = max([_floor_num(p["from_floor"]) for p in passengers] + [0])
        tgt = max([_floor_num(p["to_floor"])   for p in passengers] + [cur])
        out.append({
            **L,
            "current_floor":    cur if cur else None,
            "target_floor":     tgt if tgt else None,
            "direction":        ("up" if tgt > cur else "down" if tgt < cur else "stationary"),
            "door_state":       ("opening" if passengers else "closed"),
            "occupancy":        len(passengers),
            "workers_inside":   passengers[:8],
            "next_stop":        tgt if tgt != cur else None,
            "status":           "moving" if passengers and tgt != cur else "idle",
        })
    return stamp_safe({"ok": True, "ts": _now(),
                        "phase": "QSB_TOWER_V1.5",
                        "lift_count": len(out),
                        "lifts": out})


def schedule():
    from .live_worker_routes import live_routes
    routes = (live_routes().get("worker_routes") or [])
    routes = [r for r in routes if r.get("lift_id")]
    return stamp_safe({"ok": True, "ts": _now(),
                        "passenger_count": len(routes),
                        "next_passengers": routes[:20]})


def occupancy():
    L = live()
    return stamp_safe({"ok": True, "ts": _now(),
                        "by_lift": {x["lift_id"]: x["occupancy"] for x in (L.get("lifts") or [])}})


def dispatch(payload=None):
    # Read-only scheduler — there's no autonomous dispatch.
    return stamp_safe({"ok": True, "ts": _now(),
                        "policy": "READ_SIDE_SCHEDULER_ONLY — no autonomous dispatch",
                        "dispatch_executed": False,
                        "execution_allowed": False})
