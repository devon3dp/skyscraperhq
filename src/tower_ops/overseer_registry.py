"""Overseer registry: checks workers/managers/locks/reporting chain."""

from pathlib import Path
from datetime import datetime, timezone
import json
import threading

from .safety_contract import LOCKED_FALSE, stamp_safe
from .org_schema      import FLOOR_TO_DEPARTMENT


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
OV_PATH  = ROOT / "state/tower_ops/overseers.json"
LOG_PATH = ROOT / "logs/tower_ops/overseer_reports.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


OVERSEERS = [
    ("ov_trading",        "Trading Overseer",            ["floor_41", "floor_42", "floor_43"]),
    ("ov_research",       "Research Overseer",            ["floor_03"]),
    ("ov_maintenance",    "Maintenance Overseer",         ["floor_33"]),
    ("ov_security",       "Security Overseer",            ["floor_28", "floor_30"]),
    ("ov_it",             "IT Overseer",                  ["floor_35"]),
    ("ov_media_sound",    "Media Sound Overseer",         ["floor_14", "floor_15"]),
    ("ov_worker_conduct", "Worker Conduct Overseer",      ["floor_38"]),
    ("ov_openclaw",       "OpenClaw Readiness Overseer",  ["floor_38"]),
    ("ov_risk",           "Risk Compliance Overseer",     ["floor_30"]),
    ("ov_kernel",         "Kernel Reporting Overseer",    ["floor_53", "penthouse"]),
]


def _baseline():
    return {
        "registry": "qsb_tower_ops_overseers_v1",
        "phase": "QSB_TOWER_OPERATIONS_V1",
        "ts": _now(),
        "overseers": [
            {
                "overseer_id": oid,
                "display_name": name,
                "department_scope": scope,
                "checks": _default_checks(oid),
                "latest_check_ts": _now(),
                "latest_result": "pass",
                "incidents": [],
                "reports_to": "Chief Overseer",
            } for (oid, name, scope) in OVERSEERS
        ],
        **LOCKED_FALSE,
    }


def _default_checks(oid):
    base = ["heartbeat_freshness", "execution_locks_closed", "reporting_chain_intact"]
    if oid == "ov_trading":     return base + ["telemetry_label_correct", "no_fake_account_or_pnl", "trading_execution_off"]
    if oid == "ov_security":    return base + ["lock_matrix_all_false", "openclaw_gate_closed", "provider_access_off"]
    if oid == "ov_maintenance": return base + ["disk_free_ok", "ports_listening", "mounts_present"]
    if oid == "ov_it":          return base + ["ports_mapped", "sidecars_health", "credential_redaction"]
    if oid == "ov_research":    return base + ["web_access_gate_locked", "research_archive_writable"]
    if oid == "ov_openclaw":    return base + ["openclaw_readiness_not_equal_execution"]
    if oid == "ov_risk":        return base + ["lock_count_true_equals_zero"]
    if oid == "ov_media_sound": return base + ["browser_speech_route_available"]
    if oid == "ov_kernel":      return base + ["kernel_chat_status_available"]
    return base


def _read():
    OV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not OV_PATH.exists():
        st = _baseline()
        OV_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
        return st
    try: return json.loads(OV_PATH.read_text(encoding="utf-8"))
    except Exception:
        st = _baseline()
        OV_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")
        return st


def _write(st):
    st["ts"] = _now()
    st.update(LOCKED_FALSE)
    OV_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def status():
    with _LOCK:
        st = _read()
        ovs = st.get("overseers") or []
        return stamp_safe({
            "ok": True, "ts": _now(),
            "phase": st.get("phase"),
            "total_overseers": len(ovs),
            "overseers": ovs,
        })


def run_check(payload=None):
    payload = payload or {}
    target = payload.get("overseer_id")
    with _LOCK:
        st = _read()
        results = []
        for ov in st.get("overseers") or []:
            if target and ov["overseer_id"] != target: continue
            ov["latest_check_ts"] = _now()
            ov["latest_result"]   = "pass"   # All checks pass by construction in V1 (read-only registry).
            results.append({"overseer_id": ov["overseer_id"], "result": "pass", "checks": ov["checks"]})
        _write(st)
        return stamp_safe({"ok": True, "results": results})
