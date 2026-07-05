"""Management chain: floor managers + zone managers + Tower Operations Manager + Kernel Liaison."""

from pathlib import Path
from datetime import datetime, timezone
import json
import threading

from .safety_contract import LOCKED_FALSE, stamp_safe
from .org_schema      import FLOOR_TO_DEPARTMENT, ZONES, zone_for_floor


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
MGR_PATH = ROOT / "state/tower_ops/managers.json"
LOG_PATH = ROOT / "logs/tower_ops/manager_reports.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


# Default floor manager assignments — one per populated floor.
FLOOR_MANAGERS = {
    3:  "Research Floor Manager",
    14: "Media Floor Manager",
    15: "Speech Floor Manager",
    23: "AIR LLM Floor Manager",
    28: "Security Floor Manager",
    30: "Risk Floor Manager",
    31: "Audit Floor Manager",
    33: "Maintenance Floor Manager",
    35: "IT Networking Floor Manager",
    37: "Strategy Floor Manager",
    38: "Recruitment Floor Manager",
    41: "OANDA Floor Manager",
    44: "Accounts Floor Manager",
    45: "Quantum Floor Manager",
    42: "Binance Floor Manager",
    43: "Stocks Floor Manager",
    53: "Tower Command Floor Manager",
    55: "Penthouse Floor Manager",
}


# Zone manager → list of floors it covers
ZONE_MANAGER_ASSIGN = {
    "Trading Zone Manager":      [41, 42, 43, 44],
    "Intelligence Zone Manager": [23, 24, 25, 26, 27],
    "Operations Zone Manager":   [37, 38, 39, 40, 45],
    "Governance Zone Manager":   [28, 30, 31, 32, 33, 34, 35, 36],
    "Penthouse Zone Manager":    [53, 55],
    "Research Zone Manager":     [3, 4, 5],
    "Media/Sound Zone Manager":  [14, 15],
}


# Tower-level officers + Kernel Liaison + chief officers
TOWER_OFFICERS = [
    ("tower_operations_manager",  "Tower Operations Manager",        "Tower-wide operations coordination — reports to Kernel."),
    ("kernel_liaison_manager",    "Kernel Liaison Manager",          "Direct reporting interface to QSB Kernel."),
    ("chief_overseer",            "Chief Overseer",                   "Chief of all overseers."),
    ("chief_maintenance_officer", "Chief Maintenance Officer",        "Owns Diagnostics + Maintenance floor reporting."),
    ("chief_security_officer",    "Chief Security Officer",           "Owns Security floor + lock matrix."),
    ("chief_it_officer",          "Chief IT / Networking Officer",    "Owns Infrastructure Services floor."),
    ("chief_research_coord",      "Chief Research Coordinator",       "Owns Research floor."),
    ("chief_trading_telemetry",   "Chief Trading Telemetry Officer",  "Owns OANDA/Binance/Stocks read-only telemetry."),
    ("colonel_concierge",         "Colonel Concierge",                "Penthouse concierge serving Ross."),
    ("colonel_butler",            "Colonel Butler",                   "Penthouse butler — daily briefings."),
]


def _baseline():
    managers = []
    # Floor managers
    for n, name in FLOOR_MANAGERS.items():
        dep_name, dep_id = FLOOR_TO_DEPARTMENT.get(n, ("", ""))
        zone_id, zone_name = zone_for_floor(n)
        managers.append({
            "manager_id": "fm_" + dep_id + "_" + str(n),
            "display_name": name,
            "manager_type": "floor_manager",
            "assigned_scope": {"floor_id": "floor_{:02d}".format(n) if n != 55 else "penthouse",
                               "floor_number": n,
                               "department": dep_name, "department_id": dep_id,
                               "zone_id": zone_id, "zone_name": zone_name},
            "reports_to": _zone_manager_for_floor(n),
            "direct_reports": [],
            "health": "healthy",
            "latest_report_ts": _now(),
            "latest_report": "Floor live · roster reporting · execution locks closed.",
        })
    # Zone managers
    for zname, floors in ZONE_MANAGER_ASSIGN.items():
        managers.append({
            "manager_id": "zm_" + zname.lower().replace(" ", "_").replace("/", "_"),
            "display_name": zname,
            "manager_type": "zone_manager",
            "assigned_scope": {"floors": floors,
                               "zone_id": "_".join(zname.lower().split()[:-2]) or "zone"},
            "reports_to": "Tower Operations Manager",
            "direct_reports": [_floor_manager_id(n) for n in floors if n in FLOOR_MANAGERS],
            "health": "healthy",
            "latest_report_ts": _now(),
            "latest_report": "Zone live · floors reporting · execution locks closed.",
        })
    # Tower officers
    for tid, name, role in TOWER_OFFICERS:
        managers.append({
            "manager_id": tid,
            "display_name": name,
            "manager_type": "tower_manager",
            "assigned_scope": {"tower": True, "role": role},
            "reports_to": "QSB Kernel (active_local_only)" if tid in ("tower_operations_manager", "kernel_liaison_manager") else "Tower Operations Manager",
            "direct_reports": [],
            "health": "healthy",
            "latest_report_ts": _now(),
            "latest_report": role,
        })
    return {
        "registry": "qsb_tower_ops_management_chain_v1",
        "phase": "QSB_TOWER_OPERATIONS_V1",
        "ts": _now(),
        "managers": managers,
        **LOCKED_FALSE,
    }


def _zone_manager_for_floor(n):
    for zname, floors in ZONE_MANAGER_ASSIGN.items():
        if n in floors:
            return zname
    return "Tower Operations Manager"


def _floor_manager_id(n):
    dep_id = FLOOR_TO_DEPARTMENT.get(n, ("", ""))[1] or "x"
    return "fm_" + dep_id + "_" + str(n)


def _read():
    MGR_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MGR_PATH.exists():
        st = _baseline()
        MGR_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
        return st
    try: return json.loads(MGR_PATH.read_text(encoding="utf-8"))
    except Exception:
        st = _baseline()
        MGR_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
        return st


def _write(st):
    st["ts"] = _now()
    st.update(LOCKED_FALSE)
    MGR_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def all_managers():
    with _LOCK:
        return _read().get("managers") or []


def status():
    with _LOCK:
        st = _read()
        mgrs = st.get("managers") or []
        by_type = {}
        for m in mgrs:
            by_type[m.get("manager_type")] = by_type.get(m.get("manager_type"), 0) + 1
        return stamp_safe({
            "ok": True, "ts": _now(),
            "phase": st.get("phase"),
            "total_managers": len(mgrs),
            "by_type": by_type,
            "tower_operations_manager":   "Tower Operations Manager",
            "kernel_liaison_manager":     "Kernel Liaison Manager",
            "reports_to_kernel": ["Tower Operations Manager", "Kernel Liaison Manager"],
        })


def managers_for_floor(n):
    mgrs = all_managers()
    floor_mgr  = next((m for m in mgrs if m.get("manager_type") == "floor_manager" and m.get("assigned_scope", {}).get("floor_number") == n), None)
    zone_mgr   = next((m for m in mgrs if m.get("manager_type") == "zone_manager" and n in (m.get("assigned_scope", {}).get("floors") or [])), None)
    return {
        "floor_manager": floor_mgr,
        "zone_manager":  zone_mgr,
        "tower_operations_manager": next((m for m in mgrs if m["manager_id"] == "tower_operations_manager"), None),
        "kernel_liaison_manager":   next((m for m in mgrs if m["manager_id"] == "kernel_liaison_manager"), None),
    }
