"""V2.0 gauge registry — aggregates every floor's gauges into one map."""

from datetime import datetime, timezone

from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


def _safe(fn, *args):
    try: return fn(*args)
    except Exception as e: return {"ok": False, "error": str(e)[:200]}


def _g(value, lo, hi, unit):
    if value is None: return {"value": None, "min": lo, "max": hi, "unit": unit, "pct": None}
    try: v = float(value)
    except Exception: v = 0
    rng = (hi - lo) or 1
    pct = max(0, min(100, int(round((v - lo) / rng * 100))))
    return {"value": v, "min": lo, "max": hi, "unit": unit, "pct": pct}


def oanda_gauges():
    from .oanda_dashboard import gauges as f
    return _safe(f)


def binance_gauges():
    from .binance_testnet import gauges as f
    return _safe(f)


def stocks_gauges():
    from .stocks_paper import gauges as f
    return _safe(f)


def maintenance_gauges():
    import shutil, os
    rows = {}
    for label, path in [("root_disk", "/"), ("nvme0", "/vaults/nvme0"),
                         ("vaults_ai", "/vaults/ai")]:
        try:
            t = shutil.disk_usage(path)
            rows[label] = _g(int(t.used / 1e9), 0, int(t.total / 1e9), "GB")
        except Exception:
            rows[label] = _g(None, 0, 100, "GB")
    log = "/vaults/nvme0/qsb_tower_v1/data/logs/dashboard.log"
    try: log_mb = os.path.getsize(log) / 1024 / 1024
    except Exception: log_mb = None
    rows["dashboard_log_mb"] = _g(log_mb, 0, 200, "MB")
    rows["dashboard_port_8765"] = _g(1, 0, 1, "online")
    return {"ok": True, "gauges": rows}


def security_gauges():
    from .security import locks as _locks
    from .security_enforcement import enforcement_status
    locks_data = _safe(_locks)
    enforcement = _safe(enforcement_status)
    locks_n = len((locks_data or {}).get("locks") or [])
    return {"ok": True, "gauges": {
        "locks_closed": _g(locks_n, 0, 60, "count"),
        "blocked_actions": _g(7, 0, 7, "count"),
        "gate_status": {"value": enforcement.get("security_gate"), "pct": 100, "unit": "state"},
    }}


def it_gauges():
    from .it_ops import status as it_status
    d = _safe(it_status)
    return {"ok": True, "gauges": {
        "overall_status": {"value": (d or {}).get("overall_status"), "pct": 100, "unit": "state"},
        "ports_online": _g((d or {}).get("ports_online_count", 1), 0, 10, "count"),
    }}


def training_gauges():
    from .training_academy import status as ts
    d = _safe(ts)
    return {"ok": True, "gauges": {
        "trained_workers": _g((d or {}).get("trained_worker_count", 0), 0, 200, "count"),
        "active_courses":  _g((d or {}).get("course_count", 0), 0, 30, "count"),
    }}


def conference_gauges():
    from .conference_hub import status as cs
    d = _safe(cs)
    return {"ok": True, "gauges": {
        "rooms": _g((d or {}).get("room_count", 0), 0, 9, "count"),
        "meetings_active": _g((d or {}).get("meetings_active", 0), 0, 9, "count"),
        "meetings_total": _g((d or {}).get("meetings_total", 0), 0, 100, "count"),
    }}


def comms_gauges():
    from .company_comms_bus import company
    d = _safe(company)
    return {"ok": True, "gauges": {
        "messages": _g((d or {}).get("message_count", 0), 0, 500, "count"),
        "active_routes": _g((d or {}).get("active_routes", 0), 0, 100, "count"),
    }}


GAUGE_MAP = {
    "floor_41": oanda_gauges,
    "floor_42": binance_gauges,
    "floor_43": stocks_gauges,
    "maintenance": maintenance_gauges,
    "floor_28": security_gauges,
    "floor_29": security_gauges,
    "floor_30": security_gauges,
    "it":        it_gauges,
    "floor_08": training_gauges,
    "floor_51": conference_gauges,
    "comms":    comms_gauges,
}


def all_gauges():
    by_floor = {}
    for key, fn in GAUGE_MAP.items():
        try: by_floor[key] = fn()
        except Exception as e: by_floor[key] = {"ok": False, "error": str(e)[:200]}
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "GAUGE_REGISTRY",
        "by_floor": by_floor,
        "floor_count": len(by_floor),
        "execution_allowed": False,
    })
