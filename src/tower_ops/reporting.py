"""Floor / Zone / Tower report aggregator."""

from datetime import datetime, timezone

from .safety_contract import stamp_safe
from .org_schema      import FLOOR_TO_DEPARTMENT, ZONES, zone_for_floor
from .worker_registry import workers as worker_list
from .management_chain import all_managers, managers_for_floor


def _now(): return datetime.now(timezone.utc).isoformat()


def floor_reports():
    workers = worker_list().get("workers") or []
    out = []
    for n, (dep_name, dep_id) in FLOOR_TO_DEPARTMENT.items():
        floor_id = "floor_{:02d}".format(n) if n != 55 else "penthouse"
        floor_workers = [w for w in workers if w.get("floor_assignment") == floor_id]
        if not floor_workers and n not in (44, 45):
            # populated floors that ended up with no workers still get an empty report
            pass
        mgrs = managers_for_floor(n)
        zone_id, zone_name = zone_for_floor(n)
        active   = sum(1 for w in floor_workers if w.get("recruitment_stage", "").startswith("active"))
        offline  = sum(1 for w in floor_workers if w.get("recruitment_stage") == "rejected")
        warnings = sum(1 for w in floor_workers if (w.get("health") or "healthy") != "healthy")
        out.append({
            "floor_id": floor_id, "floor_number": n,
            "floor_name": dep_name, "department_id": dep_id,
            "zone_id": zone_id, "zone_name": zone_name,
            "floor_manager_id":   (mgrs.get("floor_manager") or {}).get("manager_id"),
            "floor_manager_name": (mgrs.get("floor_manager") or {}).get("display_name"),
            "zone_manager_id":    (mgrs.get("zone_manager")  or {}).get("manager_id"),
            "zone_manager_name":  (mgrs.get("zone_manager")  or {}).get("display_name"),
            "worker_count":        len(floor_workers),
            "active_worker_count": active,
            "offline_worker_count": offline,
            "warning_count":      warnings,
            "health":             "healthy" if warnings == 0 else "warning",
            "latest_report_ts":   _now(),
            "latest_report_summary": "Floor reporting · execution locks closed · advisory_only.",
            "reports_to":         (mgrs.get("zone_manager") or {}).get("display_name") or "Tower Operations Manager",
            "routes_to":          ["Tower Operations Manager", "Kernel Liaison Manager", "Penthouse Kernel"],
            "execution_allowed":  False,
        })
    return stamp_safe({"ok": True, "ts": _now(), "floor_reports": out})


def zone_reports():
    fr = floor_reports().get("floor_reports") or []
    out = {}
    for r in fr:
        zid = r["zone_id"]
        z = out.setdefault(zid, {
            "zone_id": zid, "zone_name": r["zone_name"],
            "floors": [], "worker_count": 0,
            "active_worker_count": 0, "warning_count": 0,
            "health": "healthy", "ts": _now(),
            "reports_to": "Tower Operations Manager",
        })
        z["floors"].append(r["floor_id"])
        z["worker_count"]        += r["worker_count"]
        z["active_worker_count"] += r["active_worker_count"]
        z["warning_count"]       += r["warning_count"]
        if r["warning_count"] > 0: z["health"] = "warning"
    return stamp_safe({"ok": True, "ts": _now(), "zone_reports": list(out.values())})


def tower_report():
    fr = floor_reports().get("floor_reports") or []
    zr = zone_reports().get("zone_reports") or []
    total_workers = sum(r["worker_count"] for r in fr)
    return stamp_safe({
        "ok": True, "ts": _now(),
        "tower_name": "QSB Tower V1.3",
        "phase": "QSB_TOWER_OPERATIONS_V1",
        "total_floors": len(fr),
        "total_workers": total_workers,
        "zones": zr,
        "tower_operations_manager": "Tower Operations Manager",
        "kernel_liaison_manager":   "Kernel Liaison Manager",
        "reports_to": "QSB Kernel (active_local_only)",
        "overall_health": "healthy" if all(z["health"] == "healthy" for z in zr) else "warning",
    })
