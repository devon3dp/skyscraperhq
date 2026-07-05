"""Research facility — Floor 3 (Research Department).

Local-only research task registry. Web access remains gated.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import threading
import uuid

from .safety_contract import LOCKED_FALSE, stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_PATH = ROOT / "state/tower_ops/research_tasks.json"
LOG_PATH   = ROOT / "logs/tower_ops/manager_reports.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


SEED_TASKS = [
    {"task_id": "rt_001", "title": "Catalog QSB Tower V1.3 floor manifests",     "status": "in_progress", "owner": "Architecture Researcher"},
    {"task_id": "rt_002", "title": "AirLLM advisory chamber capability inventory","status": "in_progress","owner": "Model Capability Researcher"},
    {"task_id": "rt_003", "title": "Cross-market correlation baseline (paper)",   "status": "queued",     "owner": "Architecture Researcher"},
    {"task_id": "rt_004", "title": "OpenClaw readiness criteria documentation",   "status": "queued",     "owner": "Code Pattern Researcher"},
    {"task_id": "rt_005", "title": "Sound/speech routing pattern survey",         "status": "queued",     "owner": "Architecture Researcher"},
]


def _baseline():
    return {
        "registry": "qsb_research_facility_v1",
        "phase": "QSB_TOWER_OPERATIONS_V1",
        "ts": _now(),
        "tasks": [dict(t, created_ts=_now(), updated_ts=_now()) for t in SEED_TASKS],
        "web_access_gate": "LOCKED",
        **LOCKED_FALSE,
    }


def _read():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        st = _baseline()
        STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
        return st
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        st = _baseline()
        STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
        return st


def _write(st):
    st["ts"] = _now(); st.update(LOCKED_FALSE)
    STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def status():
    with _LOCK:
        st = _read()
        ts = st.get("tasks") or []
        by_status = {}
        for t in ts: by_status[t.get("status", "queued")] = by_status.get(t.get("status", "queued"), 0) + 1
        return stamp_safe({
            "ok": True, "ts": _now(),
            "overall_status": "healthy",
            "total_tasks": len(ts), "by_status": by_status,
            "web_access_gate": "LOCKED",
            "policy": "LOCAL_TASK_REGISTRY_ONLY — no autonomous web research",
        })


def tasks():
    with _LOCK:
        st = _read()
        return stamp_safe({"ok": True, "ts": _now(), "tasks": st.get("tasks") or []})


def create_task(payload=None):
    payload = payload or {}
    title = (payload.get("title") or "").strip()
    if not title: return {"ok": False, "error": "title_required"}
    new = {"task_id": "rt_" + uuid.uuid4().hex[:8], "title": title,
           "status": "queued", "owner": payload.get("owner") or "Research Intake Clerk",
           "created_ts": _now(), "updated_ts": _now()}
    with _LOCK:
        st = _read()
        st["tasks"].append(new); _write(st)
    return stamp_safe({"ok": True, "task": new})


def complete_task(payload=None):
    payload = payload or {}; tid = payload.get("task_id")
    with _LOCK:
        st = _read()
        for t in st.get("tasks") or []:
            if t.get("task_id") == tid:
                t["status"] = "complete"; t["updated_ts"] = _now()
                _write(st)
                return stamp_safe({"ok": True, "task": t})
        return {"ok": False, "error": "task_not_found", "task_id": tid}


def reports():
    return stamp_safe({"ok": True, "ts": _now(),
                        "research_reports": [
                            {"summary": "Research queue maintained locally · web access locked."},
                        ]})
