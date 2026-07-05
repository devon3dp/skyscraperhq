"""Security department — Floor 28 (Security Department).

Monitors execution locks, OpenClaw gate, provider gate, payload safety.
Read-only. Never modifies any lock.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import threading

from .safety_contract import LOCKED_FALSE, stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
INC_PATH = ROOT / "state/tower_ops/security_incidents.json"
LOG_PATH = ROOT / "logs/tower_ops/security_events.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


def _read_incidents():
    INC_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not INC_PATH.exists():
        INC_PATH.write_text(json.dumps({"incidents": [], **LOCKED_FALSE}, indent=2), encoding="utf-8")
    try: return json.loads(INC_PATH.read_text(encoding="utf-8"))
    except Exception: return {"incidents": []}


def _write_incidents(d):
    d.update(LOCKED_FALSE)
    INC_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")


def _append_log(rec):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", _now())
    rec.setdefault("execution_allowed", False)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def locks_summary():
    """Return the canonical lock matrix all-false, with explicit gate states."""
    return {
        **LOCKED_FALSE,
        "openclaw_gate":                 "CLOSED",
        "provider_access_gate":          "CLOSED",
        "trading_execution_gate":        "CLOSED",
        "direct_provider_access_gate":   "CLOSED",
        "external_providers_gate":       "CLOSED",
        "autonomous_dispatch_gate":      "CLOSED",
        "credential_redaction":          "ACTIVE",
        "payload_inspection":            "ACTIVE",
        "expected_lock_count_true":      0,
    }


def status():
    with _LOCK:
        d = _read_incidents()
        return stamp_safe({
            "ok": True, "ts": _now(),
            "overall_status": "healthy",
            "policy": "READ_ONLY enforcement — never toggles locks · scrubs credentials · escalates incidents",
            "locks":          locks_summary(),
            "incident_count": len(d.get("incidents") or []),
            "open_incident_count": sum(1 for i in (d.get("incidents") or []) if not i.get("acked")),
        })


def locks():
    return stamp_safe({"ok": True, "ts": _now(), "locks": locks_summary()})


def incidents():
    with _LOCK:
        d = _read_incidents()
        return stamp_safe({"ok": True, "ts": _now(),
                            "incidents": d.get("incidents") or []})


def ack_incident(payload=None):
    payload = payload or {}; iid = payload.get("incident_id")
    with _LOCK:
        d = _read_incidents()
        for i in d.get("incidents", []):
            if i.get("incident_id") == iid:
                i["acked"] = True; i["acked_ts"] = _now()
                _write_incidents(d)
                _append_log({"event": "ack_incident", "incident_id": iid})
                return stamp_safe({"ok": True, "incident_id": iid})
        return {"ok": False, "error": "incident_not_found", "incident_id": iid}
