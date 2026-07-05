"""Access Control V1 — 12 access levels + per-worker allow/forbid matrix.

This module enforces NOTHING in code paths that lead to execution.
It is a description of what each access level is permitted to read or
report on. Every check returns booleans only — never enables locks.
"""

from pathlib import Path
from datetime import datetime, timezone
import json

from .safety_contract import LOCKED_FALSE, stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
MATRIX_PATH = ROOT / "state/tower_ops/access_matrix.json"
LOG_PATH    = ROOT / "logs/tower_ops/access_events.jsonl"


def _now(): return datetime.now(timezone.utc).isoformat()


ACCESS_LEVELS = (
    "visitor", "worker_read_only", "worker_advisory",
    "floor_manager", "zone_manager", "overseer",
    "tower_manager", "kernel_liaison",
    "security", "maintenance", "it_admin_read_only", "penthouse_staff",
)

# Capability matrix — what each level may READ. None of these grant execution.
CAPS = {
    "visitor":              {"read_unified", "read_floor_directory"},
    "worker_read_only":     {"read_unified", "read_floor_detail", "read_team_registries"},
    "worker_advisory":      {"read_unified", "read_floor_detail", "read_team_registries",
                              "emit_advisory_packet", "write_audit_log"},
    "floor_manager":        {"read_unified", "read_floor_detail", "read_roster",
                              "read_floor_reports", "report_to_zone"},
    "zone_manager":         {"read_unified", "read_floor_detail", "read_roster",
                              "read_zone_reports", "report_to_tower"},
    "overseer":             {"read_unified", "read_floor_detail", "read_roster",
                              "read_overseer_checks", "run_overseer_checks", "escalate_incident"},
    "tower_manager":        {"read_unified", "read_floor_detail", "read_tower_report",
                              "report_to_kernel"},
    "kernel_liaison":       {"read_unified", "read_floor_detail", "read_tower_report",
                              "report_to_kernel", "open_kernel_chat"},
    "security":             {"read_unified", "read_locks", "read_incidents",
                              "ack_incident", "escalate_incident"},
    "maintenance":          {"read_unified", "read_maintenance_checks",
                              "run_maintenance_check", "ack_alert"},
    "it_admin_read_only":   {"read_unified", "read_ports", "read_sidecars",
                              "read_connectivity", "read_routes",
                              "read_credentials_presence_only"},
    "penthouse_staff":      {"read_unified", "read_tower_report", "open_kernel_chat",
                              "open_speech", "open_recruitment", "open_maintenance",
                              "open_security", "open_it", "open_research",
                              "open_accounts", "open_quantum"},
}


def _allowed_data(level):
    """Data-domain permissions per level. Strictly read-only descriptors."""
    base = {"unified", "floor_directory"}
    if level in ("worker_advisory", "floor_manager", "zone_manager", "overseer",
                  "tower_manager", "kernel_liaison", "penthouse_staff"):
        base |= {"floor_detail", "manager_reports", "overseer_reports"}
    if level == "security":         base |= {"lock_matrix", "incidents"}
    if level == "maintenance":      base |= {"maintenance_checks", "disk_free", "ports"}
    if level == "it_admin_read_only": base |= {"ports", "sidecars", "connectivity", "routes"}
    return sorted(base)


def _allowed_trading_data(level, dept):
    if dept in ("trading_fx", "trading_crypto", "trading_equities"):
        return ["read_market_data", "read_account_summary_redacted",
                "read_paper_signals", "read_paper_ledger"]
    if dept == "accounts":
        return ["read_pnl_summary_only", "read_paper_ledger", "read_telemetry_labels"]
    if level == "tower_manager" or level == "kernel_liaison":
        return ["read_summary_only"]
    return []


def _allowed_model_access(level, dept):
    if dept == "airllm_advisory":   return ["read_airllm_chamber_registry", "manual_advisory_lane_only"]
    if dept == "model_ops":         return ["read_model_lanes", "read_model_router"]
    if dept == "penthouse_staff":   return ["read_model_lanes", "open_kernel_chat"]
    if level == "kernel_liaison":   return ["open_kernel_chat", "summarize_to_kernel"]
    if level == "worker_advisory":  return ["read_model_lanes"]
    return ["read_model_lanes"]


def access_card(worker):
    """Compute the full access card for one worker. No state mutation."""
    level = worker.get("access_level") or "worker_read_only"
    dept  = worker.get("team") or worker.get("department_id") or "general"
    floor_id = worker.get("floor_assignment")
    return {
        "access_level": level,
        "access_zones": [worker.get("zone_id") or "infrastructure_zone"],
        "allowed_floors":   [floor_id] if floor_id else [],
        "denied_floors":    [],
        "allowed_rooms":    [worker.get("desk_assignment") or "any_desk"],
        "allowed_actions":  worker.get("allowed_actions") or [],
        "forbidden_actions":worker.get("forbidden_actions") or [],
        "data_access":          _allowed_data(level),
        "trading_data_access":  _allowed_trading_data(level, dept),
        "model_access":         _allowed_model_access(level, dept),
        "openclaw_access":      "review_only_advisory" if worker.get("openclaw_ready") else "denied",
        "web_access":           "denied",
        "audio_access":         "browser_only" if dept in ("penthouse_staff", "speech_media") else "denied",
        "kernel_access":        "open_chat_only" if level in ("kernel_liaison", "penthouse_staff") else "denied",
        "airllm_access":        "advisory_read_only" if dept == "airllm_advisory" else "denied",
        "quantum_access":       "advisory_read_only" if dept == "quantum" else "denied",
        "accounting_access":    "read_summary" if dept == "accounts" else ("read_floor_summary" if level in ("floor_manager","zone_manager","tower_manager","kernel_liaison","penthouse_staff") else "denied"),
        # NEVER true — execution gates
        "live_trading_enabled":             False,
        "order_execution_enabled":          False,
        "openclaw_execution_enabled":       False,
        "provider_execution_enabled":       False,
        "autonomous_dispatch_enabled":      False,
        "web_access_autonomous_enabled":    False,
    }


def status():
    return stamp_safe({
        "ok": True, "ts": _now(),
        "phase": "QSB_TOWER_OPERATIONS_V2",
        "access_levels": list(ACCESS_LEVELS),
        "capabilities_by_level": {k: sorted(v) for k, v in CAPS.items()},
        "policy": "READ_ONLY DESCRIPTORS — does not toggle any execution lock",
    })


def check_access(payload):
    """Local-only check. Returns booleans only."""
    payload = payload or {}
    level = payload.get("access_level")
    action = payload.get("action")
    if not level or not action:
        return {"ok": False, "error": "access_level + action required"}
    caps = CAPS.get(level, set())
    allowed = action in caps
    return stamp_safe({"ok": True, "ts": _now(),
                        "access_level": level, "action": action,
                        "allowed": bool(allowed),
                        "execution_allowed": False})
