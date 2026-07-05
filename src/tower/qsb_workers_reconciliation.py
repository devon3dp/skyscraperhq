"""
QSB Tower V2 — Canonical Worker Reconciliation + Employment Expansion
Phase: QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2

Walks every worker-bearing registry, deduplicates by worker_id, and
produces:

  data/registries/qsb_canonical_workers.json
  data/registries/qsb_worker_count_reconciliation.json

Then EMPLOYS the 19 new workers requested by the V2 phase prompt for
reporting / paper-tasking / learning / trade observation / dashboard
telemetry. None of them are granted real execution access.

This module records the previous-mismatch reason (each subsystem keeps
its own worker slate; no single source-of-truth before V2) and exposes
counts by floor and by role.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import re

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

P_CANONICAL = REG / "qsb_canonical_workers.json"
P_RECON     = REG / "qsb_worker_count_reconciliation.json"
P_NEW_HIRES = REG / "qsb_new_workers_employed.json"
L_RECON     = LOGS / "qsb_worker_reconciliation.jsonl"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _safety_envelope():
    return {
        "real_execution_enabled":              False,
        "openclaw_real_tool_execution_enabled":False,
        "active_local_only":                   True,
        "advisory_only":                       True,
        "execution_allowed":                   False,
        "real_money_live_trading_enabled":     False,
    }


# ── New workers we explicitly employ ───────────────────────────────────

NEW_EMPLOYED_WORKERS = [
    ("wrk_binance_market_scout",
     "Binance Market Scout",
     "Watches Binance testnet tickers and flags momentum windows.",
     "floor_42_binance_trading_floor",
     "market_observer"),
    ("wrk_spread_watcher",
     "Spread Watcher",
     "Tracks bid/ask spread narrowing across instruments.",
     "floor_42_binance_trading_floor",
     "market_observer"),
    ("wrk_risk_clerk",
     "Risk Clerk",
     "Confirms every paper trade respects max_open_trades and stop_rule.",
     "floor_30_permissions_risk",
     "risk_supervisor"),
    ("wrk_trade_ledger_clerk",
     "Trade Ledger Clerk",
     "Keeps the paper-trade SQLite ledger consistent.",
     "floor_31_audit_ledger",
     "ledger_clerk"),
    ("wrk_exit_rule_monitor",
     "Exit Rule Monitor",
     "Watches stop/target/timeout rules on open trades.",
     "floor_30_permissions_risk",
     "exit_supervisor"),
    ("wrk_mistake_reviewer",
     "Mistake Reviewer",
     "Reviews closed losing trades and proposes lessons.",
     "floor_38_sandbox_operations",
     "learning"),
    ("wrk_pnl_accountant",
     "PnL Accountant",
     "Aggregates realized/unrealized PnL across paper floors.",
     "floor_44_accounts_department",
     "accounting"),
    ("wrk_strategy_student",
     "Strategy Student",
     "Practises new strategies against simulated paper data.",
     "floor_37_simulation_labs",
     "learning"),
    ("wrk_arbitrage_observer",
     "Arbitrage Observer",
     "Observes spreads across paper venues — never places real orders.",
     "floor_37_simulation_labs",
     "market_observer"),
    ("wrk_openclaw_liaison",
     "OpenClaw Liaison",
     "Channels OpenClaw diagnostic tickets to Kernel and Guardian.",
     "floor_38_sandbox_operations",
     "supervision"),
    ("wrk_dashboard_visual_inspector",
     "Dashboard Visual Inspector",
     "Validates that 3D dashboard panels render the live registries.",
     "floor_53_tower_command",
     "ui_qa"),
    ("wrk_floor_traffic_controller",
     "Floor Traffic Controller",
     "Schedules lift packets to avoid cross-floor contention.",
     "floor_36_lift_operations",
     "lift_ops"),
    ("wrk_worker_registry_clerk",
     "Worker Registry Clerk",
     "Maintains the canonical worker registry — this module's owner.",
     "floor_45_worker_recruitment_agency",
     "registry_clerk"),
    ("wrk_kernel_report_courier",
     "Kernel Report Courier",
     "Carries sealed report packets from floors to the EQSB Kernel.",
     "floor_45_worker_recruitment_agency",
     "kernel_liaison"),
    ("wrk_skyscraper_lighting_engineer",
     "Skyscraper Lighting Engineer",
     "Tunes 3D dashboard lighting/glow per floor identity.",
     "floor_53_tower_command",
     "renderer"),
    ("wrk_lift_animation_engineer",
     "Lift Animation Engineer",
     "Tunes lift animation, dispatch, and packet visuals.",
     "floor_36_lift_operations",
     "renderer"),
    ("wrk_packet_flow_engineer",
     "Packet Flow Engineer",
     "Tunes packet flow visuals and sealed-packet rendering.",
     "floor_36_lift_operations",
     "renderer"),
    ("wrk_floor_label_designer",
     "Floor Label Designer",
     "Designs floor identity badges and labels for the 3D dashboard.",
     "floor_53_tower_command",
     "renderer"),
    ("wrk_3d_camera_operator",
     "3D Camera Operator",
     "Owns camera, scroll, and zoom feel for the 3D dashboard.",
     "floor_53_tower_command",
     "renderer"),

    # ── V3 employment expansion (data-driven skyscraper rebuild) ────────
    ("wrk_3d_dashboard_architect",
     "3D Dashboard Architect",
     "Designs the 3D cockpit layout and information hierarchy.",
     "floor_53_tower_command",
     "renderer"),
    ("wrk_worker_placement_coordinator",
     "Worker Placement Coordinator",
     "Maps canonical workers to their assigned floors for the renderer.",
     "floor_45_worker_recruitment_agency",
     "registry_clerk"),
    ("wrk_floor_interior_designer",
     "Floor Interior Designer",
     "Designs each floor's interior layout for the 3D inspection view.",
     "floor_53_tower_command",
     "renderer"),
    ("wrk_openclaw_route_animator",
     "OpenClaw Route Animator",
     "Animates OpenClaw's real route between supervised floors.",
     "floor_38_sandbox_operations",
     "renderer"),
    ("wrk_data_telemetry_mapper",
     "Data Telemetry Mapper",
     "Maps registry shapes to the dashboard live telemetry block.",
     "floor_53_tower_command",
     "telemetry"),
    ("wrk_frontend_health_inspector",
     "Frontend Health Inspector",
     "Watches dashboard HTTP status + static asset health.",
     "floor_53_tower_command",
     "ui_qa"),
    ("wrk_ui_stability_clerk",
     "UI Stability Clerk",
     "Catches frontend regressions and stale rendering.",
     "floor_53_tower_command",
     "ui_qa"),
    ("wrk_floor_activity_reporter",
     "Floor Activity Reporter",
     "Summarises per-floor activity from event ticker.",
     "floor_31_audit_ledger",
     "telemetry"),
    ("wrk_event_stream_courier",
     "Event Stream Courier",
     "Carries event packets from floors to the bottom ticker.",
     "floor_45_worker_recruitment_agency",
     "kernel_liaison"),
    ("wrk_dashboard_performance_monitor",
     "Dashboard Performance Monitor",
     "Records render FPS and asset load times advisory-only.",
     "floor_53_tower_command",
     "ui_qa"),
    ("wrk_animation_quality_auditor",
     "Animation Quality Auditor",
     "Flags any random or non-data-driven animation.",
     "floor_53_tower_command",
     "ui_qa"),
    ("wrk_live_data_integrity_checker",
     "Live Data Integrity Checker",
     "Validates that visible dashboard data matches registry source.",
     "floor_31_audit_ledger",
     "ledger_clerk"),
    ("wrk_guardian_visual_signal_engineer",
     "Guardian Visual Signal Engineer",
     "Renders Guardian verdicts as colored badges on relevant floors.",
     "floor_29_guardian_department",
     "renderer"),
    ("wrk_kernel_status_presenter",
     "Kernel Status Presenter",
     "Presents EQSB Kernel state on the cockpit header and Penthouse.",
     "floor_53_tower_command",
     "kernel_liaison"),
    ("wrk_trading_floor_visual_reporter",
     "Trading Floor Visual Reporter",
     "Summarises Floor 41/42/43 paper state for the right rail.",
     "floor_41_oanda_practice_trading",
     "trading_observer"),

    # Cover the prompt's listed-but-already-present roles by also adding
    # any V3 names that might otherwise be missed. (Idempotent — these
    # only get inserted if not already employed.)
    ("wrk_skyscraper_camera_operator",
     "Skyscraper Camera Operator",
     "Tunes pan/zoom/orbit camera behaviour for the 3D scene.",
     "floor_53_tower_command",
     "renderer"),

    # ── Hardware Systems Floor (floor 35) employees ────────────────────
    ("wrk_hardware_systems_manager",
     "Hardware Systems Manager",
     "Owns the Hardware Systems Floor; tracks every hardware report.",
     "floor_35_infrastructure_services_department",
     "hardware_systems_manager"),
    ("wrk_cpu_monitor", "CPU Monitor",
     "Reads CPU model / cores / threads / load average. Read-only.",
     "floor_35_infrastructure_services_department", "cpu_monitor"),
    ("wrk_gpu_monitor", "GPU Monitor",
     "Reads GPU model, NVIDIA driver, CUDA version, VRAM. Read-only.",
     "floor_35_infrastructure_services_department", "gpu_monitor"),
    ("wrk_memory_monitor", "Memory Monitor",
     "Reads RAM total/used/available, swap, memory pressure.",
     "floor_35_infrastructure_services_department", "memory_monitor"),
    ("wrk_storage_monitor", "Storage Monitor",
     "Reads disk usage for /, /vaults/nvme0, /vaults/ai. Read-only.",
     "floor_35_infrastructure_services_department", "storage_monitor"),
    ("wrk_process_monitor", "Process Monitor",
     "Tracks the dashboard server, Ollama, AirLLM venv presence.",
     "floor_35_infrastructure_services_department", "process_monitor"),
    ("wrk_port_monitor", "Port Monitor",
     "Lists local listening ports (ss -ltn). Read-only.",
     "floor_35_infrastructure_services_department", "port_monitor"),
    ("wrk_service_monitor", "Service Monitor",
     "Reads service presence (Ollama / dashboard pid file). Never modifies services.",
     "floor_35_infrastructure_services_department", "service_monitor"),
    ("wrk_performance_adviser", "Performance Adviser",
     "Builds advisory recommendations from memory pressure, VRAM headroom, disk space.",
     "floor_35_infrastructure_services_department", "performance_adviser"),
    ("wrk_resource_accountant", "Resource Accountant",
     "Tracks data/logs and data/backups size growth.",
     "floor_44_accounts_department", "resource_accountant"),
    ("wrk_kernel_hardware_liaison", "Kernel Hardware Liaison",
     "Routes hardware observatory state to the EQSB Kernel introspection.",
     "floor_35_infrastructure_services_department", "kernel_liaison"),
    ("wrk_code_observatory_liaison", "Code Observatory Liaison",
     "Routes code observatory state to the EQSB Kernel introspection.",
     "floor_35_infrastructure_services_department", "kernel_liaison"),

    # ── Accounts / PnL Department (floor 44) employees ─────────────────
    ("wrk_reward_accountant", "Reward Accountant",
     "Posts reward-point ledger entries from workforce scorecards.",
     "floor_44_accounts_department", "accounting"),
    ("wrk_loss_review_clerk", "Loss Review Clerk",
     "Routes losing paper trades into the lesson-review queue.",
     "floor_44_accounts_department", "loss_review"),
]


def _normalize_floor(name):
    if not name:
        return "unassigned"
    s = str(name).lower().replace(" ", "_")
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    if s.isdigit():
        s = "floor_" + s.zfill(2)
    if re.match(r"^\d", s):
        s = "floor_" + s
    return s


def _extract_workers_from(blob, source_name):
    """Pull a list of worker-like dicts from a heterogeneous registry."""
    out = []
    if isinstance(blob, list):
        seq = blob
    elif isinstance(blob, dict):
        seq = None
        for key in ("workers", "candidates", "slots", "items",
                     "registry", "data", "assigned"):
            v = blob.get(key)
            if isinstance(v, list):
                seq = v
                break
        if seq is None:
            return out
    else:
        return out

    for w in seq:
        if not isinstance(w, dict):
            # Skip pure strings — not enough info.
            continue
        wid = (w.get("id") or w.get("worker_id") or w.get("badge_id")
               or w.get("name") or w.get("display_name") or w.get("title"))
        if not wid:
            continue
        wid = str(wid).strip()
        out.append({
            "worker_id": wid,
            "display_name": w.get("display_name") or w.get("name") or wid,
            "role": (w.get("role") or w.get("role_description")
                     or w.get("category") or "unassigned"),
            "home_floor": _normalize_floor(
                w.get("home_floor") or w.get("floor")
                or w.get("assigned_floor") or w.get("department")
                or w.get("floor_id")),
            "current_floor": _normalize_floor(
                w.get("current_floor") or w.get("home_floor")
                or w.get("floor") or w.get("assigned_floor")),
            "source": source_name,
            "status_raw": (w.get("status") or w.get("state")
                            or w.get("active_state") or "registered"),
            "execution_enabled": bool(w.get("execution_enabled") or False),
            "sandbox_only": bool(w.get("sandbox_only") or True),
        })
    return out


SOURCE_FILES = [
    "workers.json",
    "recruitment_workers.json",
    "agent_worker_slots.json",
    "coding_worker_slots.json",
    "model_routing_worker_slots.json",
    "model_worker_slots.json",
    "sandbox_extended_workers.json",
    "worker_sandbox_registry.json",
    "openclaw_candidate_registry.json",
    "openclaw_sandbox_registry.json",
    "external_worker_candidates.json",
    "worker_candidate_registry.json",
    "worker_onboarding_queue.json",
    # V1 expansion roster (1000 new workers across 9 departments)
    "qsb_workforce_expansion_v1_roster.json",
]


def discover_workers():
    discovered = {}
    counts_by_source = {}
    for name in SOURCE_FILES:
        d = _load(name)
        rows = _extract_workers_from(d, name)
        counts_by_source[name] = len(rows)
        for r in rows:
            key = r["worker_id"].lower()
            if key not in discovered:
                discovered[key] = dict(r)
                discovered[key]["sources"] = [r["source"]]
            else:
                if r["source"] not in discovered[key]["sources"]:
                    discovered[key]["sources"].append(r["source"])
                # Prefer more specific floor info
                if (discovered[key]["home_floor"] in ("unassigned", "")
                        and r["home_floor"] not in ("unassigned", "")):
                    discovered[key]["home_floor"] = r["home_floor"]
                    discovered[key]["current_floor"] = r["current_floor"]
                if (not discovered[key].get("display_name")
                        and r.get("display_name")):
                    discovered[key]["display_name"] = r["display_name"]

    return list(discovered.values()), counts_by_source


def employ_new_workers(canonical):
    employed_ids = {c["worker_id"].lower() for c in canonical}
    new_records = []
    for wid, display, role_desc, home, role_cat in NEW_EMPLOYED_WORKERS:
        if wid.lower() in employed_ids:
            continue
        new_records.append({
            "worker_id": wid,
            "display_name": display,
            "role": role_cat,
            "role_description": role_desc,
            "home_floor": _normalize_floor(home),
            "current_floor": _normalize_floor(home),
            "source": "qsb_workers_reconciliation_v2_employment",
            "status_raw": "newly_employed",
            "execution_enabled": False,
            "sandbox_only": True,
            "sources": ["v2_phase_employment"],
        })
    return new_records


def canonicalize(all_records):
    """Tag every record with active/reporting/learning/paper-tasking
    permissions. Real execution stays false."""
    canonical = []
    for r in all_records:
        wid = r["worker_id"]
        is_new = (r["source"] == "qsb_workers_reconciliation_v2_employment"
                  or "v2_phase_employment" in r.get("sources", []))
        is_active = (
            is_new
            or (r["status_raw"] or "").lower() in ("active", "registered",
                                                     "employed", "healthy",
                                                     "running", "onboarded",
                                                     "newly_employed")
            or True  # default-on for reporting in V2
        )
        canonical.append({
            "worker_id":              wid,
            "display_name":           r.get("display_name") or wid,
            "role":                   r.get("role") or "unassigned",
            "role_description":       r.get("role_description"),
            "home_floor":             r.get("home_floor") or "unassigned",
            "current_floor":          r.get("current_floor") or "unassigned",
            "status":                 "active" if is_active else "registered",
            "reporting_enabled":      True,
            "learning_enabled":       True,
            "paper_tasking_enabled":  True,
            "real_execution_enabled": False,
            "sandbox_only":           True,
            "is_newly_employed":      is_new,
            "sources":                r.get("sources") or [r.get("source")],
        })
    return canonical


def reconcile():
    discovered, counts_by_source = discover_workers()
    new_records = employ_new_workers(discovered)
    canonical = canonicalize(discovered + new_records)

    by_floor = {}
    by_role = {}
    for c in canonical:
        by_floor[c["home_floor"]] = by_floor.get(c["home_floor"], 0) + 1
        by_role[c["role"]]        = by_role.get(c["role"],        0) + 1

    active = [c for c in canonical if c["status"] == "active"]
    reporting = [c for c in canonical if c["reporting_enabled"]]
    newly_employed = [c for c in canonical if c["is_newly_employed"]]

    canonical_payload = {
        "ok": True,
        "phase": "QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2",
        "kind": "qsb_canonical_workers",
        "generated_ts": _now(),
        "total_canonical_workers": len(canonical),
        "total_active_workers": len(active),
        "total_reporting_workers": len(reporting),
        "total_newly_employed_workers": len(newly_employed),
        "newly_employed_ids": [c["worker_id"] for c in newly_employed],
        "by_home_floor_counts": by_floor,
        "by_role_counts": by_role,
        "workers": canonical,
        "schema_field_set": ["worker_id", "display_name", "role",
                              "home_floor", "current_floor", "status",
                              "reporting_enabled", "learning_enabled",
                              "paper_tasking_enabled",
                              "real_execution_enabled"],
    }
    canonical_payload.update(_safety_envelope())
    P_CANONICAL.parent.mkdir(parents=True, exist_ok=True)
    P_CANONICAL.write_text(json.dumps(canonical_payload, indent=2),
                            encoding="utf-8")

    # Reconciliation report
    discovered_total = len(discovered)
    canonical_total = len(canonical)
    delta_employed = canonical_total - discovered_total
    mismatch_reason = (
        "Before V2 there was no canonical worker registry. Each subsystem "
        "(recruitment, sandbox, OpenClaw, model lanes, coding department, "
        "agent slots, onboarding queue, etc.) kept its own slate of "
        "workers. The dashboard read a few of these (notably workers.json + "
        "recruitment), while the Kernel read others (mostly its symbolic "
        "graph). The two counts diverged because no module deduplicated "
        "across the source registries, and several modules reported "
        "different totals depending on which subset they queried. V2 "
        "consolidates every source under qsb_canonical_workers.json and "
        "publishes one reconciliation count."
    )

    recon_payload = {
        "ok": True,
        "phase": "QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2",
        "kind": "qsb_worker_count_reconciliation",
        "generated_ts": _now(),
        "counts_by_source": counts_by_source,
        "sources_total_reported": sum(counts_by_source.values()),
        "total_discovered_unique_workers": discovered_total,
        "total_canonical_workers": canonical_total,
        "total_newly_employed_workers": len(newly_employed),
        "total_active_workers": len(active),
        "total_reporting_workers": len(reporting),
        "delta_pre_v2_to_post_v2": delta_employed,
        "mismatch_reason": mismatch_reason,
        "by_home_floor_counts": by_floor,
        "by_role_counts": by_role,
        "newly_employed_ids": [c["worker_id"] for c in newly_employed],
        "note": (
            "Counts are unique by worker_id (case-insensitive). The "
            "sources_total_reported is the SUM of per-source list lengths "
            "and intentionally double-counts workers that appeared in "
            "multiple registries — that double-counting is itself "
            "evidence of the pre-V2 mismatch."
        ),
    }
    recon_payload.update(_safety_envelope())
    P_RECON.write_text(json.dumps(recon_payload, indent=2), encoding="utf-8")

    new_hires_payload = {
        "ok": True,
        "phase": "QSB_DASHBOARD_DATA_DRIVEN_SKYSCRAPER_REBUILD_V2",
        "kind": "qsb_new_workers_employed",
        "generated_ts": _now(),
        "total_newly_employed_workers": len(newly_employed),
        "newly_employed_workers": [
            {
                "worker_id": c["worker_id"],
                "display_name": c["display_name"],
                "role": c["role"],
                "role_description": c.get("role_description"),
                "home_floor": c["home_floor"],
                "current_floor": c["current_floor"],
                "status": c["status"],
                "reporting_enabled": c["reporting_enabled"],
                "learning_enabled": c["learning_enabled"],
                "paper_tasking_enabled": c["paper_tasking_enabled"],
                "real_execution_enabled": c["real_execution_enabled"],
                "employment_phase": "QSB_DASHBOARD_DATA_DRIVEN_SKYSCRAPER_REBUILD_V2"
                if c["worker_id"] in {
                    "wrk_3d_dashboard_architect",
                    "wrk_worker_placement_coordinator",
                    "wrk_floor_interior_designer",
                    "wrk_openclaw_route_animator",
                    "wrk_data_telemetry_mapper",
                    "wrk_frontend_health_inspector",
                    "wrk_ui_stability_clerk",
                    "wrk_floor_activity_reporter",
                    "wrk_event_stream_courier",
                    "wrk_dashboard_performance_monitor",
                    "wrk_animation_quality_auditor",
                    "wrk_live_data_integrity_checker",
                    "wrk_guardian_visual_signal_engineer",
                    "wrk_kernel_status_presenter",
                    "wrk_trading_floor_visual_reporter",
                    "wrk_skyscraper_camera_operator",
                } else
                "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1"
                if c["worker_id"] in {
                    "wrk_hardware_systems_manager",
                    "wrk_cpu_monitor", "wrk_gpu_monitor",
                    "wrk_memory_monitor", "wrk_storage_monitor",
                    "wrk_process_monitor", "wrk_port_monitor",
                    "wrk_service_monitor", "wrk_performance_adviser",
                    "wrk_resource_accountant",
                    "wrk_kernel_hardware_liaison",
                    "wrk_code_observatory_liaison",
                    "wrk_reward_accountant", "wrk_loss_review_clerk",
                } else
                "QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2",
            }
            for c in newly_employed
        ],
    }
    new_hires_payload.update(_safety_envelope())
    P_NEW_HIRES.write_text(json.dumps(new_hires_payload, indent=2),
                            encoding="utf-8")

    L_RECON.parent.mkdir(parents=True, exist_ok=True)
    with L_RECON.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": _now(),
            "event": "reconcile",
            "total_canonical_workers": canonical_total,
            "total_newly_employed_workers": len(newly_employed),
        }) + "\n")

    return canonical_payload, recon_payload


def main():
    import sys
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    canonical, recon = reconcile()
    if cmd == "canonical":
        print(json.dumps(canonical, indent=2))
    elif cmd == "recon":
        print(json.dumps(recon, indent=2))
    else:
        print(json.dumps({
            "ok": True,
            "total_canonical_workers": canonical["total_canonical_workers"],
            "total_active_workers": canonical["total_active_workers"],
            "total_reporting_workers": canonical["total_reporting_workers"],
            "total_newly_employed_workers":
                canonical["total_newly_employed_workers"],
            "by_home_floor_counts": canonical["by_home_floor_counts"],
            "by_role_counts": canonical["by_role_counts"],
            "mismatch_reason": recon["mismatch_reason"],
            **_safety_envelope(),
        }, indent=2))


if __name__ == "__main__":
    main()
