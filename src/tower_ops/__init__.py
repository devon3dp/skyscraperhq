"""QSB Tower V1.3 — Tower Operations Layer V1.

Phase: QSB_TOWER_OPERATIONS_V1

Real organization layer for the QSB skyscraper:
  - Real local workers with persistent state + lazy heartbeats
  - Floor managers / zone managers / Tower Operations Manager
  - Overseers
  - Floor → Zone → Tower → Kernel reporting chain
  - Maintenance / Security / IT / Research / Colonel Concierge / Trading Telemetry

This layer is strictly READ-ONLY / ADVISORY. No execution unlocks. Every
published record stamps the safety contract from `safety_contract.LOCKED_FALSE`
regardless of caller input.
"""

from .safety_contract     import LOCKED_FALSE, NEW_LOCK_KEYS, all_lock_keys
from .org_schema          import ZONES, FLOOR_TO_DEPARTMENT, MGR_TYPES, DEPARTMENT_FLOORS
from .worker_registry     import status as worker_status, workers as worker_list
from .management_chain    import status as manager_status, all_managers
from .overseer_registry   import status as overseer_status, run_check as overseer_run
from .reporting           import tower_report, floor_reports, zone_reports
from .maintenance         import status as maintenance_status, checks as maintenance_checks, run_check as maintenance_run
from .security            import status as security_status, incidents as security_incidents
from .it_ops              import status as it_status, ports as it_ports, sidecars as it_sidecars, connectivity as it_connectivity, routes as it_routes
from .research_facility   import status as research_status, tasks as research_tasks
from .colonel_concierge   import status as colonel_status, butler_briefing, concierge_summary
from .trading_telemetry   import (
    oanda_account, oanda_positions, oanda_trades, oanda_pnl,
    binance_account, binance_positions, binance_orders, binance_pnl,
    stocks_account, stocks_positions, stocks_pnl,
)
# V2 additions
from .identity_badges    import status as badge_status, all_badges
from .access_control     import status as access_status, check_access, ACCESS_LEVELS
from .worker_directory   import directory as worker_directory, by_floor as workers_by_floor_dir, by_badge as worker_by_badge
from .accounts_department import (status as accounts_status, floor_accountants_list,
                                    floor_summary as accounts_floor_summary,
                                    trading_summary as accounts_trading_summary,
                                    paper_ledger_summary, not_configured as accounts_not_configured)
from .quantum_floor       import (status as quantum_status, workers as quantum_workers,
                                    reports as quantum_reports, create_research_task as quantum_research_task)
from .model_ops           import (status as models_status, lanes as models_lanes,
                                    local as models_local, airllm as models_airllm,
                                    router as models_router, manual_kernel_query,
                                    manual_airllm_advisory)
from .lifts               import status as lifts_status, routes as lifts_routes
from .tower_tick          import tick as tower_tick, live_state as renderer_state
from .missing             import report as missing_report
from .speech_ops          import status as speech_status, diagnostics as speech_diagnostics
from .chat_diagnostics    import diagnostics as kernel_chat_diagnostics
# V3 additions
from .curriculum_registry  import courses as training_courses
from .certification_engine import (status as cert_status, certifications,
                                     enrol as training_enrol,
                                     complete_lesson as training_complete_lesson,
                                     certify_worker, revoke_certification)
from .training_academy     import status as training_status, trained_workers
from .tower_audit          import (run_full as audit_run_full, latest as audit_latest,
                                     history as audit_history, status as audit_status,
                                     gaps as audit_gaps)
from .next_steps           import report as audit_next_steps
# V4 — Pro Dashboard + OANDA Practice Trading + OpenClaw Practice
from .oanda_practice_trading import (account as oanda_practice_account,
                                       pricing as oanda_practice_pricing,
                                       open_positions as oanda_open_positions_practice,
                                       open_trades   as oanda_open_trades_practice,
                                       transactions  as oanda_practice_transactions,
                                       practice_ledger,
                                       practice_preflight, order_guard,
                                       practice_order_preview,
                                       place_practice_order,
                                       close_practice_trade,
                                       kill_switch as oanda_practice_kill_switch,
                                       GUARDS as OANDA_PRACTICE_GUARDS)
from .openclaw_practice     import (status as openclaw_practice_status,
                                      proposals as openclaw_practice_proposals,
                                      practice_stream as openclaw_practice_stream,
                                      create_practice_proposal,
                                      submit_to_oanda_practice_preview)
from .dashboard_pro         import (pro_state, renderer_v4_state, renderer_v4_options,
                                      floors_live, floors_activity, workers_live,
                                      workers_routes, packets_live, events_live,
                                      departments_live, accounts_live, models_live,
                                      kernel_live, oanda_practice_summary)


def tower_ops_summary():
    """Aggregate summary used by /api/unified.tower_ops."""
    ws = worker_status()
    ms = manager_status()
    os_ = overseer_status()
    return {
        "phase": "QSB_TOWER_OPERATIONS_V1",
        "departments": list(DEPARTMENT_FLOORS.keys()),
        "worker_count":   ws.get("total_workers", 0),
        "manager_count":  ms.get("total_managers", 0),
        "overseer_count": os_.get("total_overseers", 0),
        "active_advisory":          ws.get("active_advisory", 0),
        "active_read_only":         ws.get("active_read_only", 0),
        "ready_for_openclaw_review":ws.get("ready_for_openclaw_review", 0),
        "openclaw_ready_count":     ws.get("openclaw_ready_count", 0),
        "maintenance_status":  maintenance_status().get("overall_status"),
        "security_status":     security_status().get("overall_status"),
        "it_status":           it_status().get("overall_status"),
        "research_status":     research_status().get("overall_status"),
        "recruitment_status":  ws.get("agency_status", "live"),
        "colonel_concierge_status": colonel_status().get("concierge_status"),
        "colonel_butler_status":    colonel_status().get("butler_status"),
        "trading_telemetry_status": "read_only_only_if_configured",
        "tower_operations_manager": ms.get("tower_operations_manager"),
        "kernel_liaison_manager":    ms.get("kernel_liaison_manager"),
        "reports_to_kernel":         ms.get("reports_to_kernel"),
        **LOCKED_FALSE,
        "execution_allowed": False,
        "advisory_only": True,
        "paper_only": True,
        "read_only": True,
        "not_financial_advice": True,
    }
