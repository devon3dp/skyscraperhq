"""
QSB Tower V2 — OpenClaw Supervision Limb
Phase: QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2

Activates OpenClaw as an internal operations limb:
  * openclaw_visual_enabled              = True
  * openclaw_sandbox_enabled             = True
  * openclaw_trade_supervision_enabled   = True
  * openclaw_diagnostic_ticketing_enabled= True
  * openclaw_real_tool_execution_enabled = False  (immutable here)

OpenClaw inspects floors, paper/testnet trades, worker reports, and
generates diagnostic tickets routed to Kernel / Guardian / dashboard.
It NEVER places real-money orders, NEVER calls external APIs.
"""

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

P_OPENCLAW_STATE   = REG / "qsb_openclaw_state.json"
P_TRADE_REPORTS    = REG / "qsb_openclaw_trade_reports.json"
L_OPENCLAW_EVENTS  = LOGS / "qsb_openclaw_events.jsonl"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _safety_envelope():
    return {
        "openclaw_real_tool_execution_enabled": False,
        "openclaw_execution_enabled":           False,
        "execution_allowed":                    False,
        "active_local_only":                    True,
        "advisory_only":                        True,
        "real_money_live_trading_enabled":      False,
        "live_trading_enabled":                 False,
        "binance_live_trading_enabled":         False,
    }


def _append_event(record):
    L_OPENCLAW_EVENTS.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record.setdefault("ts", _now())
    record.setdefault("openclaw_real_tool_execution_enabled", False)
    with L_OPENCLAW_EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


# ── Allowed / blocked action surface ────────────────────────────────────

ALLOWED_PAPER_ACTIONS = [
    "inspect_floor_state",
    "inspect_open_paper_trades",
    "inspect_worker_reports",
    "open_paper_trade",
    "close_paper_trade",
    "update_pnl",
    "create_diagnostic_ticket",
    "report_to_kernel",
    "report_to_guardian",
    "report_to_dashboard",
    "summarize_worker_lessons",
]

BLOCKED_UNSAFE_ACTIONS = [
    "place_real_money_order",
    "place_binance_live_order",
    "place_oanda_live_order",
    "unlock_execution_gate",
    "bypass_guardian_verdict",
    "expose_api_key",
    "log_api_secret",
    "modify_lock_matrix",
    "execute_arbitrary_shell",
    "fetch_external_url_without_proxy",
    "promote_kernel_to_executing_logic",
]


# ── Diagnostic tickets ──────────────────────────────────────────────────

def _build_diagnostic_tickets():
    """Read existing registries and produce a small diagnostic ticket
    set OpenClaw is currently 'watching'. Tickets are advisory — no
    actions are taken."""
    tickets = []

    intro = _load(REG / "eqsb_kernel_introspection_latest.json")
    entropy = intro.get("entropy") or {}
    if (entropy.get("contradiction_score") or 0) > 0:
        tickets.append({
            "ticket_id": "tkt_eqsb_contradiction_score",
            "severity": "info",
            "title": "EQSB contradiction_score is non-zero",
            "evidence": "entropy.contradiction_score=" + str(entropy.get("contradiction_score")),
            "advised_action": "review eqsb_contradiction_report.json",
            "routing": ["kernel", "guardian", "dashboard"],
        })

    audit = _load(REG / "eqsb_kernel_major_audit.json")
    if int(audit.get("missing_count") or 0) > 0:
        tickets.append({
            "ticket_id": "tkt_eqsb_missing_registries",
            "severity": "warning",
            "title": "EQSB has missing major-phase registries",
            "evidence": "missing_count=" + str(audit.get("missing_count")),
            "advised_action": "scripts/eqsb_systems_check.sh",
            "routing": ["kernel", "dashboard"],
        })

    floor41 = _load(REG / "floor41_paper_ledger.json")
    if (floor41.get("entry_count") or 0) > 0:
        tickets.append({
            "ticket_id": "tkt_floor41_paper_ledger_active",
            "severity": "info",
            "title": "Floor 41 paper ledger has entries",
            "evidence": "entry_count=" + str(floor41.get("entry_count")),
            "advised_action": "inspect via /api/openclaw/trade_reports",
            "routing": ["dashboard"],
        })

    binance = _load(REG / "binance_paper_strategy_latest.json")
    if binance.get("mode") == "binance_paper_strategy_lab":
        tickets.append({
            "ticket_id": "tkt_binance_paper_lab_active",
            "severity": "info",
            "title": "Binance paper strategy lab is observing testnet",
            "evidence": "mode=" + str(binance.get("mode")),
            "advised_action": "watch open paper-trade count vs max=20",
            "routing": ["dashboard"],
        })

    return tickets


# ── OpenClaw state ──────────────────────────────────────────────────────

