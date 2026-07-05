"""Identity Badge V1 — QSB-WORKER-<FLOOR>-<DEPT>-<NUMBER>.

Deterministic badge generation so the same worker always gets the same
badge across restarts. Persisted at state/tower_ops/worker_badges.json.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import threading

from .safety_contract import LOCKED_FALSE, stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
BADGE_PATH = ROOT / "state/tower_ops/worker_badges.json"
LOG_PATH   = ROOT / "logs/tower_ops/access_events.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


# Department → short badge code
DEPT_CODE = {
    "trading_fx":          "OANDA",
    "trading_crypto":      "BINANCE",
    "trading_equities":    "STOCKS",
    "strategy":            "STRAT",
    "recruitment":         "RECRUIT",
    "maintenance":         "MAINT",
    "security":            "SEC",
    "it_networking":       "IT",
    "research_facility":   "RES",
    "speech_media":        "SPCH",
    "media":               "MEDIA",
    "audit":               "AUDIT",
    "risk":                "RISK",
    "openclaw_advisory":   "OPENC",
    "airllm_advisory":     "AIRLLM",
    "penthouse_staff":     "KERNEL",
    "accounts":            "ACCT",
    "quantum":             "QUANT",
    "model_ops":           "MODEL",
    "training":            "TRAIN",
    "compliance":          "COMP",
    "data_memory":         "DATA",
    "emergency_control":   "EMRG",
    "logistics":           "LIFT",
    "general":             "GEN",
}


def _floor_number(floor_id):
    if not floor_id: return 0
    if floor_id == "penthouse": return 55
    m = None
    import re
    m = re.match(r"^floor_(\d{1,2})$", floor_id)
    return int(m.group(1)) if m else 0


def make_badge_id(worker, n):
    floor_n = _floor_number(worker.get("floor_assignment"))
    dept_id = worker.get("team") or worker.get("department_id") or "general"
    dept_code = DEPT_CODE.get(dept_id, "GEN")
    return "QSB-WORKER-{:03d}-{}-{:03d}".format(floor_n, dept_code, n)


def assign_badges(workers):
    """Mutates each worker dict in-place to add badge_id + short_code + access_level.
    Persists the badge map to disk so badges are stable across restarts.
    """
    BADGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    badge_map = {}
    if BADGE_PATH.exists():
        try: badge_map = json.loads(BADGE_PATH.read_text(encoding="utf-8")).get("by_worker_id", {})
        except Exception: badge_map = {}
    counters = {}  # (floor_n, dept_code) -> last_used_n
    for b in badge_map.values():
        floor_n = _floor_number(b.get("floor_assignment"))
        dept_code = b.get("dept_code", "GEN")
        n = int(b.get("badge_number", 0))
        counters[(floor_n, dept_code)] = max(counters.get((floor_n, dept_code), 0), n)

    with _LOCK:
        for w in workers:
            wid = w.get("id") or w.get("worker_id")
            if not wid: continue
            if wid in badge_map and "badge_id" in badge_map[wid]:
                # Reuse stored badge
                w["badge_id"]      = badge_map[wid]["badge_id"]
                w["short_code"]    = badge_map[wid].get("short_code", w["badge_id"].split("-")[-1])
                w["access_level"]  = _access_level_for(w)
                continue
            floor_n = _floor_number(w.get("floor_assignment"))
            dept_id = w.get("team") or w.get("department_id") or "general"
            dept_code = DEPT_CODE.get(dept_id, "GEN")
            counters[(floor_n, dept_code)] = counters.get((floor_n, dept_code), 0) + 1
            n = counters[(floor_n, dept_code)]
            badge_id = "QSB-WORKER-{:03d}-{}-{:03d}".format(floor_n, dept_code, n)
            w["badge_id"]     = badge_id
            w["short_code"]   = "{}-{:03d}".format(dept_code, n)
            w["access_level"] = _access_level_for(w)
            badge_map[wid] = {"badge_id": badge_id, "short_code": w["short_code"],
                              "dept_code": dept_code, "badge_number": n,
                              "floor_assignment": w.get("floor_assignment"),
                              "created_ts": _now()}
        BADGE_PATH.write_text(json.dumps({
            "registry": "qsb_worker_badges_v1",
            "ts": _now(),
            "by_worker_id": badge_map,
            **LOCKED_FALSE,
        }, indent=2), encoding="utf-8")
    return workers


def _access_level_for(w):
    dept = w.get("team") or w.get("department_id") or "general"
    stage = w.get("stage") or w.get("recruitment_stage") or "active_advisory"
    role = (w.get("role") or "").lower()
    display = (w.get("display_name") or "").lower()
    if "concierge" in display or "butler" in display or "penthouse" in display:
        return "penthouse_staff"
    if "tower operations manager" in display: return "tower_manager"
    if "kernel liaison" in display:           return "kernel_liaison"
    if dept == "security":                    return "security"
    if dept == "maintenance":                 return "maintenance"
    if dept == "it_networking":               return "it_admin_read_only"
    if "overseer" in display or "overseer" in role: return "overseer"
    if "zone manager" in display:             return "zone_manager"
    if "floor manager" in display or "manager" in display: return "floor_manager"
    if stage in ("active_advisory",):         return "worker_advisory"
    if stage in ("active_read_only",):        return "worker_read_only"
    return "worker_read_only"


def all_badges():
    if not BADGE_PATH.exists(): return {}
    try: return json.loads(BADGE_PATH.read_text(encoding="utf-8")).get("by_worker_id", {})
    except Exception: return {}


def status():
    badges = all_badges()
    return stamp_safe({
        "ok": True, "ts": _now(),
        "phase": "QSB_TOWER_OPERATIONS_V2",
        "badge_count": len(badges),
        "badge_format": "QSB-WORKER-<FLOOR3>-<DEPT>-<NNN>",
        "dept_codes": DEPT_CODE,
    })
