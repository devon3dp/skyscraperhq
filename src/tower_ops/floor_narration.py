"""Floor narration — spoken briefing for a selected floor."""

from datetime import datetime, timezone
from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


def _normalize(floor):
    if isinstance(floor, int): return f"floor_{floor:02d}"
    if isinstance(floor, str):
        if floor.startswith("floor_"): return floor
        try: return f"floor_{int(floor):02d}"
        except Exception: return floor
    return None


def _floor_display(floor_id):
    # 1) try the org schema first
    try:
        from .org_schema import FLOOR_TO_DEPARTMENT
        v = FLOOR_TO_DEPARTMENT.get(floor_id)
        if v and v != floor_id:
            return v
    except Exception:
        pass
    # 2) fall back to qsb_floor_name_map.json (the canonical source for both
    #    web dashboard and Godot cockpit).
    try:
        import json
        from pathlib import Path
        p = Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_floor_name_map.json")
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            nm = (d.get("name_map") or {}) if isinstance(d, dict) else {}
            # floor_id looks like 'floor_47' → extract '47'
            n = floor_id.replace("floor_", "")
            v = nm.get(n)
            if v:
                return v
    except Exception:
        pass
    return floor_id


def briefing_for(floor):
    fid = _normalize(floor)
    if not fid:
        return {"ok": False, "error": "floor_required"}
    try:
        n = int(fid.replace("floor_", ""))
    except Exception:
        n = None
    name = _floor_display(fid)
    workers_on_floor = []
    try:
        from .worker_directory import by_floor
        workers_on_floor = (by_floor(fid).get("directory") or [])
    except Exception:
        pass
    open_practice_trades = 0
    if fid == "floor_41":
        try:
            from .oanda_practice_trading import open_trades
            open_practice_trades = len(open_trades().get("trades") or [])
        except Exception:
            pass
    manager_id = "the floor manager"
    if workers_on_floor:
        for w in workers_on_floor:
            if w.get("manager_id"):
                manager_id = w["manager_id"]; break
    latest_event = "no recent event recorded"
    pending = "no pending action"
    try:
        from .approval_workflow import pending as _pend
        plist = _pend().get("pending") or []
        if plist:
            pending = f"{len(plist)} pending approval(s)"
    except Exception:
        pass
    spoken = (
        f"This is Floor {n if n else fid}, {name}. "
        f"There are {len(workers_on_floor)} active worker(s) on this floor. "
        f"{'There is ' + str(open_practice_trades) + ' open practice trade.' if open_practice_trades else 'No open practice trade.'} "
        f"Live trading is off. OpenClaw real execution is off. "
        f"The floor manager is {manager_id}. "
        f"The latest event is {latest_event}. "
        f"The next action waiting is {pending}."
    )
    return stamp_safe({
        "ok": True, "ts": _now(),
        "floor_id": fid, "floor_number": n,
        "floor_name": name,
        "active_worker_count": len(workers_on_floor),
        "open_practice_trades": open_practice_trades,
        "manager_id": manager_id,
        "spoken_text": spoken,
        "method": "browser_web_speech_synthesis",
        "execution_allowed": False,
    })


def speak(payload):
    payload = payload or {}
    return briefing_for(payload.get("floor"))