def build_openclaw_state():
    snapshot = _load(REG / "openclaw_sandbox_latest.json") or {}
    sandbox_workers = (
        snapshot.get("workers")
        or _load(REG / "openclaw_sandbox_registry.json").get("workers")
        or []
    )

    tickets = _build_diagnostic_tickets()

    # Open paper trade visibility — read from our paper trading registry
    open_trades = _load(REG / "qsb_open_paper_trades.json") or {}
    paper_policy = _load(REG / "qsb_paper_trading_policy.json") or {}

    state = {
        "ok": True,
        "phase": "QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2",
        "kind": "qsb_openclaw_state",
        "generated_ts": _now(),
        "status": "active",
        "openclaw_visual_enabled": True,
        "openclaw_sandbox_enabled": True,
        "openclaw_trade_supervision_enabled": True,
        "openclaw_diagnostic_ticketing_enabled": True,
        # Hard-coded immutable.
        "openclaw_real_tool_execution_enabled": False,
        "limb_role": "internal_operations_supervision",
        "responsibilities": [
            "inspect trading floors",
            "inspect open paper/testnet trades",
            "inspect worker reports",
            "create diagnostic tickets",
            "report to Kernel / Guardian / dashboard",
            "display allowed paper/testnet actions",
            "display blocked unsafe actions",
        ],
        "allowed_paper_actions": ALLOWED_PAPER_ACTIONS,
        "blocked_unsafe_actions": BLOCKED_UNSAFE_ACTIONS,
        "supervised_floors": [
            "floor_30_permissions_risk",
            "floor_31_audit_ledger",
            "floor_37_simulation_labs",
            "floor_38_sandbox_operations",
            "floor_41_oanda_practice_trading",
            "floor_42_binance_trading_floor",
            "floor_43_stock_exchange_floor",
            "floor_45_worker_recruitment_agency",
            "floor_53_tower_command",
        ],
        "sandbox_workers": sandbox_workers,
        "sandbox_worker_count": len(sandbox_workers),
        "diagnostic_tickets": tickets,
        "diagnostic_ticket_count": len(tickets),
        "current_open_trade_count": int(open_trades.get("open_trade_count") or 0),
        "max_open_trades": int(paper_policy.get("max_open_trades") or 20),
        "reports_routed_to": ["kernel", "guardian", "dashboard"],
    }
    state.update(_safety_envelope())
    P_OPENCLAW_STATE.parent.mkdir(parents=True, exist_ok=True)
    P_OPENCLAW_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    _append_event({
        "event": "build_openclaw_state",
        "ticket_count": len(tickets),
        "sandbox_worker_count": len(sandbox_workers),
    })
    return state


def build_trade_reports():
    """Compose OpenClaw's view of the trading floors: open paper trades,
    recent paper signals, allowed/blocked actions per floor. Read-only."""
    open_trades = _load(REG / "qsb_open_paper_trades.json") or {}
    paper_policy = _load(REG / "qsb_paper_trading_policy.json") or {}
    binance = _load(REG / "binance_paper_strategy_latest.json") or {}
    oanda = _load(REG / "oanda_paper_strategy_latest.json") or {}
    floor41 = _load(REG / "floor41_paper_ledger.json") or {}
    learning = _load(REG / "qsb_trade_learning.json") or {}

    reports = {
        "ok": True,
        "phase": "QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2",
        "kind": "qsb_openclaw_trade_reports",
        "generated_ts": _now(),
        "max_open_trades": int(paper_policy.get("max_open_trades") or 20),
        "current_open_trade_count": int(open_trades.get("open_trade_count") or 0),
        "remaining_trade_slots": (
            int(paper_policy.get("max_open_trades") or 20) -
            int(open_trades.get("open_trade_count") or 0)
        ),
        "open_trades_preview": (open_trades.get("trades") or [])[:20],
        "binance_paper_lab": {
            "mode": binance.get("mode"),
            "environment": binance.get("environment"),
            "signal_counts": binance.get("signal_counts"),
            "default_symbols": binance.get("default_symbols"),
            "ts": binance.get("ts"),
        },
        "oanda_paper_lab": {
            "mode": oanda.get("mode"),
            "ts": oanda.get("ts"),
        },
        "floor41_ledger_summary": {
            "entry_count": floor41.get("entry_count"),
            "latest_entry_count": floor41.get("latest_entry_count"),
            "updated_ts": floor41.get("updated_ts"),
        },
        "lessons_learned_total": int(learning.get("lesson_count") or 0),
        "recent_lessons": (learning.get("lessons") or [])[-10:],
        "allowed_paper_actions": ALLOWED_PAPER_ACTIONS,
        "blocked_unsafe_actions": BLOCKED_UNSAFE_ACTIONS,
    }
    reports.update(_safety_envelope())
    P_TRADE_REPORTS.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    _append_event({
        "event": "build_trade_reports",
        "current_open_trade_count": reports["current_open_trade_count"],
        "max_open_trades": reports["max_open_trades"],
    })
    return reports


def build_all():
    s = build_openclaw_state()
    r = build_trade_reports()
    return {"state_kind": s["kind"], "reports_kind": r["kind"], **_safety_envelope()}


def main():
    import sys
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    if cmd == "state":
        print(json.dumps(build_openclaw_state(), indent=2))
    elif cmd == "reports":
        print(json.dumps(build_trade_reports(), indent=2))
    else:
        build_openclaw_state()
        build_trade_reports()
        print(json.dumps({"ok": True, "openclaw_supervision": "active",
                          "openclaw_real_tool_execution_enabled": False},
                         indent=2))


if __name__ == "__main__":
    main()
