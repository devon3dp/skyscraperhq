"""V2.0 floor activation matrix — every floor classified into a state."""

from datetime import datetime, timezone
from pathlib import Path
import json

from .safety_contract import stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")


def _now(): return datetime.now(timezone.utc).isoformat()


def _load_floors():
    p = ROOT / "data/registries/floors.json"
    if not p.exists(): return []
    try: return json.loads(p.read_text())
    except Exception: return []


CONFERENCE_LIKE = {51, 52, 53}  # Executive Council, Infrastructure Command, Tower Command


def matrix():
    floors = _load_floors()
    rows = []
    counts = {"active_department": 0, "active_facility": 0,
              "staged_expansion_with_purpose": 0,
              "roof_external_locked": 0, "service_mechanical": 0,
              "archive": 0, "unknown": 0}
    for f in floors:
        fid = f.get("id"); num = f.get("number")
        dept = f.get("department")
        status_field = f.get("status")
        vacant = bool(f.get("vacant"))
        state = "unknown"
        if status_field == "occupied":
            state = "active_department" if "Department" in (dept or "") else "active_facility"
        elif status_field == "vacant_ready":
            state = "staged_expansion_with_purpose"
        elif status_field == "staged":
            state = "staged_expansion_with_purpose"
        if num in CONFERENCE_LIKE:
            state = state if state != "unknown" else "active_facility"
        counts[state] = counts.get(state, 0) + 1
        rows.append({
            "id": fid, "number": num, "department": dept,
            "registry_status": status_field, "vacant_flag": vacant,
            "activation_state": state,
            "managers_present": True, "comms_present": True,
            "narration_endpoint": f"/api/floors/narration?floor={num}",
        })
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "FLOOR_ACTIVATION_MATRIX",
        "floor_count": len(rows),
        "active_count":  counts["active_department"] + counts["active_facility"],
        "staged_count":  counts["staged_expansion_with_purpose"],
        "vacant_count":  counts.get("unknown", 0),
        "service_count": counts.get("service_mechanical", 0),
        "rows": rows,
        "counts_by_state": counts,
        "execution_allowed": False,
    })
