"""Tower Ops Missing/Unbuilt Floors inventory."""

from datetime import datetime, timezone
from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


CHECKS = [
    # (department, floor_assigned, endpoint, ui)
    ("Accounts / Finance",       "floor_44", "/api/accounts/status", "Floor 44 console"),
    ("Quantum Operations",       "floor_45", "/api/quantum/status",  "Floor 45 console"),
    ("Training Academy",         "floor_08", None,                    "Floor 8 roster only"),
    ("Data / Memory",            "floor_02", None,                    "Floor 2 roster only"),
    ("Model Operations",         "floor_24", "/api/models/lanes",     "Floor 24 model router"),
    ("Legal / Compliance",       "floor_32", None,                    "Floor 32 roster only"),
    ("Lift / Logistics",         "floor_22", "/api/lifts/status",     "Floor 22 lift console"),
    ("QA / Testing",             None,        None,                    "not yet assigned"),
    ("Facilities",               None,        None,                    "not yet assigned (Maintenance covers ops)"),
    ("Emergency Control Room",   "floor_29", None,                    "Floor 29 roster only"),
    ("Reports Archive",          "floor_02", None,                    "Data/Memory archive desks"),
    ("Web Research Gatekeeping", "floor_03", None,                    "Research Floor desk"),
    ("OpenClaw Readiness",       "floor_38", "/api/recruitment/openclaw_review", "Recruitment Agency floor"),
]


def report():
    rows = []
    for dept, fid, ep, ui in CHECKS:
        rows.append({
            "department":            dept,
            "floor_assigned":        fid is not None,
            "floor_id":              fid,
            "workers_assigned":      bool(fid),
            "manager_assigned":      bool(fid),
            "overseer_assigned":     bool(fid),
            "accountant_assigned":   bool(fid),
            "endpoint_exists":       bool(ep),
            "endpoint":              ep,
            "ui_exists":             ui != "not yet assigned",
            "status":                "live" if (fid and ep) else ("staffed" if fid else "missing"),
            "next_action":           "live and reporting" if (fid and ep) else
                                      ("expose endpoint" if fid else "assign vacant floor + staff"),
        })
    return stamp_safe({"ok": True, "ts": _now(),
                        "phase": "QSB_TOWER_OPERATIONS_V2",
                        "departments": rows,
                        "total_departments": len(rows),
                        "fully_live_count": sum(1 for r in rows if r["status"] == "live"),
                        "staffed_only_count": sum(1 for r in rows if r["status"] == "staffed"),
                        "missing_count": sum(1 for r in rows if r["status"] == "missing")})
