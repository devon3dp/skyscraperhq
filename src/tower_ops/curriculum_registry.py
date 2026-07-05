"""Curriculum Registry — 21 courses + sensitive-role gating."""

from datetime import datetime, timezone
from pathlib import Path
import json
import threading

from .safety_contract import LOCKED_FALSE, stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_PATH = ROOT / "state/tower_ops/curriculum_registry.json"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


# (course_id, title, classroom, gates_capability)
COURSES = [
    ("qsb_induction",                "QSB Induction",                            "Reception / Intake Desk",        None),
    ("worker_badge_identity",        "Worker Badge and Identity",                "Access Badge Classroom",         None),
    ("safety_locks_101",             "Safety Locks 101",                         "Safety and Locks Classroom",     "read_lock_matrix"),
    ("trading_telemetry_readonly",   "Read-Only Trading Telemetry",              "Trading Telemetry Classroom",    "read_trading_telemetry"),
    ("oanda_telemetry_reading",      "OANDA Telemetry Reading",                  "Trading Telemetry Classroom",    "access_floor_41"),
    ("binance_telemetry_reading",    "Binance Telemetry Reading",                "Trading Telemetry Classroom",    "access_floor_42"),
    ("stocks_telemetry_reading",     "Stocks Telemetry Reading",                 "Trading Telemetry Classroom",    "access_floor_43"),
    ("accounts_pnl_labels",          "Accounts and P&L Labels",                  "Accounts Classroom",             "access_accounts_data"),
    ("openclaw_readiness_not_exec",  "OpenClaw Readiness, Not Execution",        "OpenClaw Readiness Classroom",   "openclaw_readiness_review"),
    ("security_permissions",         "Security and Permissions",                 "Security Classroom",             "security_role"),
    ("maintenance_monitoring",       "Maintenance Monitoring",                   "Maintenance Classroom",          "maintenance_role"),
    ("it_local_sidecars",            "IT and Local Sidecars",                    "IT / Networking Classroom",      "it_role"),
    ("research_quality_sources",     "Research Quality and Source Checking",     "Research Methods Classroom",     "research_role"),
    ("model_lane_routing",           "Model Lane Routing",                       "Kernel Etiquette Classroom",     "read_model_lanes"),
    ("airllm_advisory_use",          "AirLLM Advisory Use",                      "Kernel Etiquette Classroom",     "airllm_manual_query"),
    ("quantum_safety_lab",           "Quantum Safety and Symbolic Lab",          "Quantum Classroom",              "access_quantum_floor"),
    ("kernel_communication",         "Kernel Communication",                     "Kernel Etiquette Classroom",     "kernel_chat_use"),
    ("speech_media_controls",        "Speech and Media Controls",                "Kernel Etiquette Classroom",     "speech_media_use"),
    ("manager_reporting",            "Manager Reporting",                        "Classrooms",                     "manager_role"),
    ("overseer_duties",              "Overseer Duties",                          "Classrooms",                     "overseer_role"),
    ("emergency_procedure",          "Emergency Procedure",                      "Safety and Locks Classroom",     "emergency_role"),
]


def _baseline():
    return {
        "registry": "qsb_curriculum_v1",
        "phase":    "QSB_TOWER_OPERATIONS_V3",
        "ts":       _now(),
        "courses":  [{
            "course_id": cid, "title": title, "classroom": room,
            "gates_capability": gate, "duration_minutes_advisory": 30,
            "policy": "ADVISORY_ONLY — no execution unlocks.",
        } for (cid, title, room, gate) in COURSES],
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


def courses():
    with _LOCK:
        return stamp_safe({"ok": True, "ts": _now(), "courses": _read().get("courses") or []})


def course_count():
    return len(_read().get("courses") or [])


# ── Sensitive roles → required course bundle ────────────────────────────
SENSITIVE_ROLE_GATES = {
    "trading_floor_worker":     ["safety_locks_101", "trading_telemetry_readonly"],
    "accounts_worker":          ["safety_locks_101", "accounts_pnl_labels"],
    "openclaw_ready":           ["safety_locks_101", "openclaw_readiness_not_exec"],
    "security_worker":          ["safety_locks_101", "security_permissions"],
    "maintenance_worker":       ["safety_locks_101", "maintenance_monitoring"],
    "it_worker":                ["safety_locks_101", "it_local_sidecars"],
    "quantum_worker":           ["safety_locks_101", "quantum_safety_lab"],
    "kernel_liaison":           ["safety_locks_101", "kernel_communication"],
    "airllm_worker":            ["safety_locks_101", "airllm_advisory_use"],
    "research_worker":          ["safety_locks_101", "research_quality_sources"],
    "model_ops_worker":         ["safety_locks_101", "model_lane_routing"],
    "overseer":                 ["safety_locks_101", "overseer_duties"],
    "floor_manager":            ["safety_locks_101", "manager_reporting"],
}


def required_for(role_or_team):
    """Return list of required course_ids for a sensitive role/team label."""
    return list(SENSITIVE_ROLE_GATES.get(role_or_team, []))
