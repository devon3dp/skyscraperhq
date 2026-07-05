"""Lift status registry — 9 lifts with deterministic motion + occupancy."""

from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import time

from .safety_contract import stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_PATH = ROOT / "state/tower_ops/lifts.json"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


LIFT_DEFS = [
    {"lift_id": "LIFT-01", "name": "Low-Rise Main",   "serves": list(range(0, 16)),   "phase": 0.0},
    {"lift_id": "LIFT-02", "name": "Mid-Rise Main",   "serves": list(range(15, 31)),  "phase": 0.5},
    {"lift_id": "LIFT-03", "name": "High-Rise Main",  "serves": list(range(30, 46)),  "phase": 1.0},
    {"lift_id": "LIFT-04", "name": "Express Penthouse","serves": [0, 41, 42, 43, 53, 55], "phase": 1.5},
    {"lift_id": "LIFT-05", "name": "Trading Express", "serves": [0, 30, 31, 37, 38, 41, 42, 43], "phase": 2.0},
    {"lift_id": "LIFT-06", "name": "Models Lift",     "serves": [0, 14, 15, 23, 24, 26, 27, 55], "phase": 2.5},
    {"lift_id": "LIFT-07", "name": "Governance Lift", "serves": [0, 28, 30, 31, 32, 33, 35, 53], "phase": 3.0},
    {"lift_id": "LIFT-08", "name": "Service Lift",    "serves": [0, 33, 35, 22, 28, 38], "phase": 3.5},
    {"lift_id": "LIFT-09", "name": "Kernel Liaison",  "serves": [0, 23, 28, 30, 31, 37, 53, 55], "phase": 4.0},
]


def _occupancy_for(lift, t):
    """Deterministic worker occupancy from worker registry — by team affinity."""
    try:
        from .worker_registry import workers as worker_list
        ws = (worker_list().get("workers") or [])
        # Mix workers whose home is in `serves` and rotate by phase
        mix = [w for w in ws if w.get("floor_assignment") and
                _floor_num(w["floor_assignment"]) in lift["serves"]]
        # rotate
        offset = int((t + lift["phase"]) * 0.5) % max(1, len(mix))
        cap = 4
        return [{
            "worker_id":   w.get("id"),
            "badge_id":    w.get("badge_id"),
            "short_code":  w.get("short_code"),
            "display_name":w.get("display_name"),
        } for w in mix[offset:offset + cap]]
    except Exception:
        return []


def _floor_num(s):
    if s == "penthouse": return 55
    import re
    m = re.match(r"^floor_(\d{1,2})$", s or "")
    return int(m.group(1)) if m else 0


def status():
    t = time.time()
    out = []
    for L in LIFT_DEFS:
        serves = L["serves"]
        # Deterministic position — triangle wave inside the served range
        period = 24.0
        u = ((t / period + L["phase"]) % 1.0)
        u = 1.0 - abs(u * 2 - 1.0)
        idx = int(u * (len(serves) - 1))
        cur  = serves[idx]
        tgt  = serves[min(idx + 1, len(serves) - 1)]
        occ  = _occupancy_for(L, t)
        out.append({
            "lift_id": L["lift_id"],
            "name":    L["name"],
            "current_floor":  cur,
            "target_floor":   tgt,
            "occupancy_count":len(occ),
            "workers_inside": occ,
            "status": "moving" if cur != tgt else "loading",
            "serves": serves,
            "execution_allowed": False,
        })
    return stamp_safe({"ok": True, "ts": _now(),
                        "phase": "QSB_TOWER_OPERATIONS_V2",
                        "lifts": out, "lift_count": len(out)})


def routes():
    return stamp_safe({"ok": True, "ts": _now(),
                        "routes": [{"lift_id": L["lift_id"], "serves": L["serves"]} for L in LIFT_DEFS]})
