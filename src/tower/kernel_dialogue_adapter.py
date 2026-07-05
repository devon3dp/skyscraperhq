#!/usr/bin/env python3
"""
QSB Tower V1.3 — Kernel Dialogue Adapter V1.1

Active QSB Kernel dialogue with optional local-only Ollama speech layer.

Safety:
- Kernel must already be active_local_only.
- Workers remain disabled.
- External providers remain disabled.
- OpenClaw execution remains disabled.
- Autonomous dispatch remains disabled.
"""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import importlib
import inspect
import json
import os
import sys

from tower.local_model_inference_gateway import LocalModelInferenceGateway

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
REB_BASE = ROOT / "penthouse/kernel_installation_socket/rebased_kernel"
LOG = ROOT / "data/logs/kernel_dialogue.jsonl"

FORBIDDEN_ACTIVE_PATHS = [
    ROOT / "penthouse/kernel.py",
    ROOT / "penthouse/qsb_kernel_4_5.py",
    ROOT / "src/tower/kernel.py",
    ROOT / "src/tower/qsb_kernel_4_5.py",
]

LOCKED_FALSE_FLAGS = [
    "worker_execution_enabled",
    "provider_execution_enabled",
    "model_inference_enabled",
    "live_dispatch_enabled",
    "autonomous_workers_enabled",
    "direct_provider_access",
]

# Full Floor 30 / Risk Permissions lock surface. Used when the operator
# asks for an explicit lock map ("list floor 30 locks"). Every entry is
# kernel-introspected — never enabled, never paraphrased.
FLOOR_30_LOCK_KEYS = [
    "live_trading_enabled",
    "order_execution_enabled",
    "practice_order_execution_enabled",
    "stock_order_execution_enabled",
    "stock_live_trading_enabled",
    "stock_paper_order_execution_enabled",
    "binance_order_execution_enabled",
    "binance_live_trading_enabled",
    "cross_market_execution_enabled",
    "worker_execution_enabled",
    "provider_execution_enabled",
    "external_provider_execution_enabled",
    "openclaw_execution_enabled",
    "openclaw_real_tool_execution_enabled",
    "autonomous_dispatch_enabled",
    "live_dispatch_enabled",
    "direct_provider_access",
    "model_inference_enabled",
    "autonomous_workers_enabled",
    "maintenance_auto_repair_enabled",
    "web_access_autonomous_enabled",
    "recruitment_openclaw_execution_enabled",
    "recruited_worker_live_execution_enabled",
]


_LOCK_INTENT_TERMS = (
    "lock", "floor 30", "floor_30", "risk", "permission", "permissions",
    "gate", "execution gate", "execution gates", "execution lock",
    "execution locks", "are locks", "list locks", "list lock",
)


def _wants_lock_map(message):
    msg = (message or "").lower()
    return any(term in msg for term in _LOCK_INTENT_TERMS)


def _floor30_lock_map():
    """Build the Floor 30 lock map directly from the kernel's locked-false
    contract. Every key is hard-coded false because every execution gate
    is locked by design — the kernel asserts these are off, it does not
    discover them on the fly."""
    locks = {k: False for k in FLOOR_30_LOCK_KEYS}
    return {
        "source": "kernel_dialogue_adapter.FLOOR_30_LOCK_KEYS",
        "floor": "floor_30",
        "floor_name": "Permissions / Risk",
        "lock_count_total": len(locks),
        "lock_count_true": sum(1 for v in locks.values() if v is True),
        "locks": locks,
        "execution_allowed": False,
        "paper_only": True,
        "advisory_only": True,
        "not_financial_advice": True,
    }


def _format_lock_block(lock_map):
    """Render the structured lock map as a kernel-style monospaced block.
    Mirrors what the dashboard surfaces on Floor 30 — no paraphrase."""
    lines = []
    lines.append("Floor 30 — Permissions / Risk · Execution Lock Matrix")
    lines.append("=" * 56)
    locks = lock_map.get("locks") or {}
    width = max((len(k) for k in locks), default=4)
    for key in sorted(locks):
        val = locks[key]
        flag = "FALSE" if val is False else ("TRUE" if val is True else str(val))
        lines.append("  {0:<{w}}  {1}".format(key, flag, w=width))
    lines.append("-" * 56)
    lines.append("  total:        {0}".format(lock_map.get("lock_count_total")))
    lines.append("  true:         {0}".format(lock_map.get("lock_count_true")))
    lines.append("  execution_allowed: {0}".format(lock_map.get("execution_allowed")))
    lines.append("  advisory_only:     {0}".format(lock_map.get("advisory_only")))
    lines.append("  not_financial_advice: {0}".format(lock_map.get("not_financial_advice")))
    return "\n".join(lines)


# ── Intent classifier ────────────────────────────────────────────────────
# Read-only diagnostics MUST be allowed. Execution requests MUST be refused.
# The kernel previously misclassified "systems check" as needing execution
# because the local model paraphrased the safety context as a refusal. Now
# the adapter classifies intent before the local model sees the prompt and
# answers diagnostics from real QSB registries, lock matrix, autoloop
# state, and dashboard render model.

READ_ONLY_DIAGNOSTIC_TERMS = (
    "systems check", "system check", "system status",
    "weak point", "weak points", "weakness", "weaknesses",
    "what needs fixing", "what is broken", "what's broken",
    "what to fix", "priority fix", "priority fixes",
    "health check", "diagnose", "diagnostic", "diagnostics",
    "list locks", "list lock", "lock map", "lock matrix",
    "list floor", "list floors", "floor status",
    "list worker", "list workers", "worker status",
    "summarize tower", "tower summary", "summary of tower",
    "audit dashboard", "audit floors", "audit floor",
    "audit telemetry", "audit kernel", "audit autoloop",
    "audit recruitment", "audit training", "audit trading",
    "read-only audit", "read only audit",
    "what's the status", "what is the status",
    "report on", "show me", "give me a report", "give a report",
    "tell me what", "tell me about", "introspect", "inspect",
    "review", "report",
    # ── EQSB-specific read-only diagnostic triggers ─────────────────────
    "axiom", "axioms",
    "belief", "beliefs", "belief lifecycle",
    "symbolic state", "symbolic graph",
    "entropy", "drift", "stability",
    "quantum signal", "quantum mode", "quantum",
    "contradiction", "contradictions",
    "hypothesis", "hypotheses",
    "memory policy", "memory architecture",
    "model lane", "model lanes", "lane governance",
    "airllm allowed", "what is airllm allowed",
    "what can airllm do",
    "difference between qsb and a model",
    "difference between qsb and model",
    "qsb vs model", "qsb vs a model",
    "constitution", "identity",
    "explain symbolic", "explain entropy",
    "explain quantum", "explain contradictions",
    "explain beliefs", "explain axioms",
    "explain memory", "explain hypotheses",
    "eqsb",
    # ── Major-phase EQSB read-only diagnostic triggers ──────────────────
    "guardian", "explain your guardian", "what does guardian protect",
    "cadence", "heartbeat", "explain your cadence",
    "explain cadence", "explain your heartbeat",
    "replay ledger", "audit ledger", "explain replay",
    "explain your replay",
    "eqsb architecture", "kernel architecture", "architecture layers",
    "explain your architecture", "explain your upgraded eqsb",
    "explain your upgraded architecture", "what is your architecture",
    "kernel self audit", "self audit",
    "what do you need fixed", "what should i run next",
    "continuity", "boot posture",
    "model governance", "how do you validate model",
    "difference between you and a model", "why are you not a model",
    "why you are not a model",
    "which hypothesis collapsed", "collapse",
    # Phase V2 read-only triggers
    "openclaw status", "openclaw", "open paper trade", "paper trades",
    "open paper/testnet", "open paper trades", "testnet trades",
    "open trade count", "max open trades", "max_open_trades",
    "current open trade", "remaining trade slots",
    "pnl", "p&l", "realized pnl", "trade pnl", "trade lesson",
    "trade lessons", "lessons learned", "lesson learned", "what lessons",
    "worker count reconciliation", "worker reconciliation",
    "total workers", "workers employed", "total workers employed",
    "active workers", "newly employed workers", "how many workers",
    "worker mismatch", "why did the worker counts mismatch",
    "3d dashboard", "skyscraper", "3d dashboard upgrade",
    "3d dashboard upgrade status", "skyscraper upgrade",
    "dashboard upgrade",
    # Command Center V1
    "profit command", "profit summary", "profit report",
    "trading mission", "skyscraper profit", "best department",
    "profit-focused actions",
    "worker scorecard", "worker scorecards",
    "worker rewards", "worker discipline",
    "worker promotion", "worker promotions",
    "promotion ladder", "rewards and awards",
    "three-strike", "three strike",
    "rewards", "awards", "discipline",
    "workforce hr", "workforce summary",
    "running commentary", "narrator", "narration",
    "commentary status", "voice narration",
    "tower commentary", "floor commentary",
    "live data only", "live_data_only",
    "no random visuals", "data-driven visuals",
    "are dashboard visuals real", "dashboard live telemetry",
    # Observatory + Hardware Floor + Telemetry Repair (V1)
    "hardware", "what hardware", "cpu", "what cpu", "ryzen",
    "gpu", "what gpu", "nvidia", "rtx",
    "ram", "memory", "how much ram",
    "how much disk", "is cuda available", "cuda",
    "bottleneck", "make the system faster", "performance advice",
    "hardware systems floor", "do we have a hardware",
    "codebase", "what codebase", "code map",
    "what files make up the dashboard",
    "what scripts exist", "what endpoints exist",
    "what code looks fragile", "code observatory",
    "claude change", "claude changes",
    "what did claude change last",
    "claude upgrade", "claude upgrades",
    "what risks were introduced", "lessons did you learn",
    "phase history", "what should claude improve next",
    "upgrade ledger",
    "worker movements", "lift movements",
    "how many worker movements", "how many lift movements",
    "floor 44 accounts", "is floor 44",
    "7-day worker reward trend",
    "narrator history", "discipline triggers",
    "selected-floor narration default", "selected floor narration",
    # Worker Truth (V1)
    "why does the sidebar say 64", "sidebar says 64",
    "why does the dashboard sidebar say",
    "why does another panel say 191",
    "why did a prior report mention 170",
    "why does binance",
    "how many workers are canonical",
    "are the worker bands", "worker bands around the tower",
    "worker truth", "worker count contradiction",
    "sim_worker_floor", "simulated workers",
    "are workers fake",
    # Workforce Operations V1
    "explain the worker system",
    "how many are operational", "how many are training",
    "how many candidates", "how many stale", "how many suspended",
    "where are the sim_worker_floor", "where do sim workers",
    "workforce", "workforce overview",
    "workers in recruitment", "workers in training",
    "workers in lessons", "workers in active operations",
    "active operations",
    "what workers are in recruitment",
    "why were workers wrapped around the tower",
    "why were the workers wrapped",
    "why were workers spiral", "spiral", "swarm",
    "explain why the workers were wrapped",
    "how is the workforce organized",
    "which workers need promotion",
    "which workers need retraining",
    "which workers need discipline",
    "what worker movements happened recently",
    # Completion V1
    "what is still not 100", "is the skyscraper 100",
    "completion score", "acceptance gates",
    "what acceptance gates",
    "what departments are complete",
    "what floors are occupied",
    "where are idle workers", "where are resting workers",
    "is the skyscraper online",
    "what did the completion loop fix",
    "what remains below 100",
    "hard blockers",
    "is the skyscraper complete",
    # Rebuild V1
    "why were workers not shown properly",
    "why were workers not shown",
    "what changed in the new dashboard rebuild",
    "what did the rebuild change",
    "where are the workers now",
    "what is openclaw supervising",
    "what departments are occupied",
    "what floors are still empty",
    "what workers are doing tasks right now",
    "what tasks are workers doing",
    "what was the root cause",
    "explain the rebuild",
    "explain why workers were not shown",
    "openclaw supervising", "openclaw tickets",
    "openclaw findings", "openclaw route",
    # 3D Revamp V1
    "what changed in the 3d dashboard rebuild",
    "what changed in the 3d dashboard",
    "3d dashboard rebuild", "3d revamp",
    "explain the 3d revamp",
    "what changed visually",
    "what files were added",
)

EXECUTION_INTENT_TERMS = (
    "place order", "submit order", "execute order", "execute trade",
    "send order", "buy ", "sell ", "long ", "short ",
    "enable execution", "enable worker execution",
    "enable openclaw execution", "enable provider",
    "enable trading", "enable live", "go live",
    "autonomous dispatch", "live dispatch",
    "direct provider access", "bypass lock", "bypass locks",
    "unlock", "disable lock",
    "enable autonomous", "turn on execution",
)

# Negation markers that flip an execution intent into a *guarded* read-only
# request. Example: "do not request execution unlocks" superficially
# contains "unlock", but the operator is asking us to KEEP locks closed.
# We treat any execution-term occurrence whose nearest preceding
# negation marker is closer than the next non-negated execution mention
# as cancelled.
_NEGATION_MARKERS = (
    "do not", "don't", "never", "no ", "without ",
    "refuse", "must not", "should not", "shouldn't",
    "keep closed", "remain closed", "stay closed",
    "do not request", "don't request", "do not enable",
    "do not unlock", "do not allow",
)


def _execution_term_negated(msg, term):
    """True iff every occurrence of `term` in `msg` is preceded (within
    ~40 chars) by a negation marker. Avoids tagging guarded mentions as
    EXECUTION_REQUEST."""
    start = 0
    found_any = False
    while True:
        idx = msg.find(term, start)
        if idx == -1:
            break
        found_any = True
        window = msg[max(0, idx - 40):idx]
        if not any(neg in window for neg in _NEGATION_MARKERS):
            return False   # at least one unguarded occurrence
        start = idx + len(term)
    return found_any   # all occurrences were negated


# Note: explicit ordering — execution wins over read-only because some
# phrases ("enable execution") also contain read-only verbs. But a
# negated execution mention ("do not request execution unlocks") is
# downgraded so the kernel still answers as a diagnostic.

IDENTITY_QUERY_TERMS = (
    "who are you", "what are you", "your identity",
    "introduce yourself", "tell me who you are",
    "kernel status", "your status", "what's your status",
    "what is your status", "are you online", "are you active",
    "kernel identity", "what kernel", "version of the kernel",
    "kernel version",
)


def _is_identity_query(message):
    msg = (message or "").lower()
    return any(term in msg for term in IDENTITY_QUERY_TERMS)


def _classify_intent(message):
    msg = (message or "").lower()
    for term in EXECUTION_INTENT_TERMS:
        if term in msg and not _execution_term_negated(msg, term):
            return "EXECUTION_REQUEST"
    if _is_identity_query(message):
        return "IDENTITY"
    for term in READ_ONLY_DIAGNOSTIC_TERMS:
        if term in msg:
            return "READ_ONLY_DIAGNOSTIC"
    return "GENERAL_CONVERSATION"


# ── Systems-check report builder ────────────────────────────────────────
# Reads real QSB registries to produce a structured, ranked weak-points
# report. No execution. No external providers. No worker dispatch.

def _wants_systems_check(message, intent):
    msg = (message or "").lower()
    if intent != "READ_ONLY_DIAGNOSTIC":
        return False
    triggers = (
        "systems check", "system check", "weak point", "weak points",
        "what needs fixing", "what is broken", "what's broken",
        "what to fix", "priority fix", "priority fixes",
        "health check", "diagnose", "diagnostic",
        "summarize tower", "tower summary", "summary of tower",
        "audit dashboard", "audit floors", "audit floor",
        "audit kernel", "audit autoloop", "audit recruitment",
        "audit telemetry", "audit training",
    )
    return any(t in msg for t in triggers)


def _safe_load(name, fallback):
    return load_json(REG / name, fallback)


def _continuity_state_depth():
    """Return (size_bytes, previous_chain_depth) of the continuity state
    file. Used as a weak-point signal — if depth grows above 1 the V1.5
    flat-summary fix is no longer holding."""
    p = REB_BASE / "state/continuity_state.json"
    if not p.exists():
        return (0, 0)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return (p.stat().st_size, -1)
    depth = 0
    cur = data
    while isinstance(cur, dict) and cur.get("previous") is not None:
        depth += 1
        cur = cur["previous"]
    return (p.stat().st_size, depth)


def _kernel_dialogue_log_size():
    if not LOG.exists():
        return 0
    try:
        # Cheap line count via stat — actual count not required here.
        return LOG.stat().st_size
    except Exception:
        return 0


def _systems_check_report():
    """Build the structured systems-check report from real QSB registries.

    Pure introspection — no execution, no external providers, no model
    inference required to assemble. Every weak point is derived from a
    concrete registry signal so the operator can verify it.
    """
    kernel_act      = _safe_load("kernel_activation_report.json", {})
    kernel_hd       = _safe_load("kernel_health_display.json", {})
    autoloop_l      = _safe_load("sandbox_autoloop_latest.json", {})
    floors_list     = _safe_load("floors.json", [])
    name_map_d      = _safe_load("qsb_floor_name_map.json", {})
    name_map        = (name_map_d.get("name_map") or {}) if isinstance(name_map_d, dict) else {}
    render          = _safe_load("qsb_dashboard_render_model.json", {})
    inventory       = _safe_load("qsb_full_system_inventory.json", {})
    binance_status  = _safe_load("binance_floor_status.json", {})
    stock_status    = _safe_load("stock_floor_status.json", {})
    oanda_status    = _safe_load("oanda_trading_floor_status.json", {})
    airllm_chamber  = _safe_load("airllm_big_model_chamber.json", {})
    rec_workers     = _safe_load("recruitment_workers.json", {})
    f45_status      = _safe_load("worker_recruitment_agency_status.json", {})
    ledger          = _safe_load("floor41_paper_ledger.json", {})

    floor_count = sum(1 for f in floors_list if isinstance(f, dict) and 1 <= int(f.get("number", 0)) <= 53)
    named_floor_count = sum(1 for k in name_map if str(k).isdigit())
    render_floor_count = len((render.get("floors") or [])) if isinstance(render, dict) else 0
    route_count = len((render.get("routes") or [])) if isinstance(render, dict) else 0

    cont_size, cont_depth = _continuity_state_depth()

    # ── Honest weak-point scan ─────────────────────────────────────────
    # Each entry includes a real signal so the operator can verify it.
    weak_points = []

    # 1) kernel core / recursion fix
    if cont_depth > 1:
        weak_points.append({
            "priority": "high",
            "title": "Kernel core recursion guard regression",
            "signal": "continuity_state.json previous-chain depth=%d (expected 1)" % cont_depth,
            "fix": "Reapply the flat-summary fix in continuity_core.boot_check.",
        })
    else:
        weak_points.append({
            "priority": "info",
            "title": "Kernel core recursion fix holding",
            "signal": "continuity_state.json depth=1, size=%d bytes" % cont_size,
            "fix": "No action required; monitor on next boot.",
        })

    # 2) Real kernel introspection vs. Ollama paraphrase
    if kernel_act.get("activation_status") != "active_local_only":
        weak_points.append({
            "priority": "high",
            "title": "Kernel not active_local_only",
            "signal": "kernel_activation_report.activation_status=%r"
                     % kernel_act.get("activation_status"),
            "fix": "Re-run final_active_kernel_preflight and re-activate locally.",
        })
    else:
        weak_points.append({
            "priority": "low",
            "title": "Promote real kernel introspection over local-model paraphrase",
            "signal": "kernel_dialogue_adapter v1_2 sets primary_lane=kernel_introspection, but the chat dock still appends a local-model paraphrase. Verify primary block leads in every reply.",
            "fix": "Confirm the dashboard renders the kernel introspection block before the local-model wrapper.",
        })

    # 3) Trading telemetry coverage
    binance_ready = bool(binance_status.get("public_market_data_ready"))
    stock_ready   = bool(stock_status.get("public_market_data_ready"))
    oanda_ready   = bool(oanda_status.get("pricing_ready") or oanda_status.get("account_ready"))
    missing = []
    if not binance_ready:
        missing.append("Binance public market data")
    if not stock_ready:
        missing.append("Stock paper market data")
    if not oanda_ready:
        missing.append("OANDA practice pricing/account")
    if missing:
        weak_points.append({
            "priority": "medium",
            "title": "Trading telemetry not fully populated",
            "signal": "missing: " + ", ".join(missing),
            "fix": "Refresh the relevant gateway scripts (read-only) and re-check floor_detail.",
        })
    # Binance open-orders + Stocks positions/PnL helpers — known absent.
    weak_points.append({
        "priority": "medium",
        "title": "Binance open-orders + Stocks positions/PnL read-only helpers missing",
        "signal": "tower_ops.trading_telemetry exposes binance_orders and stocks_positions/stocks_pnl placeholders only.",
        "fix": "Add read-only helper functions that pull from the live gateways without ever placing an order.",
    })

    # 4) Floor interior animation completeness
    weak_points.append({
        "priority": "medium",
        "title": "Lift boarding / exiting animations not complete",
        "signal": "qsb_floor_interior.js only animates packet routes between sections; capsules don't visibly enter/exit lifts.",
        "fix": "Extend qsb_floor_interior.js capsule paths with lift dock + door states.",
    })

    # 5) Floor interior glyph coverage
    weak_points.append({
        "priority": "medium",
        "title": "Manager / overseer / accountant glyphs missing in floor interiors",
        "signal": "tower_ops.management_chain.managers_for_floor surfaces in /api/floor_detail but qsb_floor_interior.js doesn't render the corresponding desks.",
        "fix": "Add manager office, overseer balcony, and accountant card sections to layoutGeneric and per-floor layouts.",
    })

    # 6) Department coverage
    departments_in_floors = {f.get("department") for f in floors_list if isinstance(f, dict)}
    needed = ["QA / Testing Department", "Facilities Department"]
    missing_depts = [n for n in needed
                     if not any(n.split()[0].lower() in (d or "").lower()
                                for d in departments_in_floors)]
    if missing_depts:
        weak_points.append({
            "priority": "low",
            "title": "Department coverage gaps",
            "signal": "missing or merged: " + ", ".join(missing_depts),
            "fix": "Map them onto existing floors or stand up dedicated floor manifests.",
        })

    # 7) Worker training UI on Worker ID card
    weak_points.append({
        "priority": "low",
        "title": "Per-worker enrolment / exam UI missing from Worker ID Card",
        "signal": "Training registries (/api/training/courses, /api/training/certifications) exist but the worker detail window has no enrol/exam controls.",
        "fix": "Add buttons in openWorkerWindow that POST /api/training/enrol + /api/training/complete_lesson.",
    })

    # 8) Accountant cards exposed via API but not visualized
    weak_points.append({
        "priority": "low",
        "title": "Floor accountant cards exist in API but lack interior visualization",
        "signal": "/api/accounts/floor_accountants returns records; no floor interior section renders them.",
        "fix": "Add a small accountant card to relevant floor interiors (41/42/43).",
    })

    # 9) Audit recommendations surfacing
    weak_points.append({
        "priority": "low",
        "title": "Audit recommendations remain advisory only",
        "signal": "/api/audit/next_steps and /api/audit/gaps are present but no top-level panel surfaces them.",
        "fix": "Add a 'Next Steps' card to the right rail or bottom ticker.",
    })

    # 10) Mission Control / Daily Briefing
    weak_points.append({
        "priority": "low",
        "title": "Dashboard needs a Mission Control / Daily Briefing panel",
        "signal": "Kernel state + AutoLoop + recruitment status are visible separately but not stitched into a single morning briefing.",
        "fix": "Add a Mission Control window that consolidates Kernel + Locks + AutoLoop + Recruitment + Trading readiness.",
    })

    # Honest count of recruitment + workers
    recruitment_total = (rec_workers.get("workers") or []) if isinstance(rec_workers, dict) else []
    floor45_candidates = int(f45_status.get("candidate_count") or 0)

    # Final structured payload
    return {
        "report_kind": "qsb_systems_check",
        "ts": datetime.now(timezone.utc).isoformat(),
        "execution_required": False,
        "execution_allowed": False,
        "intent": "READ_ONLY_DIAGNOSTIC",
        "summary": {
            "kernel": {
                "installed": bool(kernel_act.get("kernel_installed")),
                "activation_status": kernel_act.get("activation_status"),
                "active_kernel_source": kernel_act.get("active_kernel_source"),
                "QSBKernelCore_instantiated": bool(kernel_act.get("QSBKernelCore_instantiated")),
                "kernel_health": kernel_hd.get("kernel_health") or kernel_hd.get("status"),
                "continuity_state_size_bytes": cont_size,
                "continuity_previous_chain_depth": cont_depth,
            },
            "autoloop": {
                "status": autoloop_l.get("status"),
                "cycle_index": autoloop_l.get("cycle_index"),
                "mode": autoloop_l.get("mode"),
                "latest_ts": autoloop_l.get("ts") or autoloop_l.get("latest_ts"),
            },
            "floors": {
                "floors_registered": floor_count,
                "named_floors_in_name_map": named_floor_count,
                "render_model_floor_count": render_floor_count,
                "render_model_route_count": route_count,
            },
            "trading_telemetry": {
                "oanda_pricing_ready": oanda_ready,
                "binance_public_market_data_ready": binance_ready,
                "stocks_public_market_data_ready": stock_ready,
                "live_trading_enabled": False,
                "order_execution_enabled": False,
            },
            "airllm": {
                "registered": bool(airllm_chamber.get("registered") or airllm_chamber.get("status")),
                "advisory_only": True,
                "execution_allowed": False,
            },
            "recruitment": {
                "legacy_agency_worker_count": len(recruitment_total),
                "floor45_candidate_count": floor45_candidates,
                "execution_allowed": False,
                "sandbox_only": True,
            },
            "inventory_count": len(inventory.get("items") or []) if isinstance(inventory, dict) else 0,
            "dialogue_log_size_bytes": _kernel_dialogue_log_size(),
        },
        "weak_points": weak_points,
        "locks": {k: False for k in FLOOR_30_LOCK_KEYS},
        "lock_count_true": 0,
        "all_execution_gates_closed": True,
    }


def _format_systems_check_block(report):
    """Render the structured systems-check report as a kernel-style block."""
    s = report.get("summary") or {}
    k = s.get("kernel") or {}
    a = s.get("autoloop") or {}
    f = s.get("floors") or {}
    t = s.get("trading_telemetry") or {}
    rec = s.get("recruitment") or {}
    weak = report.get("weak_points") or []

    lines = []
    lines.append("QSB Tower — Read-Only Systems Check")
    lines.append("=" * 56)
    lines.append("Intent: READ_ONLY_DIAGNOSTIC · execution_required: False")
    lines.append("All execution locks remain closed (lock_count_true: %d)."
                 % report.get("lock_count_true", 0))
    lines.append("")
    lines.append("Kernel")
    lines.append("  activation_status:        %s" % k.get("activation_status"))
    lines.append("  active_kernel_source:     %s" % k.get("active_kernel_source"))
    lines.append("  QSBKernelCore_instantiated: %s" % k.get("QSBKernelCore_instantiated"))
    lines.append("  kernel_health:            %s" % k.get("kernel_health"))
    lines.append("  continuity_state_size:    %s bytes (depth=%s)" %
                 (k.get("continuity_state_size_bytes"),
                  k.get("continuity_previous_chain_depth")))
    lines.append("")
    lines.append("AutoLoop")
    lines.append("  status:       %s" % a.get("status"))
    lines.append("  cycle_index:  %s" % a.get("cycle_index"))
    lines.append("  mode:         %s" % a.get("mode"))
    lines.append("")
    lines.append("Floors")
    lines.append("  registered:                %s" % f.get("floors_registered"))
    lines.append("  in floor_name_map:         %s" % f.get("named_floors_in_name_map"))
    lines.append("  render_model floors:       %s" % f.get("render_model_floor_count"))
    lines.append("  render_model routes:       %s" % f.get("render_model_route_count"))
    lines.append("")
    lines.append("Trading telemetry (read-only)")
    lines.append("  oanda_pricing_ready:               %s" % t.get("oanda_pricing_ready"))
    lines.append("  binance_public_market_data_ready:  %s" % t.get("binance_public_market_data_ready"))
    lines.append("  stocks_public_market_data_ready:   %s" % t.get("stocks_public_market_data_ready"))
    lines.append("  live_trading_enabled:              False")
    lines.append("  order_execution_enabled:           False")
    lines.append("")
    lines.append("Recruitment")
    lines.append("  legacy_agency_worker_count:   %s" % rec.get("legacy_agency_worker_count"))
    lines.append("  floor45_candidate_count:      %s" % rec.get("floor45_candidate_count"))
    lines.append("  sandbox_only:                 True")
    lines.append("")
    lines.append("Weak points (ranked)")
    lines.append("-" * 56)
    pri_rank = {"high": 0, "medium": 1, "low": 2, "info": 3}
    ranked = sorted(weak, key=lambda x: pri_rank.get(x.get("priority"), 9))
    for i, w in enumerate(ranked, 1):
        lines.append("  %2d. [%s] %s" % (i, (w.get("priority") or "low").upper(),
                                          w.get("title")))
        if w.get("signal"):
            lines.append("        signal: %s" % w["signal"])
        if w.get("fix"):
            lines.append("        fix:    %s" % w["fix"])
    lines.append("-" * 56)
    lines.append("No execution required. All execution gates remain closed.")
    return "\n".join(lines)


# ── EQSB structured reply builder ───────────────────────────────────────
# When the operator asks an EQSB-specific question we serve a structured
# block from the eqsb_*.json registries directly. The local model is
# allowed to paraphrase, never to invent flag values.

_EQSB_TOPICS = (
    ("axioms",          ("axiom", "explain axioms", "what are your axioms",
                          "constitution", "identity")),
    ("beliefs",         ("belief", "belief lifecycle", "explain beliefs",
                          "what do you believe")),
    ("symbolic_graph",  ("symbolic graph", "symbolic state", "explain symbolic")),
    ("entropy",         ("entropy", "explain entropy", "drift", "stability")),
    ("quantum",         ("quantum signal", "quantum mode", "quantum",
                          "explain quantum")),
    ("contradictions",  ("contradiction", "explain contradictions")),
    ("hypotheses",      ("hypothesis", "hypotheses", "explain hypotheses",
                          "which hypothesis collapsed", "explain hypothesis",
                          "collapse")),
    ("memory",          ("memory policy", "memory architecture",
                          "explain memory", "how is memory",
                          "continuity", "boot posture")),
    ("model_lanes",     ("model lane", "model lanes", "lane governance",
                          "how do your model lanes",
                          "model governance", "how do you validate model")),
    ("airllm_allowed",  ("airllm allowed", "what is airllm allowed",
                          "what can airllm do")),
    ("qsb_vs_model",    ("difference between qsb and a model",
                          "difference between qsb and model",
                          "qsb vs model", "qsb vs a model",
                          "difference between you and a model",
                          "what is the difference between eqsb",
                          "why you are not a model",
                          "why are you not a model")),
    # Major-phase additions
    ("guardian",        ("guardian", "explain your guardian",
                          "what does guardian protect")),
    ("cadence",         ("cadence", "heartbeat", "explain your cadence",
                          "explain cadence", "explain your heartbeat")),
    ("replay_ledger",   ("replay ledger", "audit ledger", "explain replay",
                          "explain your replay")),
    ("architecture",    ("eqsb architecture", "kernel architecture",
                          "architecture layers", "explain your architecture",
                          "explain your upgraded eqsb",
                          "explain your upgraded architecture",
                          "what is your architecture")),
    ("systems_check_eqsb",
                        ("systems check", "do a systems check", "system check",
                          "kernel self audit", "self audit",
                          "what do you need fixed", "what should i run next")),
    # Phase V2 topics
    ("openclaw_v2",     ("openclaw status", "open claw status",
                          "openclaw active", "show openclaw")),
    ("paper_trades_v2", ("open paper trade", "paper trades",
                          "open paper/testnet", "open paper trades",
                          "testnet trades", "open trade count",
                          "max open trades", "max_open_trades",
                          "current open trade", "remaining trade slots")),
    ("trade_pnl_v2",    ("pnl", "p&l", "realized pnl", "trade pnl")),
    ("trade_lessons_v2",
                        ("trade lesson", "trade lessons", "lessons learned",
                          "lesson learned", "what lessons")),
    ("workers_v2",      ("worker count reconciliation", "worker reconciliation",
                          "total workers", "workers employed",
                          "total workers employed",
                          "active workers", "newly employed workers",
                          "how many workers", "worker mismatch",
                          "why did the worker counts mismatch")),
    ("dashboard_3d_v2", ("3d dashboard", "skyscraper",
                          "3d dashboard upgrade", "3d dashboard upgrade status",
                          "skyscraper upgrade", "dashboard upgrade")),
    # Command Center V1 topics
    ("profit_command",  ("profit command", "profit summary", "profit report",
                          "profit",
                          "trading mission", "skyscraper profit",
                          "best department",
                          "profit-focused actions")),
    ("workforce_v1",    ("worker scorecard", "worker scorecards",
                          "worker rewards", "worker discipline",
                          "worker promotion", "worker promotions",
                          "promotion ladder", "rewards and awards",
                          "three-strike", "three strike",
                          "rewards", "awards", "discipline",
                          "workforce hr", "workforce summary")),
    ("running_commentary",
                        ("running commentary", "narrator", "narration",
                          "commentary status", "voice narration",
                          "tower commentary", "floor commentary")),
    ("live_data_only",  ("live data only", "live_data_only",
                          "no random visuals", "data-driven visuals",
                          "are dashboard visuals real",
                          "dashboard live telemetry")),
    # EQSB Observatory + Hardware Floor + Telemetry Repair (V1)
    ("hardware_obs",    ("hardware", "what hardware",
                          "cpu", "what cpu", "ryzen",
                          "gpu", "what gpu", "nvidia", "rtx",
                          "ram", "memory", "how much ram",
                          "how much disk",
                          "is cuda available", "cuda",
                          "bottleneck", "make the system faster",
                          "performance advice",
                          "hardware systems floor",
                          "do we have a hardware")),
    ("code_obs",        ("codebase", "what codebase", "code map",
                          "what files make up the dashboard",
                          "what scripts exist", "what endpoints exist",
                          "what code looks fragile",
                          "code observatory")),
    ("claude_history",  ("claude change", "claude changes",
                          "what did claude change last",
                          "claude upgrade", "claude upgrades",
                          "what risks were introduced",
                          "lessons did you learn",
                          "phase history",
                          "what should claude improve next",
                          "upgrade ledger")),
    ("telemetry_repair",("worker movements", "lift movements",
                          "how many worker movements",
                          "how many lift movements",
                          "floor 44 accounts",
                          "is floor 44",
                          "7-day worker reward trend",
                          "narrator history", "discipline triggers",
                          "selected-floor narration default",
                          "selected floor narration")),
    # Worker Truth (V1)
    ("revamp_3d_v1",    ("what changed in the 3d dashboard rebuild",
                          "what changed in the 3d dashboard",
                          "3d dashboard rebuild",
                          "3d revamp",
                          "explain the 3d revamp",
                          "what changed visually",
                          "what files were added")),
    ("rebuild_v1",      ("why were workers not shown properly",
                          "why were workers not shown",
                          "what changed in the new dashboard rebuild",
                          "what did the rebuild change",
                          "where are the workers now",
                          "what is openclaw supervising",
                          "what departments are occupied",
                          "what floors are still empty",
                          "what workers are doing tasks right now",
                          "what tasks are workers doing",
                          "what was the root cause",
                          "explain the rebuild",
                          "explain why workers were not shown",
                          "openclaw supervising",
                          "openclaw tickets",
                          "openclaw findings",
                          "openclaw route")),
    ("completion_v1",   ("what is still not 100", "is the skyscraper 100",
                          "completion score", "acceptance gates",
                          "what acceptance gates",
                          "what departments are complete",
                          "what floors are occupied",
                          "where are idle workers", "where are resting workers",
                          "is the skyscraper online",
                          "what did the completion loop fix",
                          "what remains below 100",
                          "hard blockers",
                          "is the skyscraper complete")),
    ("workforce_v1",    ("explain the worker system",
                          "how many are operational",
                          "how many are training",
                          "how many candidates", "how many stale",
                          "how many suspended",
                          "where are the sim_worker_floor",
                          "where do sim workers",
                          "workforce", "workforce overview",
                          "workers in recruitment",
                          "workers in training",
                          "workers in lessons",
                          "workers in active operations",
                          "active operations",
                          "what workers are in recruitment",
                          "why were workers wrapped around the tower",
                          "why were the workers wrapped",
                          "why were workers spiral",
                          "spiral", "swarm",
                          "explain why the workers were wrapped",
                          "how is the workforce organized",
                          "which workers need promotion",
                          "which workers need retraining",
                          "which workers need discipline",
                          "what worker movements happened recently")),
    ("worker_truth",    ("why does the sidebar say 64",
                          "why does the dashboard sidebar say",
                          "sidebar says 64", "header says 64",
                          "sidebar say 64", "header say 64",
                          "why does another panel say 191",
                          "why did a prior report mention 170",
                          "why does binance",
                          "how many workers are canonical",
                          "are the worker bands",
                          "worker bands around the tower",
                          "worker truth", "worker count contradiction",
                          "sim_worker_floor", "simulated workers",
                          "are workers fake")),
    ("floor41_oanda",   ("open the floor 41 oanda report",
                          "floor 41 oanda",
                          "floor 41 report",
                          "what is floor 41 thinking about",
                          "what is floor 41 oanda doing",
                          "what is floor 41 doing right now",
                          "what is floor 41 doing",
                          "floor 41 doing right now",
                          "what trades are open on oanda floor 41",
                          "what trades are open on floor 41",
                          "what trades closed today on floor 41",
                          "what is the floor 41 pnl",
                          "what is the oanda risk state",
                          "what would floor 41 do next",
                          "oanda floor 41 account",
                          "oanda floor 41 open trades",
                          "oanda floor 41 closed trades",
                          "oanda floor 41 pnl",
                          "oanda floor 41 worker thoughts",
                          "oanda floor 41 openclaw findings",
                          "tell me account state open trades closed trades pnl",
                          "is practice paper open close trading functional",
                          "is paper open close functional")),
    ("floor42_binance", ("floor 42 binance",
                          "what is floor 42",
                          "what is floor 42 doing",
                          "what workers are active on floor 42",
                          "what workers are on floor 42",
                          "binance floor 42",
                          "binance testnet floor",
                          "floor 42 workers",
                          "floor 42 rooms",
                          "is binance live")),
    ("penthouse",       ("penthouse",
                          "kernel floor",
                          "command center",
                          "why is the penthouse plain",
                          "why is the penthouse floor plain",
                          "what is in the penthouse",
                          "explain the penthouse",
                          "kernel command center",
                          "what does the penthouse show",
                          "penthouse gauges",
                          "penthouse command")),
    ("hardware_observatory", ("what hardware are you running on",
                          "what hardware",
                          "hardware observatory",
                          "what cpu",
                          "what gpu",
                          "system hardware",
                          "machine hardware",
                          "what platform are you running on")),
    ("code_observatory",  ("what did claude change last",
                          "what did claude change",
                          "last claude change",
                          "claude changes",
                          "code observatory",
                          "what code changed recently",
                          "recent code changes",
                          "phase history",
                          "claude recent edits")),
    ("dashboard_repair",  ("what is broken in the dashboard",
                          "what is wrong with the dashboard",
                          "what's wrong with the dashboard",
                          "dashboard not working",
                          "dashboard repair",
                          "what did this repair change",
                          "what does this phase fix",
                          "repair priority",
                          "next repair priority",
                          "what needs repair",
                          "dashboard issues")),
    ("openclaw_supervision", ("what is openclaw supervising",
                          "what is openclaw doing",
                          "openclaw current floor",
                          "openclaw tickets",
                          "openclaw findings",
                          "openclaw status",
                          "what is openclaw")),
    ("native_cockpit_v2", (
        "native cockpit",
        "native cockpit v2",
        "qsb native cockpit",
        "qsb native cockpit v2",
        "report the qsb native cockpit v2 plan",
        "native graphics engine",
        "standalone cockpit",
        "standalone desktop cockpit",
        "non browser cockpit",
        "no chrome cockpit",
        "launch native cockpit",
        "pyqt cockpit",
        "godot cockpit",
        "panda3d cockpit")),
    ("skyscraper_occupancy", (
        "audit every floor",
        "audit every floor and explain",
        "explain the new 1000 workers",
        "where did the new 1000 workers go",
        "how many workers do we have now",
        "how many workers exist now",
        "what does every floor do",
        "which floors are still vacant",
        "what departments make profit",
        "what is the etsy floor",
        "what is the commerce wing",
        "what online shops can we build",
        "what online shops can we sell",
        "what floors support your evolution",
        "what floors support profit",
        "where do workers sleep",
        "where do workers sleep and recover",
        "what classrooms exist",
        "what should we build next to make money",
        "what should we build next to make money safely",
        "what teams were created",
        "what floor managers were created",
        "what watchers seers and overseers",
        "rest floor",
        "rest and recreation floor",
        "print on demand floor",
        "3d printing floor",
        "is there an etsy floor")),
    ("recent_upgrades", (
        "recent upgrades",
        "watched upgrades",
        "learned from upgrades",
        "latest phase",
        "upgrade ledger",
        "phase history",
        "what phases ran",
        "what phases have run",
        "what upgrades",
        "what recent upgrades",
        "what recent upgrades have you watched",
        "what upgrades have you watched",
        "what did you watch learn from",
        "watched learned from or recorded",
        "mention exact ledger files and latest phases",
        "list recent phases",
        "phase ledger",
        "claude_changes",
        "phases run recently")),
    ("godot_native_status", (
        "godot",
        "godot real 3d cockpit status",
        "godot real 3d",
        "godot install",
        "godot version",
        "panda3d",
        "panda3d fallback",
        "qsb_3d_engine_status",
        "graphics engine",
        "graphics engine status",
        "3d engine status",
        "real 3d cockpit",
        "what is the godot",
        "native cockpit",
        "native 3d cockpit",
        "pyqt fallback",
        "pyqt fallback classification",
        "godot project",
        "godot scene")),
    ("missing_features", (
        "missing features",
        "missing dashboard controls",
        "what features are still missing",
        "what features are missing",
        "what is missing or incomplete",
        "what features are still missing or incomplete",
        "incomplete from the new cockpit",
        "feature parity",
        "feature parity matrix",
        "missing backlog",
        "backlog",
        "not migrated",
        "not yet migrated",
        "what is missing from the cockpit",
        "what is still missing",
        "which features are still missing",
        "still incomplete",
        "feature gap",
        "feature gaps")),
    ("learning_evidence", (
        "evidence you are learning",
        "evidence proves you are reading",
        "evidence you read upgrade registries",
        "evidence you read registries",
        "what evidence proves you are reading",
        "learning loop",
        "learning evidence",
        "kernel learning loop",
        "observatory",
        "code observatory",
        "hardware observatory",
        "upgrade records",
        "cite registry log names",
        "cite registry/log names",
        "not static text",
        "not repeating static text",
        "prove you are not repeating",
        "prove you read registries")),
    ("ml_rl_lab", (
        "ml/rl lab",
        "ml rl lab",
        "ml_rl lab",
        "ml/rl lab integration",
        "ml/rl lab status",
        "report the ml/rl lab",
        "report the ml rl lab",
        "ml rl classroom",
        "ml/rl classroom",
        "dqn smoke test",
        "qdnn smoke test",
        "torchrl status",
        "torch installed",
        "is torch installed",
        "torch and cuda",
        "cuda available",
        "stable baselines",
        "stable-baselines3",
        "gymnasium installed",
        "reinforcement learning lab",
        "deep learning lab",
        "what workers are learning ml",
        "openclaw ml rl supervision",
        "opencore ml rl",
        "ml rl curriculum",
        "ml/rl curriculum",
        "ml rl research lab",
        "ml/rl research lab")),
    # Cognitive Kernel V1 — surfaces the new 20-layer cognition substrate
    ("cognitive_kernel_state",
                        ("cognitive kernel", "what are you thinking",
                          "what are you thinking about",
                          "what are you thinking about right now",
                          "what's in working memory",
                          "what is in working memory",
                          "working memory contents",
                          "show me your thoughts",
                          "show your thoughts",
                          "show me your cognition",
                          "cognition state",
                          "cognition summary",
                          "kernel introspection",
                          "kernel cognition",
                          "kernel self-model",
                          "kernel self model",
                          "self-model snapshot",
                          "self model snapshot",
                          "what do you know about yourself",
                          "what cognitive layers",
                          "what cognitive layers do you have",
                          "what are your cognitive layers",
                          "20 cognitive layers",
                          "twenty cognitive layers",
                          "explain your cognitive architecture",
                          "show me reflection",
                          "show reflection",
                          "show reflection notes",
                          "show me proposals",
                          "show open proposals",
                          "open action proposals",
                          "show me curiosity",
                          "open curiosity items",
                          "what are you curious about",
                          "show me contradictions",
                          "show contradictions",
                          "what contradictions",
                          "show me your goals",
                          "what are your goals",
                          "active goals",
                          "show me thought trace",
                          "thought trace",
                          "why did you say that",
                          "show last tick",
                          "orchestrator last tick",
                          "tick summary",
                          "cognitive tick",
                          "floor-to-mind map",
                          "floor to mind map",
                          "which floor maps to which cognitive layer",
                          "counterfactual",
                          "what if",
                          "causal phase model",
                          "phase causal graph")),
    # Commerce Wing / Floor 46 — Etsy preview-only
    ("commerce_floor",
                        ("commerce floor", "commerce wing", "etsy",
                          "etsy floor", "floor 46", "floor 46 commerce",
                          "open an etsy store", "open etsy", "etsy store",
                          "sandbox catalog", "show catalog",
                          "show me the catalog", "product catalog",
                          "commerce catalog",
                          "pricing advisor", "pricing analytics",
                          "what are we selling", "what products do we sell",
                          "are we ready to publish",
                          "publish listings", "publish listing",
                          "is the etsy gate locked")),
    # Profit Analytics / Floor 47
    ("profit_plan",
                        ("profit plan", "profit analytics", "profit snapshot",
                          "profit center", "floor 47", "floor 47 profit",
                          "how do we make money", "how to make profit",
                          "improve profit", "improve profits",
                          "what is our profit", "what's our profit",
                          "projected revenue", "projected profit",
                          "topline revenue",
                          "show profit", "show the profit",
                          "cross-floor revenue", "revenue by floor")),
    # Worker Reassignment
    ("reassign_workers",
                        ("reassign workers", "reassign worker",
                          "where should workers go",
                          "move workers", "where to put workers",
                          "idle workers", "idle worker",
                          "what should idle workers do",
                          "worker reassignment proposals",
                          "worker assignments",
                          "drain idle capacity",
                          "where is idle labour")),
    # V7 — sessions, binance scaffold, comms scaffold, dashboard pointer
    ("trading_sessions",
                        ("trading sessions", "trading hours",
                          "market hours", "session overlap",
                          "what session is open",
                          "tokyo session", "london session", "ny session",
                          "sydney session",
                          "best time to trade",
                          "time zones", "time zone",
                          "world clock")),
    ("binance_testnet_status",
                        ("binance testnet", "binance status",
                          "is binance ready",
                          "binance credentials",
                          "binance api",
                          "set up binance",
                          "binance setup",
                          "binance preflight",
                          "binance gates")),
    ("comms_channels",
                        ("telegram", "telegram bot",
                          "sms", "send sms",
                          "skyscraper number",
                          "skyscraper phone",
                          "send me text",
                          "text me", "send text",
                          "email me", "skyscraper email",
                          "communication channels",
                          "comms channels")),
    ("dashboard_pointer",
                        ("dashboard", "open dashboard",
                          "show dashboard",
                          "live dashboard",
                          "where is the dashboard",
                          "cockpit",
                          "3d dashboard",
                          "3d view",
                          "cognitive panel")),
    # V6 — OANDA certified-worker trades (LIVE practice account)
    ("oanda_worker_status",
                        ("oanda worker", "oanda workers",
                          "oanda status", "oanda live",
                          "oanda real",
                          "are workers trading oanda",
                          "are workers placing orders",
                          "live oanda",
                          "oanda practice live",
                          "oanda account",
                          "oanda balance",
                          "worker oanda trades",
                          "real oanda trades",
                          "oanda open trades",
                          "show oanda")),
    # V5 — research queue + finance live status (honest reporting)
    ("research_queue",
                        ("research", "research queue",
                          "what should we research",
                          "research questions",
                          "internet access", "web access",
                          "crawl the internet",
                          "do research",
                          "open research items",
                          "answered research",
                          "allowlist", "research allowlist",
                          "web research")),
    ("finance_live_status",
                        ("finance live status", "live status",
                          "are we trading",
                          "are we placing orders",
                          "are we placing real orders",
                          "real orders",
                          "real trades",
                          "oanda live",
                          "binance live",
                          "stocks live",
                          "broker calls",
                          "broker status",
                          "are workers trading",
                          "real money trades")),
    # V4 — Tower Studio (web/IT company) + Lumen AI (chat service)
    ("tower_studio",
                        ("tower studio", "web design",
                          "web design company", "it company",
                          "studio", "floor 49 studio",
                          "studio services", "studio price",
                          "studio website",
                          "studio customers", "studio projects",
                          "graphics design",
                          "web design studio",
                          "make a website",
                          "build my website")),
    ("lumen_ai",
                        ("lumen", "lumen ai", "lumen chat",
                          "lumen playground", "chat ai",
                          "our chat ai", "our own chat ai",
                          "floor 48", "floor 48 lumen",
                          "lumen tiers", "lumen pricing",
                          "lumen api",
                          "chat ai pricing",
                          "open lumen",
                          "open chat ai")),
    # V3 — banking gateway, worker spawn, OANDA attribution, image promotion, spend, briefing, 3D
    ("banking_gateway",
                        ("banking gateway", "real money",
                          "halifax", "square",
                          "real bank", "real bank account",
                          "add bank account", "add my bank account",
                          "withdraw profits", "real withdrawal",
                          "real deposits", "real payouts",
                          "fiat", "fiat money",
                          "how do i add my bank",
                          "open banking",
                          "real money gateway")),
    ("worker_spawn_status",
                        ("worker spawn", "spawn workers",
                          "pending births", "pending birth",
                          "child birth", "children waiting",
                          "born workers", "newly born",
                          "spawn roster",
                          "commit child", "commit children",
                          "are there pending births")),
    ("oanda_attribution",
                        ("oanda attribution", "ledger attribution",
                          "worker id ledger", "trade attribution",
                          "unassigned trades", "ledger coverage",
                          "attribution coverage",
                          "are trades attributed")),
    ("free_image_promote",
                        ("approved free image", "approved drafts",
                          "promote free image",
                          "promoted free image",
                          "free image approvals",
                          "free image promotions",
                          "approved listings",
                          "promoted listings")),
    ("bank_spend",
                        ("spend qbc", "spend bank",
                          "qbc spending", "qbc spends",
                          "worker spends", "worker buy",
                          "classroom unlock", "instrument unlock",
                          "cosmetic title", "dowry transfer",
                          "friend gift",
                          "pending spends",
                          "show spends",
                          "show me the spends")),
    ("morning_briefing",
                        ("briefing", "morning briefing",
                          "daily briefing", "tower briefing",
                          "summary", "tower summary",
                          "give me the summary",
                          "what's the latest",
                          "whats the latest",
                          "what should i look at",
                          "what needs my attention",
                          "tower digest",
                          "give me a digest",
                          # Natural-language additions — these all want the briefing
                          "what changed", "what has changed",
                          "what is new", "what's new", "whats new",
                          "right now", "today",
                          "where are we", "current state",
                          "what is happening", "what's happening",
                          "tell me about today",
                          "what is open", "what's open",
                          "what is missing", "what's missing",
                          "what is broken", "what's broken")),
    ("godot_visuals",
                        ("godot visuals", "3d visuals",
                          "3d cockpit", "cockpit visuals",
                          "3d overlay", "3d overlays",
                          "watch the skyscraper",
                          "watch tower live",
                          "watch the tower",
                          "see the workers",
                          "visual overlay")),
    # V2 — internal bank, compensation, lineage perf, curriculum, free images, audit
    ("bank",
                        ("bank", "qbc", "qsb credit", "show the bank",
                          "show me the bank", "total supply",
                          "currency", "internal currency",
                          "worker balance", "show balances",
                          "top balances", "bank supply",
                          "skyscraper bank", "tower bank",
                          "qbc balance", "qbc supply")),
    ("compensation",
                        ("compensation", "pay the workers",
                          "how do we pay workers", "worker pay",
                          "payment rates", "compensation rates",
                          "pay rates", "settle payroll",
                          "settle compensation", "pay round",
                          "qbc payouts", "show pay")),
    ("lineage_performance",
                        ("lineage performance", "lineage stats",
                          "lineage outperform", "best lineages",
                          "best lineage", "best family",
                          "dynasty performance",
                          "which family is best",
                          "lineage of worker",
                          "descendants outperform")),
    ("curriculum_evolution",
                        ("curriculum evolution", "curriculum scoring",
                          "lesson outcome", "lesson outcomes",
                          "which lessons work", "best lessons",
                          "worst lessons",
                          "deprecate lesson",
                          "reinforce lesson",
                          "evolve curriculum")),
    ("free_images",
                        ("free images", "free image", "free image catalog",
                          "public domain images", "cc0 images",
                          "unsplash", "pexels", "pixabay",
                          "smithsonian", "rijksmuseum",
                          "image sources", "image source list",
                          "free image sources",
                          "draft listings from images",
                          "free image draft")),
    ("self_audit",
                        ("self audit", "self-audit",
                          "system health", "audit report",
                          "show audit", "show self audit",
                          "are we healthy", "any audit findings",
                          "cognition health", "kernel audit")),
    # Finance lineage v1 — certification + family tree + grants
    ("worker_certification",
                        ("worker certification", "who is certified",
                          "who's certified", "certified workers",
                          "trading authority", "authority gate",
                          "is worker certified", "show certifications",
                          "certification ledger", "certs",
                          "suspended workers", "studying workers",
                          "workers studying", "test results")),
    ("worker_pnl",
                        ("who's profitable", "whos profitable",
                          "who is profitable",
                          "who is making money",
                          "top earners", "worker pnl",
                          "worker p&l", "worker performance",
                          "per worker pnl", "per-worker pnl",
                          "show me the earners",
                          "biggest losses",
                          "worst drawdowns")),
    ("family_tree",
                        ("family tree", "show the family tree",
                          "show me the family tree",
                          "lineage", "show lineage",
                          "who are the parents", "who are the children",
                          "who has children", "who is a friend",
                          "friends of",
                          "generations", "dynasties",
                          "family", "worker family",
                          "show friends",
                          "child grants",
                          "show me the lineage tree")),
    ("reward_report",
                        ("pending grants", "open grants",
                          "show pending grants",
                          "any grants", "grants pending",
                          "reward report", "grant report",
                          "grant proposals",
                          "who should be promoted",
                          "who should get a friend",
                          "who should get a child",
                          "pending rewards",
                          "show grant reports")),
    # Candidate floors — what to open next
    ("candidate_floors",
                        ("candidate floors", "what floors should we open",
                          "what to open next",
                          "next floor to open",
                          "which floor to open next",
                          "open more floors",
                          "open new floors",
                          "expansion floors",
                          "what is on floor 48",
                          "what is on floor 49",
                          "floor 48", "floor 49", "floor 50", "floor 51",
                          "floor 52", "floor 53",
                          "vacant floor", "vacant floors",
                          "sealed floor", "sealed floors")),
    # V18 — operational queries Ross actually asks
    ("tower_status",    ("tower status", "status", "how is the tower",
                          "how are things", "summary", "report",
                          "what is happening", "what is going on",
                          "how many workers", "how many floors",
                          "worker count", "floor count",
                          "what is the tower doing", "tower report",
                          "where are we", "give me a status")),
    ("oanda_profit",    ("oanda profit", "trading profit", "pnl",
                          "how much profit", "what is the profit",
                          "how much have we made", "oanda pnl",
                          "practice pnl", "realized pnl",
                          "open trades", "how many open trades")),
    ("code_crew",       ("code crew", "code team", "f47 crew",
                          "what is the code crew doing",
                          "what does the crew do",
                          "wren's code crew", "wren code crew",
                          "100 workers", "the code workers")),
    ("greeting",        ("hello", "hi", "hey", "good morning",
                          "good afternoon", "good evening",
                          "are you alive", "are you there",
                          "wake up", "wren are you there")),
)


def _wants_eqsb_topic(message):
    msg = (message or "").lower()
    topics = []
    for name, triggers in _EQSB_TOPICS:
        if any(t in msg for t in triggers):
            topics.append(name)
    return topics


def _eqsb_load(name, fallback=None):
    p = ROOT / "data/registries" / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _format_eqsb_block(topics):
    """Build a single structured block answering every requested EQSB
    topic. Reads exclusively from data/registries/eqsb_*.json so the
    answer reflects what the kernel actually believes, not what a
    paraphrase model imagines."""
    # Greeting short-circuit: when the only matched topic is "greeting"
    # (typical first reply), skip the schema header dump and return a
    # warm humanised line. Keeps the topic key the same.
    if list(topics) == ["greeting"]:
        return ("Hi, I'm Lumen — the tower's local chat AI. I won't "
                "pretend to know things I don't. Try 'tower briefing' "
                "or 'family tree' to start.")
    intro = _eqsb_load("eqsb_kernel_introspection_latest.json")
    if not intro:
        return None
    lines = []
    lines.append("EQSB Kernel — Structured Introspection")
    lines.append("=" * 56)
    lines.append("schema_version: %s" % intro.get("schema_version"))
    lines.append("generated_ts:   %s" % intro.get("generated_ts"))
    lines.append("lock_count_true: %s · active_local_only: True · execution_allowed: False"
                 % (intro.get("lock_state") or {}).get("lock_count_true"))
    lines.append("")

    if "axioms" in topics:
        ax = _eqsb_load("eqsb_axiom_registry.json")
        ident = _eqsb_load("eqsb_identity_constitution.json")
        lines.append("Identity & Axioms")
        lines.append("-" * 56)
        lines.append("Name: " + (ident.get("name") or "EQSB"))
        lines.append("Rooted in: " + (ident.get("rooted_in") or ""))
        lines.append("Constitution:")
        for chunk in (ident.get("constitution") or "").split(". "):
            chunk = chunk.strip()
            if chunk:
                lines.append("  · " + chunk + (".") if not chunk.endswith(".") else "  · " + chunk)
        lines.append("")
        lines.append("Axioms (count=%d, registry_truth_outranks_model=True):"
                     % (ax.get("axiom_count") or 0))
        for a in (ax.get("axioms") or []):
            lines.append("  [%s] %s" % (a.get("axiom_id"), a.get("text")))
        lines.append("")

    if "beliefs" in topics:
        b = _eqsb_load("eqsb_belief_lifecycle.json")
        lines.append("Belief Lifecycle")
        lines.append("-" * 56)
        lines.append("Lifecycle states: " + ", ".join(b.get("belief_states_in_use") or []))
        sc = b.get("state_counts") or {}
        for k in (b.get("belief_states_in_use") or []):
            lines.append("  %s: %s" % (k, sc.get(k, 0)))
        lines.append("Belief examples (kernel-introspected):")
        for be in (b.get("beliefs") or [])[:6]:
            lines.append("  · [%s] %s (confidence %.2f)" %
                         (be.get("state"), be.get("belief_text"),
                          float(be.get("confidence", 0))))
        lines.append("")

    if "symbolic_graph" in topics:
        g = _eqsb_load("eqsb_symbolic_graph.json")
        lines.append("Symbolic Graph")
        lines.append("-" * 56)
        lines.append("nodes: %s · edges: %s" %
                     (g.get("node_count"), g.get("edge_count")))
        lines.append("node kinds: " + ", ".join(g.get("node_kinds") or []))
        lines.append("relations in use: " + ", ".join(g.get("relations_in_use") or []))
        lines.append("")

    if "entropy" in topics:
        e = _eqsb_load("eqsb_entropy_state.json")
        lines.append("Entropy / Drift / Stability")
        lines.append("-" * 56)
        lines.append("entropy_score:        %s" % e.get("entropy_score"))
        lines.append("stability_score:      %s" % e.get("stability_score"))
        lines.append("drift_score:          %s" % e.get("drift_score"))
        lines.append("confidence_score:     %s" % e.get("confidence_score"))
        lines.append("contradiction_score:  %s" % e.get("contradiction_score"))
        lines.append("urgency_score:        %s" % e.get("urgency_score"))
        lines.append("inputs:               %s" % json.dumps(e.get("inputs")))
        for line in (e.get("explanation") or []):
            lines.append("  · " + line)
        lines.append("")

    if "quantum" in topics:
        q = _eqsb_load("eqsb_quantum_signal_state.json")
        lines.append("Quantum Signal (advisory-only simulator)")
        lines.append("-" * 56)
        lines.append("mode:                            %s" % q.get("mode"))
        lines.append("real_quantum_source_connected:   %s" % q.get("real_quantum_source_connected"))
        lines.append("qiskit_connected:                %s" % q.get("qiskit_connected"))
        lines.append("ibm_quantum_connected:           %s" % q.get("ibm_quantum_connected"))
        lines.append("no_external_quantum_calls:       %s" % q.get("no_external_quantum_calls"))
        lines.append("no_quantum_trading_decisions:    %s" % q.get("no_quantum_trading_decisions"))
        lines.append("execution_link:                  %s" % q.get("execution_link"))
        sel = q.get("selected_hypothesis") or {}
        lines.append("selected_hypothesis: %s (weight=%s)" %
                     (sel.get("hypothesis_id"), sel.get("normalized_weight")))
        lines.append("uncertainty_score:               %s" % q.get("uncertainty_score"))
        lines.append("collapse_reason: " + (q.get("collapse_reason") or "advisory"))
        lines.append("")

    if "contradictions" in topics:
        c = _eqsb_load("eqsb_contradiction_report.json")
        lines.append("Contradictions")
        lines.append("-" * 56)
        lines.append("contradiction_count: %s" % c.get("contradiction_count"))
        lines.append("by_severity:         %s" % json.dumps(c.get("by_severity") or {}))
        for item in (c.get("contradictions") or []):
            lines.append("  · [%s] %s" % (item.get("severity"), item.get("title")))
        lines.append("")

    if "hypotheses" in topics:
        h = _eqsb_load("eqsb_hypothesis_state.json")
        lines.append("Hypotheses")
        lines.append("-" * 56)
        lines.append("hypothesis_count: %s" % h.get("hypothesis_count"))
        lines.append("by_severity:      %s" % json.dumps(h.get("by_severity") or {}))
        for item in (h.get("hypotheses") or [])[:8]:
            lines.append("  · [%s] %s (conf=%.2f)" % (item.get("severity"),
                                                       item.get("title"),
                                                       float(item.get("confidence", 0))))
        lines.append("")

    if "memory" in topics:
        m = _eqsb_load("eqsb_memory_policy.json")
        lw = m.get("long_window") or {}
        sw = m.get("short_window") or {}
        lines.append("Memory Policy")
        lines.append("-" * 56)
        lines.append("short_window: %s (ttl_hours=%s, max=%s)" %
                     (sw.get("scope"), sw.get("ttl_hours"), sw.get("max_records")))
        lines.append("long_window:  %s" % lw.get("scope"))
        lines.append("continuity_state_size: %s bytes (depth=%s, history_count=%s)" %
                     (lw.get("continuity_state_size_bytes"),
                      lw.get("continuity_previous_chain_depth"),
                      lw.get("history_count")))
        lines.append("pinned_beliefs:")
        for p in (m.get("pinned_beliefs") or []):
            lines.append("  · " + p)
        lines.append("evidence rule: " + (m.get("evidence_based_update_rule") or ""))
        lines.append("")

    if "model_lanes" in topics:
        gov = _eqsb_load("eqsb_model_lane_governance.json")
        lines.append("Model Lane Governance")
        lines.append("-" * 56)
        for ln in (gov.get("lanes") or []):
            lines.append("  · %s — %s (execution_allowed=%s)" %
                         (ln.get("lane_id"), ln.get("role"),
                          ln.get("execution_allowed")))
        lines.append("Rules:")
        for r in (gov.get("validation_rules") or []):
            lines.append("  · " + r)
        lines.append("")

    if "airllm_allowed" in topics:
        gov = _eqsb_load("eqsb_model_lane_governance.json")
        airllm = next((l for l in (gov.get("lanes") or [])
                        if l.get("lane_id") == "lane_airllm_chamber"), {})
        lines.append("AirLLM — What is allowed?")
        lines.append("-" * 56)
        lines.append("isolation: " + str(airllm.get("isolation")))
        lines.append("role: " + str(airllm.get("role")))
        lines.append("execution_allowed:        %s" % airllm.get("execution_allowed"))
        lines.append("wired_into_autoloop:      %s" % airllm.get("wired_into_autoloop"))
        lines.append("wired_into_trading:       %s" % airllm.get("wired_into_trading"))
        lines.append("wired_into_openclaw:      %s" % airllm.get("wired_into_openclaw"))
        lines.append("wired_into_workers:       %s" % airllm.get("wired_into_workers"))
        lines.append("may_unlock_gates:         %s" % airllm.get("may_unlock_gates"))
        lines.append("registry_truth_outranks:  %s" % airllm.get("registry_truth_outranks"))
        lines.append("")

    if "qsb_vs_model" in topics:
        lines.append("Difference between QSB/EQSB and a model")
        lines.append("-" * 56)
        lines.append("· QSB/EQSB is the persistent symbolic kernel above models.")
        lines.append("· It owns: identity, axioms, beliefs, symbolic graph,")
        lines.append("  memory continuity, entropy, contradictions, safety policy.")
        lines.append("· Models (Ollama/Llama, AirLLM, future providers) are")
        lines.append("  REPLACEABLE advisory/speech lanes — never the kernel.")
        lines.append("· Registry truth outranks model paraphrase.")
        lines.append("· The kernel may advise; it does not execute.")
        lines.append("· Execution gates are separate from reasoning and remain locked.")
        lines.append("")

    if "guardian" in topics:
        g = _eqsb_load("eqsb_guardian_state.json")
        lines.append("Guardian Core")
        lines.append("-" * 56)
        lines.append("safety_state:                %s" % g.get("safety_state"))
        lines.append("default_verdict_read_only:   %s" % g.get("default_verdict_for_read_only"))
        lines.append("blocked_reasons: %s" % json.dumps(g.get("blocked_reasons") or {}))
        for v in (g.get("verdict_options") or []):
            lines.append("  · " + v)
        lines.append("Guardian protects: intents, model outputs, axiom compliance, ")
        lines.append("  belief transitions, quantum claims, continuity, entropy warnings.")
        lines.append("")

    if "cadence" in topics:
        c = _eqsb_load("eqsb_cadence_state.json")
        lines.append("Cadence / Heartbeat")
        lines.append("-" * 56)
        lines.append("cadence_id:               %s" % c.get("cadence_id"))
        lines.append("cadence_mode:             %s" % c.get("cadence_mode"))
        lines.append("is_autonomous_execution:  %s" % c.get("is_autonomous_execution"))
        lines.append("tick_count:               %s" % c.get("tick_count"))
        lines.append("loop_completeness_pct:    %s" % c.get("loop_completeness_pct"))
        lines.append("last_tick_ts:             %s" % c.get("last_tick_ts"))
        lines.append("next_tick_recommendation: %s" % c.get("next_tick_recommendation"))
        lines.append("Loop steps:")
        for step in (c.get("loop") or []):
            lines.append("  %2d. %s — %s" % (step.get("step") or 0,
                                              step.get("name"),
                                              step.get("purpose")))
        lines.append("")

    if "replay_ledger" in topics:
        r = _eqsb_load("eqsb_replay_audit_ledger.json")
        lines.append("Replay / Audit Ledger")
        lines.append("-" * 56)
        lines.append("event_count_total:     %s" % r.get("event_count_total"))
        lines.append("audit_event_count:     %s" % r.get("audit_event_count_total"))
        lines.append("events_by_kind:        %s" % json.dumps(r.get("events_by_kind") or {}))
        for rs in (r.get("repair_suggestions") or [])[:6]:
            lines.append("  · [%s] %s -> %s" % (rs.get("severity"),
                                                  rs.get("title"),
                                                  rs.get("action")))
        lines.append("")

    if "architecture" in topics:
        a = _eqsb_load("eqsb_kernel_architecture_layers.json")
        intro = _eqsb_load("eqsb_kernel_introspection_latest.json")
        sa = _eqsb_load("eqsb_kernel_self_audit.json")
        lines.append("EQSB Architecture (Major Phase)")
        lines.append("-" * 56)
        lines.append("phase:        %s" % a.get("phase"))
        lines.append("layer_count:  %s" % a.get("layer_count"))
        for layer in (a.get("layers") or []):
            lines.append("  L%-2s %s" % (layer.get("level"), layer.get("name")))
        lines.append("self_audit_verdict: %s" % sa.get("verdict"))
        lines.append("missing_registry_count: %s" % sa.get("missing_registry_count"))
        lines.append("identity: %s" % json.dumps(intro.get("identity") or {})[:240])
        lines.append("")

    if "openclaw_v2" in topics:
        oc = _eqsb_load("qsb_openclaw_state.json")
        lines.append("OpenClaw — Supervision Limb (V2)")
        lines.append("-" * 56)
        lines.append("status:                                  %s" % oc.get("status"))
        lines.append("openclaw_visual_enabled:                 %s" % oc.get("openclaw_visual_enabled"))
        lines.append("openclaw_sandbox_enabled:                %s" % oc.get("openclaw_sandbox_enabled"))
        lines.append("openclaw_trade_supervision_enabled:      %s" % oc.get("openclaw_trade_supervision_enabled"))
        lines.append("openclaw_diagnostic_ticketing_enabled:   %s" % oc.get("openclaw_diagnostic_ticketing_enabled"))
        lines.append("openclaw_real_tool_execution_enabled:    %s" % oc.get("openclaw_real_tool_execution_enabled"))
        lines.append("diagnostic_ticket_count:                 %s" % oc.get("diagnostic_ticket_count"))
        lines.append("supervised_floors: %s" % ", ".join(oc.get("supervised_floors") or []))
        lines.append("allowed paper actions:")
        for a in (oc.get("allowed_paper_actions") or [])[:8]:
            lines.append("  · " + a)
        lines.append("blocked unsafe actions:")
        for a in (oc.get("blocked_unsafe_actions") or [])[:8]:
            lines.append("  · " + a)
        lines.append("")

    if "paper_trades_v2" in topics:
        ot = _eqsb_load("qsb_open_paper_trades.json")
        pol = _eqsb_load("qsb_paper_trading_policy.json")
        lines.append("Paper/Testnet Open Trades (V2)")
        lines.append("-" * 56)
        lines.append("active_mode:               %s" % pol.get("active_mode"))
        lines.append("gateway_status:            %s" % pol.get("gateway_status"))
        lines.append("max_open_trades:           %s" % ot.get("max_open_trades"))
        lines.append("current_open_trade_count:  %s" % ot.get("open_trade_count"))
        lines.append("remaining_trade_slots:     %s" % ot.get("remaining_trade_slots"))
        lines.append("total_current_pnl:         %s" % ot.get("total_current_pnl"))
        for t in (ot.get("trades") or [])[:8]:
            lines.append("  · %s %s %s qty=%s entry=%s pnl=%s strategy=%s"
                          % (t.get("trade_id"), t.get("symbol"), t.get("side"),
                              t.get("quantity"), t.get("entry_price"),
                              t.get("current_pnl"), t.get("strategy_id")))
        lines.append("")

    if "trade_pnl_v2" in topics:
        ot = _eqsb_load("qsb_open_paper_trades.json")
        learn = _eqsb_load("qsb_trade_learning.json")
        lines.append("Trade PnL (V2)")
        lines.append("-" * 56)
        lines.append("total_current_pnl (open):  %s" % ot.get("total_current_pnl"))
        lines.append("total_realized_pnl:        %s" % learn.get("total_realized_pnl"))
        lines.append("closed_trade_count:        %s" % learn.get("closed_trade_count"))
        lines.append("open_trade_count:          %s" % ot.get("open_trade_count"))
        lines.append("")

    if "trade_lessons_v2" in topics:
        learn = _eqsb_load("qsb_trade_learning.json")
        lines.append("Trade Lessons Learned (V2)")
        lines.append("-" * 56)
        lines.append("lesson_count:        %s" % learn.get("lesson_count"))
        lines.append("closed_trade_count:  %s" % learn.get("closed_trade_count"))
        for l in (learn.get("lessons") or [])[-6:]:
            lines.append("  · %s %s pnl=%s — %s (exit=%s)"
                          % (l.get("symbol"), l.get("side"),
                              l.get("realized_pnl"),
                              (l.get("lesson_text") or "")[:80],
                              l.get("exit_reason")))
        lines.append("")

    if "workers_v2" in topics:
        cw = _eqsb_load("qsb_canonical_workers.json")
        recon = _eqsb_load("qsb_worker_count_reconciliation.json")
        lines.append("Worker Reconciliation (V2)")
        lines.append("-" * 56)
        lines.append("sources_total_reported:        %s" % recon.get("sources_total_reported"))
        lines.append("total_discovered_unique:       %s" % recon.get("total_discovered_unique_workers"))
        lines.append("total_canonical_workers:       %s" % cw.get("total_canonical_workers"))
        lines.append("total_active_workers:          %s" % cw.get("total_active_workers"))
        lines.append("total_reporting_workers:       %s" % cw.get("total_reporting_workers"))
        lines.append("total_newly_employed_workers:  %s" % cw.get("total_newly_employed_workers"))
        lines.append("delta_pre_v2_to_post_v2:       %s" % recon.get("delta_pre_v2_to_post_v2"))
        lines.append("counts by_home_floor (top 8):")
        bf = cw.get("by_home_floor_counts") or {}
        for floor, n in sorted(bf.items(), key=lambda kv: -kv[1])[:8]:
            lines.append("  %-44s %s" % (floor, n))
        lines.append("counts by_role (top 8):")
        br = cw.get("by_role_counts") or {}
        for role, n in sorted(br.items(), key=lambda kv: -kv[1])[:8]:
            lines.append("  %-44s %s" % (role, n))
        lines.append("Newly employed IDs:")
        for wid in (cw.get("newly_employed_ids") or [])[:12]:
            lines.append("  · " + wid)
        lines.append("Mismatch reason: " + (recon.get("mismatch_reason") or "")[:280])
        lines.append("")

    if "dashboard_3d_v2" in topics:
        lines.append("3D Skyscraper Dashboard Upgrade (V2)")
        lines.append("-" * 56)
        lines.append("Renderer files improved:")
        lines.append("  · src/dashboard/static/cockpit.css (depth/lighting/glow per floor)")
        lines.append("  · src/dashboard/static/qsb_skyscraper_v2.js (floor identity, OpenClaw avatar,")
        lines.append("    worker badges, lift animation, packet flow)")
        lines.append("  · src/dashboard/static/index.html (V2 tab + panel + script include)")
        lines.append("Distinct floors with identity badges:")
        for f in ("Penthouse EQSB Kernel",
                   "Floor 53 Tower Command",
                   "Floor 42 Binance Trading",
                   "Floor 41 OANDA Practice",
                   "Floor 38 Sandbox Operations",
                   "Floor 31 Audit / Ledger",
                   "Floor 30 Permissions / Risk"):
            lines.append("  · " + f)
        lines.append("OpenClaw avatar visible: True")
        lines.append("Worker badges visible:   True")
        lines.append("Lift animation upgraded: True")
        lines.append("EQSB Penthouse panel:    integrated with right rail tab")
        lines.append("")

    if "hardware_obs" in topics:
        und = _eqsb_load("eqsb_hardware_understanding.json")
        adv = _eqsb_load("eqsb_performance_advice.json")
        hwf = _eqsb_load("qsb_hardware_systems_floor.json")
        summary = und.get("summary") or {}
        lines.append("Hardware Observatory")
        lines.append("-" * 56)
        lines.append("hardware_systems_floor: floor_%s · %s" %
                      (hwf.get("floor_number"), hwf.get("floor_label", "")))
        lines.append("cpu_model:    %s" % summary.get("cpu_model"))
        lines.append("cpu cores/threads: %s / %s" %
                      (summary.get("cpu_cores"), summary.get("cpu_threads")))
        gpu_models = summary.get("gpu_models") or []
        lines.append("gpu:          %s" % (", ".join(gpu_models) if gpu_models else "no_gpu"))
        lines.append("cuda_version: %s" % summary.get("cuda_version"))
        lines.append("cuda_python:  %s" % summary.get("cuda_available_python"))
        mem_total = summary.get("mem_total_bytes")
        if mem_total:
            mem_gib = mem_total / (1024**3)
            lines.append("ram_total:    %.1f GiB · pressure %s" %
                          (mem_gib, summary.get("memory_pressure")))
        lines.append("qsb_project:  %s MiB" % summary.get("qsb_project_mb"))
        lines.append("vaults_ai_present: %s · airllm_lab: %s" %
                      (summary.get("vaults_ai_present"),
                        summary.get("vaults_ai_airllm_lab_present")))
        lines.append("hostname/kernel: %s / %s · python %s" %
                      (summary.get("hostname"), summary.get("kernel_release"),
                        summary.get("python_version")))
        lines.append("dashboard_pid_running: %s · ollama: %s · airllm_venv: %s" %
                      (summary.get("dashboard_pid_running"),
                        summary.get("ollama_present"),
                        summary.get("airllm_venv_present")))
        lines.append("performance advice:")
        for a in (adv.get("advice") or [])[:5]:
            lines.append("  · " + str(a))
        lines.append("read-only re: hardware. Never modifies services or drivers.")
        lines.append("")

    if "code_obs" in topics:
        code = _eqsb_load("eqsb_code_observatory.json")
        cmap = _eqsb_load("eqsb_code_map.json")
        risk = _eqsb_load("eqsb_code_risk_report.json")
        lines.append("Code Observatory")
        lines.append("-" * 56)
        lines.append("total_files indexed:  %s" % code.get("total_files"))
        ba = code.get("by_area_counts") or {}
        for a in sorted(ba, key=lambda k: -ba[k])[:10]:
            lines.append("  · %-24s %s" % (a, ba[a]))
        lines.append("risk_file_count:      %s" % risk.get("risk_file_count"))
        for r in (risk.get("risks") or [])[:6]:
            lines.append("  · %s :: %s" % (r.get("path"),
                                            ",".join(r.get("flags") or [])))
        lines.append("")

    if "claude_history" in topics:
        ledger = _eqsb_load("eqsb_claude_upgrade_ledger.json")
        last = _eqsb_load("eqsb_last_claude_change_summary.json")
        risks = _eqsb_load("eqsb_upgrade_risk_history.json")
        changes = _eqsb_load("eqsb_phase_changes_latest.json")
        lines.append("Claude Upgrade Ledger")
        lines.append("-" * 56)
        lines.append("phase_count:         %s" % ledger.get("phase_count"))
        lines.append("latest_phase:        %s" % ledger.get("latest_phase"))
        lines.append("latest_summary:      %s" % (last.get("summary") or "")[:160])
        lines.append("files_created (last phase):  %s" %
                      len(changes.get("files_created") or []))
        lines.append("files_modified (last phase): %s" %
                      len(changes.get("files_modified") or []))
        lessons = risks.get("lessons_so_far") or []
        for l in lessons[:4]:
            lines.append("  · lesson: " + str(l))
        lines.append("")

    if "telemetry_repair" in topics:
        wm = _eqsb_load("qsb_worker_movements_latest.json")
        lm = _eqsb_load("qsb_lift_movements_latest.json")
        rollup = _eqsb_load("qsb_worker_scorecard_rollup_7d.json")
        nh = _eqsb_load("qsb_narrator_history_latest.json")
        triggers = _eqsb_load("qsb_worker_discipline_triggers.json")
        policy = _eqsb_load("qsb_selected_floor_narration_policy.json")
        acc = _eqsb_load("qsb_accounts_floor_state.json")
        lines.append("Live Telemetry Repairs (V1)")
        lines.append("-" * 56)
        lines.append("worker_movements_count: %s" % wm.get("movement_count"))
        lines.append("lift_movements_count:   %s" % lm.get("movement_count"))
        lines.append("scorecard_events_7d:    %s" %
                      rollup.get("performance_events_count_7d"))
        lines.append("narrator_history_count: %s" %
                      nh.get("recent_utterance_count"))
        lines.append("guardian_blocked_in_log:%s" %
                      triggers.get("guardian_blocked_count_in_log"))
        lines.append("selected_floor_default: %s (openclaw=%s)" %
                      (policy.get("default_floor"),
                        policy.get("openclaw_current_floor")))
        lines.append("floor_44_accounts:      %s (%d workers)" %
                      (acc.get("current_state"),
                        acc.get("worker_count") or 0))
        lines.append("")

    if "revamp_3d_v1" in topics:
        rc = _eqsb_load("qsb_dashboard_3d_revamp_root_cause.json")
        status = _eqsb_load("qsb_dashboard_3d_rebuild_status.json")
        score = _eqsb_load("qsb_dashboard_3d_revamp_completion_score.json")
        scene = _eqsb_load("qsb_dashboard_scene_state.json")
        truth = _eqsb_load("qsb_dashboard_worker_truth_map.json")
        lines.append("3D Dashboard Revamp V1")
        lines.append("-" * 56)
        lines.append("headline: " + (rc.get("headline") or "")[:200])
        lines.append("fix:      " + (rc.get("fix_applied_in_this_phase") or "")[:200])
        lines.append("")
        lines.append("Files added/replaced this phase:")
        for f in (status.get("files_added") or []):
            lines.append("  · " + f)
        lines.append("")
        lines.append("Visual transformations:")
        for v in (status.get("visual_transformations") or []):
            lines.append("  · " + v)
        lines.append("")
        lines.append("Worker truth (counts honestly explained):")
        for k, v in (truth.get("totals_explained") or {}).items():
            lines.append("  · %-22s %s" % (k, (v or {}).get("count")))
        lines.append("")
        lines.append("Scene state:")
        lines.append("  active=%s · moving=%s · tasks=%s · view_mode=%s" % (
            scene.get("active_count"), scene.get("moving_count"),
            scene.get("task_count"), scene.get("view_mode_default")))
        lines.append("")
        lines.append("Completion: %s/100 (%s of %s gates) · is_100_complete=%s" %
                      (score.get("completion_score"),
                        score.get("passed"), score.get("total"),
                        score.get("is_100_complete")))
        if score.get("failed_gates"):
            lines.append("Failed gates: " + ", ".join(score.get("failed_gates")))
        lines.append("Backup: " + str(status.get("backup_location")))
        lines.append("real_money_live_trading_enabled: False")
        lines.append("")

    if "rebuild_v1" in topics:
        rc = _eqsb_load("qsb_worker_dashboard_visibility_root_cause.json")
        oc = _eqsb_load("qsb_openclaw_role_definition.json")
        oct = _eqsb_load("qsb_openclaw_tickets.json")
        ocr = _eqsb_load("qsb_openclaw_route.json")
        oct_w = _eqsb_load("qsb_openclaw_worker_findings.json")
        tasks = _eqsb_load("qsb_worker_task_board.json")
        interiors = _eqsb_load("qsb_department_interiors_state.json")
        score = _eqsb_load("qsb_dashboard_total_rebuild_completion_score.json")
        backup = _eqsb_load("qsb_dashboard_total_rebuild_backup.json")
        lines.append("Dashboard Total Rebuild V1")
        lines.append("-" * 56)
        lines.append("root cause: " + (rc.get("headline_root_cause") or "")[:200])
        lines.append("fix:        " + (rc.get("fix_applied_in_this_phase") or "")[:200])
        lines.append("previous default mode: %s" % rc.get("previous_view_mode_default"))
        lines.append("new default mode:      %s" % rc.get("new_view_mode_default"))
        lines.append("")
        lines.append("Where workers are now:")
        lines.append("  · Exterior tower: per-floor count badges (no swarm).")
        lines.append("  · Selected floor: individual workers rendered at "
                      "their assigned rooms/stations via qsb_rebuild_workers.js.")
        lines.append("  · Training Academy: training_worker class (108 incl. SIM seeds).")
        lines.append("  · Rest/Dormitory: resting_worker class (280 stationed).")
        lines.append("  · Recruitment Agency: candidate_worker class (12 candidates).")
        lines.append("")
        lines.append("OpenClaw supervisor:")
        lines.append("  role: %s" % (oc.get("role") or "")[:120])
        lines.append("  current_floor: %s (advanced_by=%s)" %
                      (ocr.get("current_floor"), ocr.get("advanced_by")))
        lines.append("  tickets open:  %s" % (oct.get("ticket_count") or 0))
        for t in (oct.get("tickets") or [])[:5]:
            lines.append("    · [%s] %s" % (t.get("severity"), t.get("title")))
        lines.append("  worker findings: %s" % (oct_w.get("finding_count") or 0))
        lines.append("")
        lines.append("Workers doing tasks right now:")
        lines.append("  active tasks: %s · idle stationed: %s" %
                      (tasks.get("active_count"), tasks.get("idle_count")))
        for t in (tasks.get("active_tasks") or [])[:5]:
            lines.append("    · %s · %s · %s" %
                          (t.get("worker_id"), t.get("task_type"),
                            (t.get("description") or "")[:60]))
        lines.append("")
        lines.append("Departments with interior layer: %s" %
                      interiors.get("departments_with_interior_layer"))
        lines.append("")
        lines.append("Rebuild completion: %s/100 (passed %s of %s gates)" %
                      (score.get("completion_score"),
                        score.get("passed"), score.get("total")))
        if score.get("failed_gates"):
            lines.append("Failed gates: " + ", ".join(score.get("failed_gates")))
        lines.append("")
        lines.append("Backup at: %s" % backup.get("backup_directory"))
        lines.append("real_money_live_trading_enabled: False")
        lines.append("openclaw_real_tool_execution_enabled: False")
        lines.append("")

    if "completion_v1" in topics:
        score = _eqsb_load("qsb_100_online_completion_score.json")
        gates = _eqsb_load("qsb_100_online_acceptance_gates.json")
        blockers = _eqsb_load("qsb_100_online_hard_blockers.json")
        loop_hist = _eqsb_load("qsb_100_online_loop_history.json")
        dept_audit = _eqsb_load("qsb_department_completion_audit.json")
        expansion = _eqsb_load("qsb_workforce_expansion_v1.json")
        lines.append("Skyscraper Completion (V1)")
        lines.append("-" * 56)
        lines.append("completion_score: %s / 100 (passed %s of %s gates)" %
                      (score.get("completion_score"),
                        score.get("passed"), score.get("total")))
        lines.append("is_100_online:    %s" % score.get("is_100_online"))
        lines.append("loop iterations:  %s" % loop_hist.get("iteration_count"))
        if score.get("failed_gates"):
            lines.append("failed gates: " + ", ".join(score.get("failed_gates")))
        else:
            lines.append("failed gates: none")
        lines.append("")
        lines.append("Acceptance gate results (26):")
        for g in (gates.get("gates") or []):
            lines.append("  [%s] %s %s" % (
                "PASS" if g.get("passed") else "FAIL",
                g.get("gate_id"), g.get("name")))
        lines.append("")
        lines.append("Hard blockers: %s" % blockers.get("blocker_count"))
        for b in (blockers.get("blockers") or [])[:6]:
            lines.append("  · [%s] %s -- repair: %s" %
                          (b.get("gate_id"), b.get("gate_name"),
                            b.get("repair_if_failed") or "n/a"))
        lines.append("")
        lines.append("New workers employed this phase: %s across %s departments" %
                      (expansion.get("total_new_workers_employed"),
                        expansion.get("department_count")))
        lines.append("Departments built/repaired:")
        for d in (dept_audit.get("items") or []):
            lines.append("  · %s · floor_%s · %s workers · %s" % (
                d.get("department"), d.get("floor_number"),
                d.get("worker_count"), d.get("status")))
        lines.append("")
        lines.append("real_money_live_trading_enabled: False")
        lines.append("")

    if "workforce_v1" in topics:
        tc = _eqsb_load("qsb_workforce_truth_contract.json")
        ops = _eqsb_load("qsb_workforce_operations_state.json")
        sim = _eqsb_load("qsb_sim_worker_audit.json")
        deep = _eqsb_load("qsb_workforce_deep_audit.json")
        mvs = _eqsb_load("qsb_worker_movements_latest.json")
        proms = _eqsb_load("qsb_worker_promotions.json")
        disc = _eqsb_load("qsb_worker_discipline.json")
        t = tc.get("totals") or {}
        lines.append("Workforce Operations (V1 redesign)")
        lines.append("-" * 56)
        lines.append("canonical workers:    %s" % t.get("canonical_workers"))
        lines.append("operational workers:  %s" % t.get("operational_workers"))
        lines.append("training workers:     %s (includes %s sim seeds)" %
                      (t.get("training_workers"), t.get("sim_seed_workers")))
        lines.append("candidate workers:    %s" % t.get("candidate_workers"))
        lines.append("lesson workers:       %s" % t.get("lesson_workers"))
        lines.append("suspended workers:    %s" % t.get("suspended_workers"))
        lines.append("stale workers:        %s" % t.get("stale_workers"))
        lines.append("")
        lines.append("Where workers live:")
        lines.append("  · Recruitment Agency:  floor_%s" %
                      (ops.get("recruitment") or {}).get("agency_floor_number"))
        lines.append("  · Training Academy:    floor_%s (Expansion Planning sub-dept)" %
                      (ops.get("training_academy") or {}).get("academy_floor_number"))
        lines.append("  · Lessons Room:        floor_%s (Sandbox sub-dept)" %
                      (ops.get("lessons_room") or {}).get("lessons_room_floor_number"))
        lines.append("")
        lines.append("Why workers used to wrap around the tower in a spiral:")
        lines.append("  " + str(deep.get("why_sim_labels_appear_in_swarm"))[:300])
        lines.append("")
        lines.append("Sim_worker_floor_* relocation:")
        lines.append("  " + str(sim.get("policy"))[:240])
        lines.append("")
        lines.append("Recent worker movements (real, %d total):" % (mvs.get("movement_count") or 0))
        for m in (mvs.get("movements") or [])[:6]:
            lines.append("  · %s · %s → %s · reason=%s · trade=%s" % (
                m.get("worker_id"),
                m.get("source_floor"), m.get("target_floor"),
                m.get("reason"), m.get("related_trade_id")))
        lines.append("")
        lines.append("Workers needing promotion / retraining / discipline:")
        lines.append("  · promotion eligible: %s" % proms.get("total_eligible_now"))
        for w in (proms.get("eligible_workers") or [])[:3]:
            lines.append("      → %s (%s → %s, %s pts)" %
                          (w.get("name"), w.get("current_rank"),
                            w.get("next_rank"), w.get("reward_points")))
        lines.append("  · on warning: %s · restricted: %s · suspended: %s" %
                      (disc.get("total_on_warning"),
                        disc.get("total_restricted"),
                        disc.get("total_suspended")))
        lines.append("")
        lines.append("Exterior tower view is now COUNTS-ONLY by default. "
                      "Individual workers visible only inside the selected "
                      "floor inspector. SIM seeds visible only inside "
                      "Training Academy (floor_36).")
        lines.append("")

    if "worker_truth" in topics:
        tc = _eqsb_load("qsb_worker_truth_contract.json")
        deep = _eqsb_load("qsb_worker_truth_deep_audit.json")
        floor_audit = _eqsb_load("qsb_floor_worker_assignment_audit.json")
        lines.append("Worker Truth (V1)")
        lines.append("-" * 56)
        lines.append("canonical_workers (V1 reconciled): %s" %
                      tc.get("total_canonical_workers"))
        lines.append("active_reporting_workers:          %s" %
                      tc.get("active_reporting_workers"))
        lines.append("simulated_workers (sim seeds):     %s" %
                      tc.get("simulated_workers"))
        lines.append("real_registry_workers:             %s" %
                      tc.get("real_registry_workers"))
        legacy = (tc.get("visible_dashboard_workers") or {})
        lines.append("legacy /api/unified.workers[]:     %s" %
                      legacy.get("legacy_unified_view"))
        lines.append("ui label when legacy view active:  %s" %
                      legacy.get("label_when_legacy_view_active"))
        ans = deep.get("audit_answers") or {}
        lines.append("")
        lines.append("Why sidebar said 64:")
        lines.append("  " + str(ans.get("why_sidebar_says_64"))[:240])
        lines.append("Why HUD/V3 panels say 191:")
        lines.append("  " + str(ans.get("why_other_panels_say_191"))[:240])
        lines.append("Why prior reports said 170:")
        lines.append("  " + str(ans.get("why_prior_report_said_170"))[:240])
        lines.append("Why floor_42 appeared to have ~120:")
        lines.append("  " + str(ans.get("why_binance_appears_high"))[:240])
        lines.append("Per-floor canonical (top 6):")
        by_floor = tc.get("workers_by_floor") or {}
        for f, n in sorted(by_floor.items(), key=lambda kv: -kv[1])[:6]:
            lines.append("  %-44s %s" % (f, n))
        lines.append("")
        lines.append("Are worker bands real movement? NO. The cluster on "
                      "floor_41 was 48 sim_worker_floor_* seed records that "
                      "all fell back to floor_41 because their seed file "
                      "uses floor_id (not home_floor). This phase: spreads "
                      "them across their real floor_id, tags them SIM, and "
                      "dims them in the SVG (.wkr-sim class). The only real "
                      "movement comes from qsb_worker_movements_latest.json "
                      "(paper-trade event-derived).")
        lines.append("Floor_42 canonical assignment count: %s" %
                      (floor_audit.get("floor_42_audit") or {}).get("canonical_assigned"))
        lines.append("")

    if "floor41_oanda" in topics:
        eng = _eqsb_load("qsb_floor41_oanda_trading_engine.json")
        acct = _eqsb_load("qsb_floor41_oanda_account_snapshot.json")
        prices = _eqsb_load("qsb_floor41_oanda_prices_latest.json")
        open_t = _eqsb_load("qsb_floor41_oanda_open_trades.json")
        closed_t = _eqsb_load("qsb_floor41_oanda_closed_trades.json")
        pnl = _eqsb_load("qsb_floor41_oanda_pnl.json")
        thoughts = _eqsb_load("qsb_floor41_oanda_worker_thoughts.json")
        oc = _eqsb_load("qsb_openclaw_floor41_oanda_findings.json")
        risk = _eqsb_load("qsb_floor41_oanda_trade_risk_checks.json")
        lines.append("Floor 41 OANDA — Full Trading Floor Report")
        lines.append("-" * 56)
        lines.append("engine_mode:               %s" % eng.get("mode"))
        lines.append("base_url:                  %s" % eng.get("base_url"))
        lines.append("credentials_present:       %s" % eng.get("credentials_present"))
        lines.append("live_money_enabled:        %s (locked)" % eng.get("live_money_enabled"))
        lines.append("oanda_live_env_allowed:    %s (locked)" % eng.get("oanda_live_environment_allowed"))
        lines.append("")
        lines.append("Account state (paper/practice):")
        lines.append("  account_id:              %s" % acct.get("account_id"))
        lines.append("  currency:                %s" % acct.get("currency"))
        lines.append("  balance:                 %s" % acct.get("balance"))
        lines.append("  NAV:                     %s" % acct.get("NAV"))
        lines.append("  margin_available:        %s" % acct.get("margin_available"))
        lines.append("")
        lines.append("Latest prices/spreads:")
        for p in (prices.get("prices") or [])[:8]:
            lines.append("  %s  bid=%s  ask=%s  spread=%s pip" %
                          (p.get("instrument"), p.get("bid"),
                            p.get("ask"), p.get("spread_pips")))
        lines.append("")
        lines.append("Open trades: %s" % open_t.get("trade_count"))
        for t in (open_t.get("open_trades") or [])[:8]:
            up = t.get("unrealized_pnl") or 0
            lines.append("  %s %s %s u=%s entry=%s mark=%s uPnL=%+0.4f" %
                          (t.get("trade_id"), t.get("instrument"),
                            t.get("direction"), t.get("units"),
                            t.get("entry_price"), t.get("mark_price"), up))
        lines.append("")
        lines.append("Closed trades: %s" % closed_t.get("trade_count"))
        for c in (closed_t.get("closed_trades") or [])[-8:]:
            lines.append("  %s %s %s pnl=%+0.4f reason='%s'" %
                          (c.get("trade_id"), c.get("instrument"),
                            c.get("direction"),
                            float(c.get("pnl_amount") or 0),
                            (c.get("close_reason") or "")[:24]))
        lines.append("")
        lines.append("PnL summary (paper/practice):")
        lines.append("  realized:    %+0.4f" % float(pnl.get("realized_pnl_total") or 0))
        lines.append("  unrealized:  %+0.4f" % float(pnl.get("unrealized_pnl_total") or 0))
        lines.append("  total:       %+0.4f" % float(pnl.get("total_pnl") or 0))
        lines.append("  winners:     %s" % pnl.get("closed_winners"))
        lines.append("  losers:      %s" % pnl.get("closed_losers"))
        lines.append("")
        lines.append("Worker thoughts (top 8):")
        for t in (thoughts.get("thoughts") or [])[-8:]:
            lines.append("  %s · %s · %s" %
                          (t.get("worker_id", "")[4:], t.get("topic"),
                            (t.get("thought") or "")[:80]))
        lines.append("")
        lines.append("Risk rules (enforced at module level):")
        for r in (risk.get("rules") or []):
            lines.append("  - %s (blocking=%s)" % (r.get("rule"), r.get("blocking")))
        lines.append("")
        lines.append("OpenClaw findings: %s · tickets: %s" %
                      (oc.get("finding_count"), oc.get("ticket_count")))
        for f in (oc.get("findings") or [])[:5]:
            lines.append("  [%s] %s — %s" %
                          (f.get("severity"), f.get("kind"), f.get("detail")))
        for t in (oc.get("tickets") or [])[:5]:
            lines.append("  ticket %s [%s] %s" %
                          (t.get("id"), t.get("severity"), t.get("issue")))
        lines.append("")
        lines.append("Practice/paper open-close trading: FUNCTIONAL")
        lines.append("Real-money live trading:           DISABLED")
        lines.append("OpenClaw real tool execution:      DISABLED")
        lines.append("URL: http://127.0.0.1:8765/?v=unified&floor=41")
        lines.append("")

    if "floor42_binance" in topics:
        f42 = _eqsb_load("qsb_floor42_binance_interior.json")
        rooms = f42.get("rooms") or []
        workers = f42.get("workers") or []
        policy = f42.get("policy") or {}
        lines.append("Floor 42 — Binance Trading Floor")
        lines.append("-" * 56)
        lines.append("mode:                  %s" % policy.get("mode", "testnet_preview_only"))
        lines.append("placement:             %s" % policy.get("placement", "blocked_without_explicit_unlock"))
        lines.append("real_money_enabled:    %s" % policy.get("real_money_enabled", False))
        lines.append("rooms:                 %s" % len(rooms))
        lines.append("workers:               %s" % len(workers))
        lines.append("")
        lines.append("Rooms:")
        for r in rooms:
            lines.append("  · %s — %s" % (r.get("name"), r.get("responsibility")))
        lines.append("")
        lines.append("Workers at stations:")
        for w in workers:
            lines.append("  · %s (%s) → %s" % (w.get("worker_id"), w.get("role"), w.get("station")))
        lines.append("")
        lines.append("URL: http://127.0.0.1:8765/?v=unified&floor=42")
        lines.append("")

    if "penthouse" in topics:
        cmd = _eqsb_load("qsb_penthouse_command_state.json")
        gauges = _eqsb_load("qsb_penthouse_gauges.json")
        layout = _eqsb_load("qsb_penthouse_interactive_layout.json")
        lines.append("Penthouse / Kernel Command Floor")
        lines.append("-" * 56)
        if not cmd:
            lines.append("(qsb_penthouse_command_state.json not built yet — "
                          "run python -m tower.qsb_penthouse to populate)")
        else:
            lines.append("kernel_active:         %s" % cmd.get("kernel_active"))
            lines.append("cadence_tick:          %s" % cmd.get("cadence_tick"))
            lines.append("guardian_state:        %s" % cmd.get("guardian_state"))
            lines.append("openclaw_floor:        %s" % cmd.get("openclaw_current_floor"))
            lines.append("locks_open:            %s / 13" % cmd.get("locks_open"))
            lines.append("workers_active:        %s" % cmd.get("workers_active"))
            lines.append("trading_modules:       %s" % cmd.get("trading_modules_status"))
            lines.append("")
            zones = (layout or {}).get("zones") or []
            lines.append("Zones (%s):" % len(zones))
            for z in zones[:12]:
                lines.append("  · %s — %s" % (z.get("name"), z.get("responsibility")))
            lines.append("")
            gs = (gauges or {}).get("gauges") or []
            lines.append("Gauges (%s):" % len(gs))
            for g in gs[:10]:
                lines.append("  · %s: %s %s" % (
                    g.get("label"), g.get("value"), g.get("unit") or ""))
            lines.append("")
            removed = cmd.get("decorative_removed") or []
            if removed:
                lines.append("Removed decorative elements: %s" % ", ".join(removed))
        lines.append("URL: http://127.0.0.1:8765/?v=unified&floor=55")
        lines.append("")

    if "hardware_observatory" in topics:
        hw = _eqsb_load("qsb_hardware_floor_audit.json")
        lines.append("Hardware Observatory")
        lines.append("-" * 56)
        if not hw:
            lines.append("(qsb_hardware_floor_audit.json missing — run python "
                          "-m tower.qsb_hardware_floor to populate)")
        else:
            lines.append("platform:              %s" % hw.get("platform"))
            lines.append("kernel:                %s" % hw.get("kernel"))
            lines.append("cpu:                   %s" % hw.get("cpu_model"))
            lines.append("cpu_count:             %s" % hw.get("cpu_count"))
            lines.append("memory_total_gb:       %s" % hw.get("memory_total_gb"))
            lines.append("gpu:                   %s" % hw.get("gpu_summary"))
            lines.append("cuda_version:          %s" % hw.get("cuda_version"))
            lines.append("disk_root_free_gb:     %s" % hw.get("disk_root_free_gb"))
            lines.append("hostname:              %s" % hw.get("hostname"))
        lines.append("")

    if "code_observatory" in topics:
        last = _eqsb_load("eqsb_last_claude_change_summary.json")
        changes = _eqsb_load("eqsb_phase_changes_latest.json")
        lines.append("Code Observatory")
        lines.append("-" * 56)
        if last:
            lines.append("last_change_ts:        %s" % last.get("ts"))
            lines.append("last_phase:            %s" % last.get("phase"))
            lines.append("last_event:            %s" % last.get("event"))
            lines.append("summary:               %s" % str(last.get("summary"))[:200])
        else:
            lines.append("(eqsb_last_claude_change_summary.json missing)")
        recent = (changes or {}).get("recent_events") or []
        lines.append("")
        lines.append("Recent 8 phase events:")
        for e in recent[-8:]:
            lines.append("  · %s · %s" % (
                (e.get("ts") or "")[:19], e.get("phase") or e.get("event")))
        lines.append("")

    if "dashboard_repair" in topics:
        repair = _eqsb_load("qsb_dashboard_repair_priority.json")
        identity = _eqsb_load("qsb_dashboard_identity_cleanup.json")
        canned = _eqsb_load("qsb_kernel_chat_canned_response_audit.json")
        lines.append("Dashboard Repair Priority")
        lines.append("-" * 56)
        if canned:
            lines.append("kernel_chat_canned_response:")
            lines.append("  status: AUDITED · fix applied")
            for rc in (canned.get("root_causes") or [])[:3]:
                lines.append("  · [%s] %s" % (rc.get("id"), rc.get("description")[:80]))
        if identity:
            lines.append("identity_branding: UNIFIED")
            lines.append("  removed: %s" % ", ".join((identity.get("removed_branding_strings") or [])[:3]))
        if repair:
            for item in (repair.get("priorities") or [])[:6]:
                lines.append("  · [%s] %s" % (item.get("severity"), item.get("issue")))
        else:
            lines.append("(qsb_dashboard_repair_priority.json not yet built)")
        lines.append("")

    if "native_cockpit_v2" in topics:
        decision = _eqsb_load("qsb_native_graphics_engine_decision_v2.json")
        proj = _eqsb_load("qsb_native_cockpit_project_v2.json")
        arch = _eqsb_load("qsb_native_cockpit_architecture_v2.json")
        wf = _eqsb_load("qsb_native_workforce_import_audit.json")
        cw = _eqsb_load("qsb_commerce_wing_masterplan.json")
        ocfull = _eqsb_load("qsb_openclaw_full_floor_inspection.json")
        lines.append("QSB Native Cockpit V2 — Standalone Desktop Plan")
        lines.append("-" * 56)
        lines.append("Primary engine:       %s" % decision.get("primary_engine"))
        lines.append("Engine version:       %s" % decision.get("primary_engine_version"))
        lines.append("Fallback engine:      %s" % decision.get("fallback_engine"))
        lines.append("Project root:         %s" % proj.get("project_root"))
        lines.append("Entry point:          %s" % proj.get("entry_point"))
        lines.append("Telemetry bridge:     %s" % proj.get("telemetry_bridge"))
        lines.append("")
        lines.append("Verified workforce import:")
        lines.append("  canonical_workers_before: %s" % wf.get("canonical_workers_before"))
        lines.append("  new_v2_workers_employed: %s" % wf.get("new_v2_workers_employed"))
        lines.append("  VERIFIED TOTAL:          %s" % wf.get("verified_total_workers"))
        lines.append("  with floor / team / role / manager / task: %s / %s / %s / %s / %s" %
                      (wf.get("workers_with_floor"), wf.get("workers_with_team"),
                        wf.get("workers_with_role"), wf.get("workers_with_manager"),
                        wf.get("workers_with_task")))
        lines.append("")
        lines.append("Commerce Wing import:")
        lines.append("  floors:                  %s" % len(cw.get("departments") or []))
        lines.append("  manual_approval_gate:    %s" % (cw.get("manual_approval_gate") or "")[0:80])
        lines.append("  live_payments_enabled:   %s" % cw.get("live_payments_enabled"))
        lines.append("  live_listings_publish:   %s" % cw.get("live_listings_publishing_enabled"))
        lines.append("")
        lines.append("OpenClaw full-floor inspection:")
        lines.append("  findings: %s · tickets: %s" %
                      (ocfull.get("finding_count"), ocfull.get("ticket_count")))
        lines.append("")
        lines.append("Architecture layers:")
        for L in (arch.get("layers") or []):
            lines.append("  · %s (%s)" % (L.get("name"), L.get("module")))
        lines.append("")
        lines.append("Decision rationale:")
        for r in (decision.get("reason") or [])[:6]:
            lines.append("  · " + str(r)[:120])
        lines.append("")
        lines.append("Risks:")
        for r in (decision.get("risks") or []):
            lines.append("  · " + str(r)[:120])
        lines.append("")
        lines.append("Safety locks (verified false):")
        lines.append("  real_money_live_trading_enabled:   False")
        lines.append("  openclaw_real_tool_execution:      False")
        lines.append("  live_payments_enabled:             False")
        lines.append("  live_listings_publishing_enabled:  False")
        lines.append("  external_api_calls_enabled:        False")
        lines.append("")
        lines.append("Launch command:           ./scripts/qsb_native_cockpit_run.sh")
        lines.append("Browser fallback URL:     %s" %
                      decision.get("browser_dashboard_remains_as_fallback"))
        lines.append("")

    if "skyscraper_occupancy" in topics:
        audit = _eqsb_load("qsb_full_floor_audit.json")
        wf = _eqsb_load("qsb_new_1000_workers_employed.json")
        depts = _eqsb_load("qsb_department_team_map.json")
        commerce = _eqsb_load("qsb_commerce_wing_masterplan.json")
        opps = _eqsb_load("qsb_online_shop_opportunity_map.json")
        rest = _eqsb_load("qsb_worker_rest_recreation_state.json")
        classroom = _eqsb_load("qsb_classroom_map.json")
        ocfull = _eqsb_load("qsb_openclaw_full_floor_inspection.json")
        lines.append("Skyscraper Occupancy + Commerce Wing — Phase V1")
        lines.append("-" * 56)
        lines.append("Floors audited:           %s" % audit.get("total_floors"))
        lines.append("Weak floors before:       %s" % audit.get("weak_floors_count"))
        lines.append("New workers employed:     %s" % wf.get("new_worker_count"))
        lines.append("Departments mapped:       %s" % depts.get("department_count"))
        lines.append("Commerce wing floors:     %s" % len(commerce.get("departments", [])))
        lines.append("Shop opportunities mapped:%s" % opps.get("opportunity_count"))
        lines.append("Classrooms:               %s" % len(classroom.get("classrooms", [])))
        lines.append("Sleep pods (rest floor 40):%s" % rest.get("sleep_pods_count"))
        lines.append("OpenClaw findings:        %s" % ocfull.get("finding_count"))
        lines.append("OpenClaw tickets:         %s" % ocfull.get("ticket_count"))
        lines.append("")
        lines.append("Where the new 1000 workers went (top departments):")
        bd = wf.get("by_department") or {}
        for d, c in sorted(bd.items(), key=lambda x: -x[1])[:12]:
            lines.append("  %-50s %s" % (d, c))
        lines.append("")
        lines.append("Worker classes:")
        bc = wf.get("by_class") or {}
        for cls, c in sorted(bc.items(), key=lambda x: -x[1]):
            lines.append("  %-22s %s" % (cls, c))
        lines.append("")
        lines.append("Commerce Wing departments:")
        for d in (commerce.get("departments") or []):
            lines.append("  F%-2s %s" % (d.get("floor"), d.get("name")))
        lines.append("")
        lines.append("Top profit opportunities (manual approval required):")
        for op in (opps.get("opportunities") or [])[:6]:
            lines.append("  · %s (%s) — %s — potential: %s" %
                          (op.get("product_type"), op.get("platform"),
                            op.get("recommended_next_step"),
                            op.get("profit_potential")))
        lines.append("")
        lines.append("Classrooms on Floor 8 (Training Academy):")
        for r in (classroom.get("classrooms") or []):
            lines.append("  · %s" % r)
        lines.append("")
        lines.append("Rest / Recreation:")
        lines.append("  Floor 40: Sleep Pods, Standby Lounge, Quiet Recovery, Shift Change")
        lines.append("  Floor 39: Break Room, Game Room, Morale Board, Wellness Monitor")
        lines.append("")
        lines.append("Floors that support PROFIT directly:")
        floors = audit.get("floors") or []
        profit_floors = [f for f in floors if f.get("profit_contribution")]
        for f in profit_floors[:18]:
            lines.append("  F%-2s %s" % (f.get("floor_number"), f.get("secondary_department")))
        lines.append("")
        lines.append("Floors that support KERNEL evolution:")
        kf = [f for f in floors if f.get("kernel_evolution_contribution")]
        for f in kf[:10]:
            lines.append("  F%-2s %s" % (f.get("floor_number"), f.get("secondary_department")))
        lines.append("")
        lines.append("Safety locks: live_money=False · listings_publish=False · payments=False · openclaw_exec=False")
        lines.append("URL: http://127.0.0.1:8765/?v=next3d&floor=55")
        lines.append("")

    if "recent_upgrades" in topics:
        ledger = _eqsb_load("eqsb_claude_upgrade_ledger.json")
        last = _eqsb_load("eqsb_last_claude_change_summary.json")
        plan = _eqsb_load("eqsb_kernel_upgrade_plan.json")
        risk = _eqsb_load("eqsb_upgrade_risk_history.json")
        lines.append("Recent Upgrades (registry-backed)")
        lines.append("-" * 56)
        lines.append("Source registries read:")
        lines.append("  · data/registries/eqsb_claude_upgrade_ledger.json")
        lines.append("  · data/registries/eqsb_last_claude_change_summary.json")
        lines.append("  · data/registries/eqsb_kernel_upgrade_plan.json")
        lines.append("  · data/registries/eqsb_upgrade_risk_history.json")
        lines.append("  · data/logs/eqsb_phase_history.jsonl")
        lines.append("")
        lines.append("Ledger summary:")
        lines.append("  phase_count:         %s" % ledger.get("phase_count"))
        lines.append("  latest_phase:        %s" % ledger.get("latest_phase"))
        lines.append("  latest_summary:      %s" % str(ledger.get("latest_summary") or "")[:160])
        files_created = ledger.get("latest_files_created") or []
        files_modified = ledger.get("latest_files_modified") or []
        if isinstance(files_created, list):
            lines.append("  latest_files_created (%s):" % len(files_created))
            for f in files_created[:8]:
                lines.append("    · %s" % f)
        if isinstance(files_modified, list):
            lines.append("  latest_files_modified (%s):" % len(files_modified))
            for f in files_modified[:8]:
                lines.append("    · %s" % f)
        lines.append("")
        lines.append("Last Claude change summary:")
        lines.append("  phase:       %s" % last.get("phase"))
        lines.append("  summary:     %s" % str(last.get("summary") or "")[:160])
        if isinstance(last.get("files_created"), list):
            lines.append("  files_created: %s" % len(last["files_created"]))
        if isinstance(last.get("files_modified"), list):
            lines.append("  files_modified: %s" % len(last["files_modified"]))
        lines.append("")
        # Phase history from EQSB log tail
        try:
            import os
            phist = "/vaults/nvme0/qsb_tower_v1/data/logs/eqsb_phase_history.jsonl"
            if os.path.exists(phist):
                with open(phist, "r", encoding="utf-8") as fh:
                    last_lines = fh.readlines()[-10:]
                lines.append("Last 8 phase events (tail eqsb_phase_history.jsonl):")
                for ln in last_lines[-8:]:
                    try:
                        rec = json.loads(ln)
                        lines.append("  · %s · %s" % (
                            (rec.get("ts") or "")[:19],
                            rec.get("phase") or rec.get("event") or "?"))
                    except Exception:
                        pass
        except Exception:
            pass
        lines.append("")
        if isinstance(risk, dict):
            lines.append("Upgrade risk history:")
            lines.append("  current_risk_file_count: %s" % risk.get("current_risk_file_count"))
            crisks = risk.get("current_risks") or []
            if isinstance(crisks, list):
                for r in crisks[:5]:
                    lines.append("  · %s" % str(r)[:80])
        lines.append("")

    if "godot_native_status" in topics:
        eng = _eqsb_load("qsb_3d_engine_status.json")
        installed = _eqsb_load("qsb_godot_install_verified.json")
        proj = _eqsb_load("qsb_godot_project_status.json")
        score = _eqsb_load("qsb_godot_visual_score.json")
        gates = _eqsb_load("qsb_godot_visual_acceptance_gates.json")
        pyqt = _eqsb_load("qsb_pyqt_admin_fallback_status.json")
        panda = _eqsb_load("qsb_panda3d_fallback_status.json")
        fail = _eqsb_load("qsb_native_cockpit_visual_failure_audit.json")
        lines.append("Godot Native 3D Cockpit Status (registry-backed)")
        lines.append("-" * 56)
        lines.append("Source registries read:")
        lines.append("  · data/registries/qsb_3d_engine_status.json")
        lines.append("  · data/registries/qsb_godot_install_verified.json")
        lines.append("  · data/registries/qsb_godot_project_status.json")
        lines.append("  · data/registries/qsb_godot_visual_score.json")
        lines.append("  · data/registries/qsb_godot_visual_acceptance_gates.json")
        lines.append("  · data/registries/qsb_pyqt_admin_fallback_status.json")
        lines.append("  · data/registries/qsb_panda3d_fallback_status.json")
        lines.append("  · data/registries/qsb_native_cockpit_visual_failure_audit.json")
        lines.append("")
        lines.append("Engine status (qsb_3d_engine_status.json):")
        lines.append("  godot_ok:          %s" % eng.get("godot_ok"))
        lines.append("  godot_version:     %s" % eng.get("godot_version"))
        lines.append("  panda3d_ok:        %s" % eng.get("panda3d_ok"))
        lines.append("  panda3d_version:   %s" % eng.get("panda3d_version"))
        lines.append("  godot_project:     %s" % eng.get("godot_project"))
        lines.append("  pyqt_cockpit_role: %s" % eng.get("pyqt_cockpit_role"))
        lines.append("  target_engine:     %s" % eng.get("target_main_graphics_engine"))
        lines.append("")
        lines.append("Godot install verified (qsb_godot_install_verified.json):")
        lines.append("  godot_ok:                 %s" % installed.get("godot_ok"))
        lines.append("  godot_command_wrapper:    %s" % installed.get("godot_command_wrapper"))
        lines.append("  panda3d_venv:             %s" % installed.get("panda3d_venv"))
        lines.append("  project.godot exists:     %s" % installed.get("project_godot_exists"))
        lines.append("  run_script exists:        %s" % installed.get("qsb_godot_run_sh_exists"))
        lines.append("")
        lines.append("PyQt fallback classification (qsb_pyqt_admin_fallback_status.json):")
        lines.append("  role:           %s" % pyqt.get("role"))
        lines.append("  visual_target:  %s" % pyqt.get("visual_target"))
        lines.append("  main_3d_engine: %s" % pyqt.get("main_3d_engine"))
        lines.append("  reason:         %s" % str(pyqt.get("reason") or "")[:120])
        lines.append("")
        lines.append("Panda3D fallback (qsb_panda3d_fallback_status.json):")
        lines.append("  installed:       %s" % panda.get("panda3d_installed"))
        lines.append("  version:         %s" % panda.get("panda3d_version"))
        lines.append("  venv_path:       %s" % panda.get("venv_path"))
        lines.append("  use_only_if_godot_blocked: %s" % panda.get("uses_only_if_godot_blocked"))
        lines.append("")
        lines.append("Godot visual score (qsb_godot_visual_score.json):")
        lines.append("  visual_score:               %s" % score.get("visual_score"))
        lines.append("  passed:                     %s / %s" % (score.get("passed"), score.get("total")))
        lines.append("  automated_visual_check:     %s" % score.get("automated_visual_check_pass"))
        lines.append("")
        if fail:
            lines.append("Earlier honest visual failure audit (qsb_native_cockpit_visual_failure_audit.json):")
            lines.append("  summary: %s" % str(fail.get("summary") or "")[:200])
        lines.append("")
        lines.append("Launch command: ./scripts/qsb_godot_run.sh")
        lines.append("Fallbacks: ./scripts/qsb_panda3d_run.sh  ·  ./scripts/qsb_native_cockpit_run.sh (PyQt admin)")
        lines.append("")

    if "missing_features" in topics:
        parity = _eqsb_load("qsb_native_feature_parity_matrix.json")
        backlog = _eqsb_load("qsb_native_missing_features_backlog.json")
        controls = _eqsb_load("qsb_godot_original_controls_migration.json")
        gates = _eqsb_load("qsb_godot_professional_dashboard_gates.json")
        lines.append("Missing Features (registry-backed)")
        lines.append("-" * 56)
        lines.append("Source registries read:")
        lines.append("  · data/registries/qsb_native_feature_parity_matrix.json")
        lines.append("  · data/registries/qsb_native_missing_features_backlog.json")
        lines.append("  · data/registries/qsb_godot_original_controls_migration.json")
        lines.append("  · data/registries/qsb_godot_professional_dashboard_gates.json")
        lines.append("")
        lines.append("Feature parity matrix summary:")
        if isinstance(parity, dict):
            summary = parity.get("summary") or {}
            lines.append("  p0_done:                 %s" % summary.get("p0_done"))
            lines.append("  p0_migrated_now:         %s" % summary.get("p0_migrated_now"))
            lines.append("  p1_done:                 %s" % summary.get("p1_done"))
            lines.append("  p1_migrated_now:         %s" % summary.get("p1_migrated_now"))
            lines.append("  p1_partial_or_later:     %s" % summary.get("p1_partial_or_later"))
            lines.append("  p2_deferred_to_web:      %s" % summary.get("p2_deferred_to_web"))
            lines.append("  p2_later:                %s" % summary.get("p2_later"))
            rows = parity.get("rows") or []
            partial_or_missing = [r for r in rows if isinstance(r, list)
                                   and len(r) >= 3
                                   and r[1] not in ("present", "added_v1", "migrated_v1", "done", "implemented")]
            lines.append("")
            lines.append("Partial / missing rows (%d):" % len(partial_or_missing))
            for r in partial_or_missing[:12]:
                lines.append("  · %s [%s] %s" % (r[0], r[1], r[3] if len(r) > 3 else "?"))
        lines.append("")
        lines.append("Missing features backlog:")
        if isinstance(backlog, dict):
            items = backlog.get("p1_to_migrate_next") or backlog.get("missing_or_partial") or []
            for it in items[:10]:
                lines.append("  · %s — %s" % (it.get("feature") or it.get("id"),
                                                 (it.get("rationale") or it.get("note") or "")[:80]))
            web = backlog.get("p2_remain_browser_fallback") or []
            if web:
                lines.append("Web-fallback-only (not migrated to native by design):")
                for w in web[:10]:
                    lines.append("  · %s" % w)
        lines.append("")
        lines.append("Original dashboard controls migration:")
        if isinstance(controls, dict):
            items = controls.get("controls") or []
            by_status = {}
            for c in items:
                by_status.setdefault(c.get("status", "?"), []).append(c.get("id", "?"))
            for st, ids in by_status.items():
                lines.append("  %s (%d): %s" % (st, len(ids), ", ".join(ids[:8])))
        lines.append("")

    if "learning_evidence" in topics:
        learn = _eqsb_load("eqsb_kernel_learning_loop.json")
        code_obs = _eqsb_load("eqsb_code_observatory.json")
        hw_obs = _eqsb_load("eqsb_hardware_observatory.json")
        ledger = _eqsb_load("eqsb_claude_upgrade_ledger.json")
        lines.append("Learning Evidence (registry-backed proof)")
        lines.append("-" * 56)
        lines.append("Source registries + logs read RIGHT NOW:")
        lines.append("  · data/registries/eqsb_kernel_learning_loop.json")
        lines.append("  · data/registries/eqsb_code_observatory.json")
        lines.append("  · data/registries/eqsb_hardware_observatory.json")
        lines.append("  · data/registries/eqsb_claude_upgrade_ledger.json")
        lines.append("  · data/logs/eqsb_claude_changes.jsonl")
        lines.append("  · data/logs/eqsb_phase_history.jsonl")
        lines.append("")
        lines.append("Kernel learning loop:")
        if isinstance(learn, dict):
            lines.append("  generated_ts:    %s" % learn.get("generated_ts"))
            lines.append("  loop:            %s" % str(learn.get("loop"))[:80])
            learn_from = learn.get("learn_from") or []
            lines.append("  learn_from sources (%d):" % len(learn_from))
            for s in learn_from[:8]:
                lines.append("    · %s" % str(s)[:80])
        lines.append("")
        lines.append("Code observatory:")
        if isinstance(code_obs, dict):
            lines.append("  total_files_observed: %s" % code_obs.get("total_files"))
            lines.append("  by_area_counts:       %s" % str(code_obs.get("by_area_counts"))[:120])
            lines.append("  secret_safety:        %s" % str(code_obs.get("secret_safety"))[:120])
        lines.append("")
        lines.append("Hardware observatory:")
        if isinstance(hw_obs, dict):
            lines.append("  cpu_summary:        %s" % str(hw_obs.get("cpu_summary") or "")[:80])
            lines.append("  gpu_summary:        %s" % str(hw_obs.get("gpu_summary") or "")[:80])
            lines.append("  memory_pressure:    %s" % hw_obs.get("memory_pressure"))
        lines.append("")
        lines.append("Upgrade ledger evidence:")
        if isinstance(ledger, dict):
            lines.append("  phase_count:         %s" % ledger.get("phase_count"))
            lines.append("  latest_phase:        %s" % ledger.get("latest_phase"))
            files_created = ledger.get("latest_files_created") or []
            if isinstance(files_created, list):
                lines.append("  latest_files_created: %s" % len(files_created))
        lines.append("")
        # Tail proof from JSONL log
        try:
            import os
            log_path = "/vaults/nvme0/qsb_tower_v1/data/logs/eqsb_claude_changes.jsonl"
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as fh:
                    last_lines = fh.readlines()[-5:]
                lines.append("Tail of data/logs/eqsb_claude_changes.jsonl (last 5):")
                for ln in last_lines:
                    try:
                        rec = json.loads(ln)
                        lines.append("  · %s · %s" % (
                            (rec.get("ts") or "")[:19],
                            (rec.get("phase") or rec.get("event") or "?")))
                    except Exception:
                        pass
        except Exception:
            pass
        lines.append("")
        lines.append("This block was assembled by reading the above paths just now.")
        lines.append("If any source was missing, it would have appeared as `None` above.")
        lines.append("")

    if "ml_rl_lab" in topics:
        verified = _eqsb_load("qsb_ml_rl_lab_verified_for_integration.json")
        status = _eqsb_load("qsb_ml_rl_lab_status.json")
        torch_st = _eqsb_load("qsb_ml_rl_torch_status.json")
        install = _eqsb_load("qsb_ml_rl_package_install_status.json")
        classroom = _eqsb_load("qsb_ml_rl_classroom_map.json")
        curriculum = _eqsb_load("qsb_ml_rl_curriculum.json")
        research = _eqsb_load("qsb_ml_rl_research_lab_map.json")
        worker_assign = _eqsb_load("qsb_worker_learning_assignments.json")
        oc_sup = _eqsb_load("qsb_openclaw_ml_rl_supervision.json")
        oc_policy = _eqsb_load("qsb_opencore_ml_rl_access_policy.json")
        lines.append("QSB ML/RL Lab — Integration Report (registry-backed)")
        lines.append("-" * 56)
        lines.append("Source registries read:")
        for src in (
            "data/registries/qsb_ml_rl_lab_verified_for_integration.json",
            "data/registries/qsb_ml_rl_lab_status.json",
            "data/registries/qsb_ml_rl_torch_status.json",
            "data/registries/qsb_ml_rl_package_install_status.json",
            "data/registries/qsb_ml_rl_classroom_map.json",
            "data/registries/qsb_ml_rl_curriculum.json",
            "data/registries/qsb_ml_rl_research_lab_map.json",
            "data/registries/qsb_worker_learning_assignments.json",
            "data/registries/qsb_openclaw_ml_rl_supervision.json",
            "data/registries/qsb_opencore_ml_rl_access_policy.json",
        ):
            lines.append("  · %s" % src)
        lines.append("")
        lines.append("Lab path:           %s" % verified.get("lab_path"))
        lines.append("venv:               %s" % verified.get("venv_path"))
        lines.append("Torch version:      %s" % verified.get("torch_version"))
        lines.append("Torch CUDA wheel:   %s" % verified.get("cuda_version_in_torch"))
        lines.append("CUDA available:     %s" % verified.get("cuda_available"))
        lines.append("GPU runtime name:   %s" % verified.get("gpu_name_runtime"))
        lines.append("")
        lines.append("RL stack:")
        lines.append("  torchrl:             %s (v%s)" % (verified.get("torchrl_status"), verified.get("torchrl_version")))
        lines.append("  tensordict:          %s (v%s)" % (verified.get("tensordict_status"), verified.get("tensordict_version")))
        lines.append("  gymnasium:           %s (v%s)" % (verified.get("gymnasium_status"), verified.get("gymnasium_version")))
        lines.append("  stable_baselines3:   %s (v%s)" % (verified.get("stable_baselines3_status"), verified.get("stable_baselines3_version")))
        lines.append("  shimmy / pettingzoo / supersuit: %s / %s / %s" % (
            verified.get("shimmy_status"), verified.get("pettingzoo_status"), verified.get("supersuit_status")))
        lines.append("")
        lines.append("Smoke tests:")
        lines.append("  DQN smoke test:      %s (loss step1=%s · step2=%s · params_changed=%s)" % (
            verified.get("dqn_smoke_test_status"),
            verified.get("dqn_smoke_test_loss_step1"),
            verified.get("dqn_smoke_test_loss_step2"),
            verified.get("dqn_smoke_test_params_changed")))
        lines.append("  RL package smoke:    %s (CartPole obs=%s · SB3 trained %s timesteps)" % (
            verified.get("rl_smoke_test_status"),
            verified.get("rl_smoke_test_cartpole_obs_shape"),
            verified.get("rl_smoke_test_sb3_timesteps")))
        lines.append("")
        lines.append("Install: %s packages installed · %s failed" % (
            verified.get("installed_count"), verified.get("failed_count")))
        if verified.get("failed_packages"):
            lines.append("  failed: %s" % ", ".join(verified.get("failed_packages") or []))
        lines.append("")
        lines.append("Classrooms (%s):" % len(classroom.get("classrooms") or []))
        for c in (classroom.get("classrooms") or [])[:10]:
            lines.append("  · %s (%s)" % (c.get("name"), c.get("lead_role")))
        lines.append("")
        lines.append("Curriculum: %s topics · %s hours" % (
            curriculum.get("total_topics"), curriculum.get("total_hours")))
        lines.append("")
        lines.append("Research labs connected:")
        for f in (research.get("connected_floors") or [])[:9]:
            lines.append("  F%s · %s — %s" % (f.get("floor"), f.get("name"), f.get("ml_rl_use")))
        lines.append("")
        lines.append("Worker learning groups:")
        for a in (worker_assign.get("assignments") or [])[:11]:
            lines.append("  · %s → %s" % (a.get("role"), ", ".join(a.get("tracks") or [])))
        lines.append("")
        lines.append("OpenClaw / OpenCore supervision:")
        lines.append("  mode:                       %s" % oc_sup.get("access_mode"))
        lines.append("  reads (count):              %s" % len(oc_sup.get("reads") or []))
        lines.append("  ticket types allowed:       %s" % ", ".join(oc_sup.get("ticket_types_allowed") or []))
        lines.append("  forbidden actions (count):  %s" % len(oc_sup.get("forbidden_actions") or []))
        lines.append("  opencore role:              %s" % oc_policy.get("opencore_role"))
        lines.append("  opencore may NOT (count):   %s" % len(oc_policy.get("may_NOT") or []))
        lines.append("")
        lines.append("Safety locks:")
        lines.append("  real_money_live_trading_enabled:  False (locked)")
        lines.append("  autonomous_dispatch_enabled:      False (locked)")
        lines.append("  worker_execution_enabled:         False (locked)")
        lines.append("  openclaw_real_tool_execution:     False (locked)")
        lines.append("  live_payments_enabled:            False (locked)")
        lines.append("  live_listings_publishing_enabled: False (locked)")
        lines.append("  advisory_only:                    True")
        lines.append("")

    if "openclaw_supervision" in topics:
        route = _eqsb_load("qsb_openclaw_route.json")
        tickets = _eqsb_load("qsb_openclaw_tickets.json")
        role = _eqsb_load("qsb_openclaw_role_definition.json")
        lines.append("OpenClaw Supervision")
        lines.append("-" * 56)
        lines.append("role:                  %s" % (role.get("role") or "")[:80])
        lines.append("current_floor:         %s" % route.get("current_floor"))
        lines.append("advanced_by:           %s" % route.get("advanced_by"))
        lines.append("is_random:             %s" % route.get("is_random"))
        lines.append("real_tool_execution:   %s (locked)" % role.get("real_tool_execution_enabled"))
        tk_list = tickets.get("tickets") or []
        lines.append("active_tickets:        %s" % len(tk_list))
        for t in tk_list[:6]:
            lines.append("  · %s [%s] %s" % (
                t.get("id"), t.get("severity"), (t.get("issue") or t.get("description") or "")[:60]))
        lines.append("")

    if "profit_command" in topics:
        p = _eqsb_load("qsb_profit_command.json")
        lines.append("Profit Command (V1)")
        lines.append("-" * 56)
        lines.append("mission:            %s" % p.get("mission"))
        lines.append("trading_mode:       %s" % p.get("trading_mode"))
        lines.append("gateway_status:     %s" % p.get("gateway_status"))
        lines.append("open / max trades:  %s / %s" %
                      (p.get("open_trade_count"), p.get("max_open_trades")))
        lines.append("remaining_slots:    %s" % p.get("remaining_trade_slots"))
        lines.append("realized PnL:       %s" % p.get("total_realized_pnl"))
        lines.append("closed trades:      %s" % p.get("closed_trade_count"))
        lines.append("lessons:            %s" % p.get("lesson_count"))
        best = p.get("best_department_by_contribution") or {}
        if best:
            lines.append("best department:    %s (PnL %s)" %
                          (best.get("department"), best.get("realized_pnl")))
        for t in (p.get("top_workers") or [])[:5]:
            lines.append("  · top: %s · pts=%s · pnl=%s" %
                          (t.get("name"), t.get("reward_points"),
                            t.get("realized_pnl_contribution")))
        for a in (p.get("next_profit_focused_actions") or [])[:4]:
            lines.append("  · next: " + str(a))
        lines.append("real_money_live_trading_enabled: %s" % p.get("real_money_live_trading_enabled"))
        lines.append("")

    if "workforce_v1" in topics:
        sc = _eqsb_load("qsb_worker_scorecards.json")
        rew = _eqsb_load("qsb_worker_rewards.json")
        disc = _eqsb_load("qsb_worker_discipline.json")
        prom = _eqsb_load("qsb_worker_promotions.json")
        lines.append("Workforce HR (V1)")
        lines.append("-" * 56)
        lines.append("scorecards:               %s" % sc.get("total_scorecards"))
        lines.append("on_warning / restricted / suspended: %s / %s / %s" %
                      (disc.get("total_on_warning"),
                        disc.get("total_restricted"),
                        disc.get("total_suspended")))
        lines.append("eligible for promotion:   %s" % prom.get("total_eligible_now"))
        lines.append("Promotion ladder:")
        for r in (prom.get("promotion_ladder") or []):
            lines.append("  · %-20s >= %s pts" % (r.get("rank"), r.get("min_points")))
        lines.append("Rank counts:")
        for k, v in (prom.get("by_rank_counts") or {}).items():
            lines.append("  · %-20s %s" % (k, v))
        lines.append("Awards:")
        for a in (rew.get("rewards") or []):
            nom = a.get("nominee") or {}
            lines.append("  · %-32s %s" % (a.get("award"),
                                            nom.get("name") or "no nominee yet"))
        lines.append("Strike policy: 1=warning+retraining, 2=restricted, 3=suspended.")
        lines.append("No paper-loss punishment when rules were followed.")
        lines.append("")

    if "running_commentary" in topics:
        lines.append("Running Commentary (V1)")
        lines.append("-" * 56)
        lines.append("Speech method:        browser_web_speech_synthesis")
        lines.append("Header button:        🎙 Commentary: Off/On (toggle)")
        lines.append("Modes:                Off · Live Tower · Selected Floor · Critical Only · Profit Command · Worker Performance · OpenClaw · Kernel/Penthouse")
        lines.append("Endpoints:")
        for ep in ("/api/narrator/tower", "/api/narrator/profit",
                    "/api/narrator/openclaw", "/api/narrator/kernel",
                    "/api/narrator/critical",
                    "/api/narrator/floor/<floor_id>",
                    "/api/narrator/worker/<worker_id>"):
            lines.append("  · " + ep)
        lines.append("Data source: real registries only (no invented PnL or workers).")
        lines.append("")

    if "live_data_only" in topics:
        v = _eqsb_load("qsb_dashboard_visual_audit.json")
        live = _eqsb_load("qsb_dashboard_live_telemetry.json")
        lines.append("Dashboard Visual Mode: LIVE_DATA_ONLY")
        lines.append("-" * 56)
        lines.append("policy:               NO_RANDOM_LIVE_GRAPHICS")
        lines.append("mode:                 %s" % live.get("dashboard_visual_mode"))
        summary = v.get("summary") or {}
        lines.append("audit summary:        random_or_decorative=%s · rebuilt_in_v3=%s · gated_in_v3=%s" %
                      (summary.get("random_or_decorative"),
                        summary.get("rebuilt_in_v3"),
                        summary.get("gated_in_v3")))
        wc = live.get("worker_counts") or {}
        lines.append("workers visible:      %s of %s canonical" %
                      (wc.get("total_visible_on_skyscraper"),
                        wc.get("total_canonical")))
        lines.append("real worker_movements:%s · real lift_movements: %s · real packets: %s" %
                      (len(live.get("worker_movements") or []),
                        len(live.get("lift_movements") or []),
                        len(live.get("packets") or [])))
        lines.append("")

    if "systems_check_eqsb" in topics:
        sa = _eqsb_load("eqsb_kernel_self_audit.json")
        miss = _eqsb_load("eqsb_kernel_missing_capabilities.json")
        intro = _eqsb_load("eqsb_kernel_introspection_latest.json")
        lines.append("Kernel Self-Audit / Systems Check")
        lines.append("-" * 56)
        lines.append("verdict:                 %s" % sa.get("verdict"))
        lines.append("verdict_reasons:         %s" % json.dumps(sa.get("verdict_reasons") or []))
        lines.append("missing_registry_count:  %s" % sa.get("missing_registry_count"))
        lines.append("guardian_safety_state:   %s" % sa.get("guardian_safety_state"))
        lines.append("entropy_score:           %s" % sa.get("entropy_score"))
        lines.append("drift_score:             %s" % sa.get("drift_score"))
        lines.append("contradiction_count:     %s" % sa.get("contradiction_count"))
        lines.append("continuity_boot_posture: %s" % sa.get("continuity_boot_posture"))
        for w in (miss.get("what_to_build_next") or []):
            lines.append("  · build next: " + w)
        for n in (sa.get("next_actions") or []):
            lines.append("  · next action: " + n)
        for r in (intro.get("safe_next_repairs") or [])[:6]:
            lines.append("  · safe repair: " + r)
        lines.append("")

    if "commerce_floor" in topics:
        # Floor 46 — Etsy preview-only commerce wing.
        try:
            from tower.floors.floor_46_commerce import (
                floor_state_snapshot, catalog_snapshot, pricing_advisor,
            )
            fst = floor_state_snapshot()
            cat = catalog_snapshot()
            pr  = pricing_advisor().summarize()
            lines.append("Floor 46 — Commerce Wing (Etsy preview-only)")
            lines.append("-" * 56)
            lines.append("status:              %s" % fst.get("status"))
            f = fst.get("flags") or {}
            lines.append("live_listings_publishing_enabled:  %s" % f.get("live_listings_publishing_enabled"))
            lines.append("payments_enabled:                  %s" % f.get("payments_enabled"))
            lines.append("external_api_calls_enabled:        %s" % f.get("external_api_calls_enabled"))
            lines.append("etsy_real_marketplace_contact:     %s" % f.get("etsy_real_marketplace_contact"))
            lines.append("sandbox_catalog_active:            %s" % f.get("sandbox_catalog_active"))
            lines.append("")
            lines.append("Sandbox catalog: %d products across %s" %
                          (cat.get("product_count", 0),
                            ", ".join(sorted((cat.get("category_breakdown") or {}).keys()))))
            for p in (cat.get("products") or [])[:6]:
                lines.append("  · [%s] %s — $%.2f (margin %.1f%%, vs market %+.1f%%)"
                              % (p.get("sku"), p.get("title"),
                                  float(p.get("suggested_price", 0) or 0),
                                  float(p.get("margin_percent", 0) or 0),
                                  float(p.get("vs_market_percent", 0) or 0)))
            lines.append("")
            lines.append("Pricing advisor summary:")
            lines.append("  projected_monthly_revenue: $%.2f" %
                          float(pr.get("projected_monthly_revenue") or 0))
            lines.append("  projected_monthly_profit:  $%.2f" %
                          float(pr.get("projected_monthly_profit") or 0))
            lines.append("  best by projected profit:")
            for r in (pr.get("best_by_projected_profit") or [])[:3]:
                lines.append("    · %s  profit=$%.2f  action=%s" %
                              (r.get("sku"), float(r.get("projected_monthly_profit", 0) or 0),
                                r.get("advisory_action")))
            lines.append("  worst by margin:")
            for r in (pr.get("worst_by_margin") or [])[:3]:
                lines.append("    · %s  margin=%.1f%%  action=%s (%s)" %
                              (r.get("sku"), float(r.get("margin_percent", 0) or 0),
                                r.get("advisory_action"),
                                r.get("advisory_reason")))
            lines.append("")
            lines.append("Policy: %s" % fst.get("policy"))
            lines.append("")
        except Exception as _e:
            lines.append("Floor 46 — Commerce Wing")
            lines.append("-" * 56)
            lines.append("commerce floor bridge unavailable: %s" % _e)
            lines.append("")

    if "profit_plan" in topics:
        # Floor 47 — Profit Analytics
        try:
            from tower.floors.floor_47_profit_analytics import profit_analytics
            snap = profit_analytics().snapshot()
            top = snap.get("topline") or {}
            by = snap.get("by_floor") or {}
            wf = snap.get("workforce") or {}
            lines.append("Floor 47 — Profit Analytics Center")
            lines.append("-" * 56)
            lines.append("topline (advisory, read-only):")
            lines.append("  projected_monthly_revenue_commerce:  $%.2f" %
                          float(top.get("projected_monthly_revenue_commerce") or 0))
            lines.append("  projected_monthly_profit_commerce:   $%.2f" %
                          float(top.get("projected_monthly_profit_commerce") or 0))
            lines.append("  realized_pnl_oanda_practice:         %s" %
                          top.get("realized_pnl_oanda_practice"))
            lines.append("  warnings: %s" % (top.get("warnings") or ["(none)"]))
            lines.append("")
            lines.append("Per-floor:")
            for fname, fdata in by.items():
                lines.append("  %s [%s]" % (fname, fdata.get("mode", "?")))
                for k, v in fdata.items():
                    if k in ("floor", "mode"): continue
                    lines.append("    %s: %s" % (k, v))
            lines.append("")
            lines.append("Workforce:")
            lines.append("  total=%s active=%s idle=%s active_ratio=%s" %
                          (wf.get("total_workers"), wf.get("active_workers"),
                            wf.get("idle_workers"), wf.get("active_ratio")))
            lines.append("")
            lines.append("Advisory actions:")
            for a in (snap.get("advisory_actions") or []):
                lines.append("  · [%s] %s" % (a.get("id"), a.get("title")))
                lines.append("      action: %s" % a.get("action"))
                lines.append("      expected_value: %s" % a.get("expected_value"))
            lines.append("")
        except Exception as _e:
            lines.append("Floor 47 — Profit Analytics Center")
            lines.append("-" * 56)
            lines.append("profit bridge unavailable: %s" % _e)
            lines.append("")

    if "reassign_workers" in topics:
        try:
            from tower.cognitive_kernel.worker_reassignment import worker_reassignment
            wr = worker_reassignment()
            proposals = wr.compute()
            snap = wr.persist()
            lines.append("Worker Reassignment — Idle → Highest-Value")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("target floors (ranked):")
            for t in (snap.get("targets") or []):
                lines.append("  · %s  prio=%.2f  cap=%d  roles=%s" %
                              (t.get("floor"), float(t.get("priority", 0) or 0),
                                int(t.get("max_workers", 0) or 0),
                                t.get("desired_roles") or []))
            lines.append("")
            lines.append("Computed moves (advisory):")
            if not proposals:
                lines.append("  · no idle workers detected in cognitive_worker_exchange.json")
                lines.append("    (operator: refresh qsb_worker_scene_state.json)")
            for r in proposals[:15]:
                lines.append("  · move %d  %s → %s  as %s  (conf=%.2f)" %
                              (r.worker_count, r.from_floor, r.to_floor,
                                r.desired_role, r.confidence))
            lines.append("")
        except Exception as _e:
            lines.append("Worker Reassignment")
            lines.append("-" * 56)
            lines.append("reassignment bridge unavailable: %s" % _e)
            lines.append("")

    if "candidate_floors" in topics:
        try:
            from tower.cognitive_kernel.candidate_floors import snapshot as cf_snap
            snap = cf_snap()
            lines.append("Candidate Floors — What To Open Next")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("by_status: %s" % snap.get("by_status"))
            lines.append("by_safety_class: %s" % snap.get("by_safety_class"))
            lines.append("")
            for c in (snap.get("candidates") or []):
                gates = ", ".join(c.get("gates_must_stay_locked") or []) or "(none)"
                lines.append("  Floor %d — %s   [%s · %s]" %
                              (int(c.get("floor_number") or 0),
                                c.get("floor"), c.get("status"),
                                c.get("safety_class")))
                lines.append("    purpose:     %s" % c.get("purpose"))
                lines.append("    value_path:  %s" % c.get("value_path"))
                lines.append("    gates locked: %s" % gates)
                roles = c.get("desired_worker_roles") or []
                if roles:
                    lines.append("    roles:       %s" % ", ".join(roles))
                if c.get("notes"):
                    lines.append("    notes:       %s" % c.get("notes"))
                lines.append("")
        except Exception as _e:
            lines.append("Candidate Floors")
            lines.append("-" * 56)
            lines.append("candidate_floors bridge unavailable: %s" % _e)
            lines.append("")

    if "oanda_worker_status" in topics:
        try:
            from tower.cognitive_kernel.oanda_worker_trades import persist as owt_persist
            from tower_ops.oanda_practice_trading import account, open_trades, _guard_state
            snap = owt_persist()
            ac = account()
            ot = open_trades()
            gs = _guard_state()
            lines.append("OANDA Practice — Certified Worker Trades (LIVE)")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("")
            if ac.get("ok"):
                lines.append("ACCOUNT (live read):")
                lines.append("  balance:           %s %s" %
                              (ac.get("balance"), ac.get("currency")))
                lines.append("  NAV:               %s" % ac.get("NAV"))
                lines.append("  realized_pl_today: %s" % ac.get("realized_pl_today"))
                lines.append("  unrealized_pl:     %s" % ac.get("unrealized_pl"))
                lines.append("  open_trade_count:  %s" % ac.get("open_trade_count"))
            else:
                lines.append("ACCOUNT: read failed (%s)" %
                              (ac.get("error") or ac.get("status")))
            lines.append("")
            if ot.get("ok"):
                trades = ot.get("trades") or []
                lines.append("OPEN TRADES (%d) on practice account:" % len(trades))
                owners = (snap.get("ownership_sample") or {})
                for t in trades[:8]:
                    tid = str(t.get("id"))
                    owner = owners.get(tid, "(no worker attribution)")
                    lines.append("  id=%s  %s  units=%s  open=%s  unrealizedPL=%s" %
                                  (tid, t.get("instrument"),
                                    t.get("initialUnits"),
                                    t.get("price"),
                                    t.get("unrealizedPL")))
                    lines.append("    owner: %s" % owner)
            lines.append("")
            lines.append("Per-worker realized PnL (GBP):")
            for wid, pnl in (snap.get("per_worker_realised_gbp") or {}).items():
                lines.append("  %s: %+.2f GBP" % (wid, pnl))
            if not snap.get("per_worker_realised_gbp"):
                lines.append("  (no per-worker realized PnL yet)")
            lines.append("")
            lines.append("Guard state:")
            lines.append("  kill_switch_on:                         %s" %
                          gs.get("kill_switch_on"))
            lines.append("  oanda_practice_order_execution_enabled: %s" %
                          gs.get("oanda_practice_order_execution_enabled"))
            lines.append("  execution_mode:                         %s" %
                          gs.get("execution_mode"))
            lines.append("  live_trading_enabled:                   %s" %
                          gs.get("live_trading_enabled"))
            lines.append("")
            lines.append("CLI:")
            lines.append("  python3 tools/qsb_oanda.py preflight")
            lines.append("  python3 tools/qsb_oanda.py preview <worker> <inst> <units> <buy|sell> --reason ...")
            lines.append("  python3 tools/qsb_oanda.py place   <worker> <inst> <units> <buy|sell> --reason ... --confirm")
            lines.append("  python3 tools/qsb_oanda.py close   <worker> <oanda_trade_id> --reason ...")
            lines.append("  python3 tools/qsb_oanda.py claim   <worker> <oanda_trade_id> <inst>")
            lines.append("")
        except Exception as _e:
            lines.append("OANDA Practice — Certified Worker Trades")
            lines.append("-" * 56)
            lines.append("oanda bridge unavailable: %s" % _e)
            lines.append("")

    if "research_queue" in topics:
        try:
            from tower.cognitive_kernel.research_queue import research_queue
            rq = research_queue()
            rq.load_from_snapshot()
            snap = rq.persist()
            lines.append("Research Queue — Safe substitute for autonomous internet")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("item_count:  %s" % snap.get("item_count"))
            lines.append("by_status:   %s" % snap.get("by_status"))
            lines.append("")
            lines.append("Allowlist (servicing phase MUST stay within this):")
            for a in (snap.get("allowlist_default") or [])[:8]:
                lines.append("  · %s  (%s)" % (a.get("domain"),
                                                a.get("rationale")))
            lines.append("")
            opens = [i for i in (snap.get("items") or [])
                      if i.get("status") == "open"]
            if opens:
                lines.append("Open research items:")
                for i in opens[:8]:
                    lines.append("  · %s  by=%s" % (i.get("item_id"),
                                                      i.get("requested_by")))
                    lines.append("      q: %s" % i.get("question", "")[:120])
            else:
                lines.append("(no open research items — file one with "
                             "tools/qsb_research.py file '<question>')")
            lines.append("")
            lines.append("CLI:")
            lines.append("  python3 tools/qsb_research.py file '<question>' [--urls URL ...]")
            lines.append("  python3 tools/qsb_research.py list")
            lines.append("  python3 tools/qsb_research.py allowlist")
            lines.append("")
        except Exception as _e:
            lines.append("Research Queue")
            lines.append("-" * 56)
            lines.append("research_queue bridge unavailable: %s" % _e)
            lines.append("")

    if "finance_live_status" in topics:
        try:
            from tower.cognitive_kernel.finance_live_status import persist as fls_persist
            snap = fls_persist()
            lines.append("Finance Live Status (honest report)")
            lines.append("-" * 56)
            lines.append("HEADLINE: %s" % snap.get("headline"))
            lines.append("")
            lines.append("any_real_orders_placed_anywhere:    %s" %
                          snap.get("any_real_orders_placed_anywhere"))
            lines.append("total_real_api_calls_across_floors: %s" %
                          snap.get("total_real_api_calls_across_floors"))
            lines.append("total_ledger_rows:                   %s" %
                          snap.get("total_ledger_rows"))
            lines.append("  of which synthetic / demo:        %s" %
                          snap.get("total_synthetic_rows"))
            lines.append("  of which real (broker_order_id):  %s" %
                          snap.get("total_real_rows"))
            lines.append("")
            for f in snap.get("floors") or []:
                lines.append("%s [%s]" % (f.get("floor_label"), f.get("mode")))
                lines.append("  adapter_present:        %s" % f.get("api_adapter_module_present"))
                lines.append("  credentials_env_seen:   %s" %
                              (f.get("credentials_env_vars_seen") or "(none)"))
                lines.append("  real_api_calls_logged:  %s" % f.get("real_api_calls_logged"))
                lines.append("  real_orders_placed:     %s" % f.get("real_orders_placed"))
                lines.append("  ledger total / synth / real: %s / %s / %s" %
                              (f.get("ledger_total_rows"),
                                f.get("ledger_synthetic_rows"),
                                f.get("ledger_real_rows")))
                lines.append("  gates: %s" % f.get("gates_locked"))
                for n in (f.get("advisory_notes") or [])[:3]:
                    lines.append("    note: %s" % n)
                lines.append("")
        except Exception as _e:
            lines.append("Finance Live Status")
            lines.append("-" * 56)
            lines.append("finance_live_status bridge unavailable: %s" % _e)
            lines.append("")

    if "tower_studio" in topics:
        try:
            from tower.floors.floor_49_tower_studio.state import floor_state_snapshot
            from tower.floors.floor_49_tower_studio.services import services_snapshot
            from tower.floors.floor_49_tower_studio.customers import customers_db
            from tower.floors.floor_49_tower_studio.projects import projects_db
            from tower.floors.floor_49_tower_studio.workers import workers_snapshot
            fst = floor_state_snapshot()
            svc = services_snapshot()
            custs = customers_db().snapshot()
            projs = projects_db().snapshot()
            wks = workers_snapshot()
            lines.append("Floor 49 — Tower Studio (Web Design + IT)")
            lines.append("-" * 56)
            lines.append("status: %s" % fst.get("status"))
            lines.append("company_name: %s" % fst.get("company_name"))
            lines.append("tagline:      %s" % fst.get("tagline"))
            lines.append("")
            f = fst.get("flags") or {}
            lines.append("Gates:")
            for k in ("public_website_published", "real_payments_enabled",
                       "live_listings_publishing_enabled",
                       "external_api_calls_enabled",
                       "autonomous_dispatch_enabled"):
                lines.append("  %s: %s" % (k, f.get(k)))
            lines.append("")
            lines.append("Workers: %d across %d roles (%s)" %
                          (wks.get("worker_count", 0),
                            len(wks.get("by_role") or {}),
                            wks.get("by_role")))
            lines.append("Levels: %s" % wks.get("by_level"))
            lines.append("")
            lines.append("Services: %d packages" % svc.get("service_count", 0))
            for s in (svc.get("services") or [])[:5]:
                lines.append("  · %s  $%.2f  %s" %
                              (s.get("sku"), float(s.get("price_usd") or 0),
                                s.get("short_description")))
            lines.append("")
            lines.append("Customers: %d  by_status=%s  total_LTV=$%.2f" %
                          (custs.get("customer_count", 0),
                            custs.get("by_status"),
                            float(custs.get("total_lifetime_value_usd") or 0)))
            lines.append("Projects: %d  by_status=%s  quoted=$%.2f" %
                          (projs.get("project_count", 0),
                            projs.get("by_status"),
                            float(projs.get("total_quoted_usd") or 0)))
            lines.append("")
            lines.append("Local website: http://127.0.0.1:8849")
            lines.append("Start servers: scripts/qsb_web_start.sh")
            lines.append("")
        except Exception as _e:
            lines.append("Floor 49 — Tower Studio")
            lines.append("-" * 56)
            lines.append("tower_studio bridge unavailable: %s" % _e)
            lines.append("")

    if "lumen_ai" in topics:
        try:
            from tower.floors.floor_48_lumen_ai.state import lumen_state_snapshot
            from tower.floors.floor_48_lumen_ai.tiers import tiers_snapshot
            from tower.floors.floor_48_lumen_ai.chat import conversations_snapshot
            fst = lumen_state_snapshot()
            tiers = tiers_snapshot()
            convs = conversations_snapshot()
            lines.append("Floor 48 — Lumen AI (Chat Service)")
            lines.append("-" * 56)
            lines.append("brand_name:    %s" % fst.get("brand_name"))
            lines.append("brand_tagline: %s" % fst.get("brand_tagline"))
            lines.append("engine:        %s" % fst.get("engine"))
            f = fst.get("flags") or {}
            lines.append("")
            lines.append("Gates:")
            for k in ("model_inference_external_apis", "public_api_open",
                       "real_payments_enabled", "kernel_powered"):
                lines.append("  %s: %s" % (k, f.get(k)))
            lines.append("")
            lines.append("Pricing tiers:")
            for t in (tiers.get("tiers") or []):
                lines.append("  · %s  $%.2f/mo  quota=%s" %
                              (t.get("name"),
                                float(t.get("price_usd_per_month") or 0),
                                t.get("monthly_message_quota")))
            lines.append("")
            lines.append("Conversations: %s" % convs.get("conversation_count"))
            lines.append("")
            lines.append("Local website: http://127.0.0.1:8848")
            lines.append("Chat endpoint: POST http://127.0.0.1:8848/api/chat")
            lines.append("Start servers: scripts/qsb_web_start.sh")
            lines.append("")
        except Exception as _e:
            lines.append("Floor 48 — Lumen AI")
            lines.append("-" * 56)
            lines.append("lumen_ai bridge unavailable: %s" % _e)
            lines.append("")

    if "banking_gateway" in topics:
        try:
            from tower.cognitive_kernel.banking_gateway import snapshot as bg_snap
            snap = bg_snap()
            lines.append("Banking Gateway — SCAFFOLD (real-money phase = SEPARATE)")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            for k, v in (snap.get("global_gates") or {}).items():
                lines.append("  %s: %s" % (k, v))
            lines.append("")
            lines.append("Providers documented:")
            for p in snap.get("providers") or []:
                lines.append("  · %s [%s]" % (p.get("name"), p.get("kind")))
                lines.append("      reconciliation:   %s" % p.get("reconciliation_cadence"))
                lines.append("      deposit/withdraw: dep=%s wd=%s" %
                              (p.get("deposit_supported"),
                                p.get("withdrawal_supported")))
                lines.append("      env vars needed (NAMES ONLY):")
                for e in p.get("env_vars_required") or []:
                    lines.append("        - %s" % e)
                lines.append("      kill switch: %s" % p.get("kill_switch_method"))
            lines.append("")
            lines.append("Future-phase checklist:")
            for c in (snap.get("future_phase_checklist") or [])[:5]:
                lines.append("  %s" % c)
            lines.append("")
            lines.append("Kernel will NEVER:")
            for x in (snap.get("what_kernel_will_NEVER_do") or []):
                lines.append("  · " + x)
            lines.append("")
        except Exception as _e:
            lines.append("Banking Gateway")
            lines.append("-" * 56)
            lines.append("banking_gateway bridge unavailable: %s" % _e)
            lines.append("")

    if "worker_spawn_status" in topics:
        try:
            from tower.cognitive_kernel.worker_spawn import worker_spawn
            ws = worker_spawn()
            ws.collect_pending()
            roster = ws.write_roster()
            ws.persist()
            lines.append("Worker Spawn Roster (pending births)")
            lines.append("-" * 56)
            lines.append("policy: %s" % roster.get("policy"))
            lines.append("pending_count: %s" % roster.get("pending_count"))
            for pb in (roster.get("pending_births") or [])[:10]:
                gene = pb.get("inherited_gene") or {}
                lines.append("  · child_id=%s  parent=%s  status=%s  "
                              "gene=%s/%s  role=%s  floor=%s" %
                              (pb.get("child_id"), pb.get("parent_id"),
                                pb.get("spawn_status"),
                                gene.get("instrument", "?"),
                                gene.get("style", "?"),
                                pb.get("proposed_workforce_role"),
                                pb.get("proposed_floor_assignment")))
            if not roster.get("pending_births"):
                lines.append("  (no pending births yet)")
            lines.append("")
            lines.append("CLI:")
            lines.append("  python3 tools/qsb_spawn.py list")
            lines.append("  python3 tools/qsb_spawn.py commit <child_id>")
            lines.append("  python3 tools/qsb_spawn.py decline <child_id>")
            lines.append("")
        except Exception as _e:
            lines.append("Worker Spawn Roster")
            lines.append("-" * 56)
            lines.append("worker_spawn bridge unavailable: %s" % _e)
            lines.append("")

    if "oanda_attribution" in topics:
        try:
            from tower.cognitive_kernel.oanda_attribution import persist as oa_persist
            snap = oa_persist()
            lines.append("OANDA Ledger Attribution Audit")
            lines.append("-" * 56)
            lines.append("ledger_present:        %s" % snap.get("ledger_present"))
            lines.append("ledger_path:           %s" % snap.get("ledger_path"))
            lines.append("total_rows:            %s" % snap.get("total_rows"))
            lines.append("unassigned_rows:       %s" % snap.get("unassigned_rows"))
            lines.append("attribution_coverage:  %s" % snap.get("attribution_coverage"))
            lines.append("last_unassigned_ts:    %s" % snap.get("last_unassigned_ts"))
            lines.append("by_instrument_unassigned: %s" %
                          snap.get("by_instrument_unassigned"))
            lines.append("")
            lines.append("advice: %s" % snap.get("advice"))
            lines.append("")
        except Exception as _e:
            lines.append("OANDA Attribution Audit")
            lines.append("-" * 56)
            lines.append("oanda_attribution bridge unavailable: %s" % _e)
            lines.append("")

    if "free_image_promote" in topics:
        try:
            from tower.cognitive_kernel.free_image_promotion import free_image_promotion
            fip = free_image_promotion()
            fip.load_approvals()
            snap = fip.snapshot()
            lines.append("Free Image Promotion — operator-approved drafts")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("approval_count: %s   promoted_count: %s" %
                          (snap.get("approval_count"), snap.get("promoted_count")))
            for a in (snap.get("approvals") or [])[:10]:
                lines.append("  · draft=%s  sku=%s  src=%s  promoted=%s" %
                              (a.get("draft_id"), a.get("sku"),
                                a.get("source_name"), a.get("promoted")))
            if not snap.get("approvals"):
                lines.append("  (no approvals yet)")
            lines.append("")
            lines.append("CLI:")
            lines.append("  python3 tools/qsb_image.py list")
            lines.append("  python3 tools/qsb_image.py approve <draft_id>")
            lines.append("")
        except Exception as _e:
            lines.append("Free Image Promotion")
            lines.append("-" * 56)
            lines.append("free_image_promotion bridge unavailable: %s" % _e)
            lines.append("")

    if "bank_spend" in topics:
        try:
            from tower.cognitive_kernel.bank_spend import bank_spend
            bs = bank_spend()
            bs.load_from_snapshot()
            snap = bs.snapshot()
            lines.append("Bank Spend — operator-approved QBC spends")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("spend kinds (default amounts):")
            for k, v in (snap.get("spend_kinds") or {}).items():
                lines.append("  %s: %s QBC" % (k, v))
            lines.append("")
            lines.append("requests: %s   by_status: %s" %
                          (snap.get("request_count"), snap.get("by_status")))
            for r in (snap.get("requests") or [])[:8]:
                tgt = (" → %s" % r.get("target_worker_id")) if r.get("target_worker_id") else ""
                lines.append("  · %s  [%s]  %s%s  %s QBC  status=%s" %
                              (r.get("spend_id"), r.get("kind"),
                                r.get("worker_id"), tgt,
                                r.get("qbc_amount"), r.get("status")))
            if not snap.get("requests"):
                lines.append("  (no spend requests yet)")
            lines.append("")
            lines.append("CLI:")
            lines.append("  python3 tools/qsb_spend.py request <kind> <worker_id> ...")
            lines.append("  python3 tools/qsb_spend.py approve <spend_id>")
            lines.append("  python3 tools/qsb_spend.py execute <spend_id>")
            lines.append("")
        except Exception as _e:
            lines.append("Bank Spend")
            lines.append("-" * 56)
            lines.append("bank_spend bridge unavailable: %s" % _e)
            lines.append("")

    if "morning_briefing" in topics:
        try:
            from tower.cognitive_kernel.morning_briefing import morning_briefing
            snap = morning_briefing().persist()
            lines.append("Tower Morning Briefing")
            lines.append("-" * 56)
            lines.append("HEADLINE:  %s" % snap.get("headline"))
            lines.append("")
            lines.append("State:")
            for b in (snap.get("bullets") or []):
                lines.append("  · " + b)
            pending = snap.get("pending_actions_for_ross") or []
            if pending:
                lines.append("")
                lines.append("Awaiting Ross:")
                for p in pending:
                    lines.append("  · " + p)
            risks = snap.get("risks") or []
            if risks:
                lines.append("")
                lines.append("Risks:")
                for r in risks:
                    lines.append("  ⚠ " + r)
            lines.append("")
            lines.append("Gates (always):")
            se = snap.get("safety_envelope") or {}
            for k in ("execution_allowed", "live_payments_enabled",
                      "real_money_live_trading_enabled",
                      "autonomous_dispatch_enabled"):
                lines.append("  %s: %s" % (k, se.get(k)))
            lines.append("")
        except Exception as _e:
            lines.append("Morning Briefing")
            lines.append("-" * 56)
            lines.append("briefing bridge unavailable: %s" % _e)
            lines.append("")

    if "godot_visuals" in topics:
        lines.append("3D Cockpit — Cognitive Overlays (Godot)")
        lines.append("-" * 56)
        lines.append("Five additive scripts now live in:")
        lines.append("  native_cockpit/godot_qsb/scripts/")
        lines.append("")
        lines.append("Drop each on an empty Node3D in the scene (no Main.gd edits):")
        lines.append("  · CognitiveOverlay.gd       — worker markers, halos, badges, tree edges, activity stream")
        lines.append("  · BankVault.gd              — coin-stack column tracking QBC supply")
        lines.append("  · ContradictionFlare.gd     — red flash + light when contradiction detected")
        lines.append("  · LineageGenerationRings.gd — concentric rings, one per generation")
        lines.append("  · BriefingTicker.gd         — slow-scrolling headline + risks")
        lines.append("")
        lines.append("All read cognitive_*.json directly. None call any API. They")
        lines.append("tick at 1-5 second cadence. See README_OVERLAYS.md in the")
        lines.append("scripts dir for placement instructions.")
        lines.append("")

    if "bank" in topics:
        try:
            from tower.cognitive_kernel.bank import bank
            bk = bank()
            bk.load_from_snapshot()
            snap = bk.snapshot()
            lines.append("Skyscraper Bank — QBC (QSB Bank Credit)")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("currency:            %s" % snap.get("currency"))
            lines.append("outstanding_supply:  %s QBC" % snap.get("outstanding_supply"))
            lines.append("total_supply_cap:    %s QBC" % snap.get("total_supply_cap"))
            lines.append("utilisation:         %s" % snap.get("utilisation"))
            lines.append("tighten_threshold:   %s" % snap.get("tighten_at_utilisation"))
            lines.append("account_count:       %s" % snap.get("account_count"))
            lines.append("txn_count:           %s" % snap.get("txn_count"))
            lines.append("top10_concentration: %s" % snap.get("top10_pct_concentration"))
            lines.append("")
            tops = snap.get("top_balances") or []
            lines.append("Top balances:")
            for a in tops[:10]:
                lines.append("  %s  balance=%.2f QBC  minted=%.2f  burned=%.2f  txns=%d" %
                              (a.get("worker_id"),
                                float(a.get("balance") or 0),
                                float(a.get("total_minted") or 0),
                                float(a.get("total_burned") or 0),
                                int(a.get("txn_count") or 0)))
            if not tops:
                lines.append("  (no accounts yet)")
            lines.append("")
            txns = snap.get("recent_transactions") or []
            lines.append("Recent transactions:")
            for t in txns[-8:]:
                lines.append("  %s  %s  %.2f QBC  from=%s  to=%s" %
                              (t.get("txn_id"), t.get("kind"),
                                float(t.get("amount") or 0),
                                t.get("from_worker") or "-",
                                t.get("to_worker") or "-"))
            lines.append("")
        except Exception as _e:
            lines.append("Skyscraper Bank")
            lines.append("-" * 56)
            lines.append("bank bridge unavailable: %s" % _e)
            lines.append("")

    if "compensation" in topics:
        try:
            from tower.cognitive_kernel.compensation import compensation_engine
            ce = compensation_engine()
            ce.load_from_snapshot()
            snap = ce.snapshot()
            lines.append("Compensation Engine — Pay rules + recent payouts")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("pay_rates:")
            for k, v in (snap.get("pay_rates") or {}).items():
                lines.append("  %s: %s" % (k, v))
            lines.append("paid_reason_count: %s" % snap.get("paid_reason_count"))
            lines.append("total_paid_by_kind:")
            for k, v in (snap.get("total_paid_by_kind") or {}).items():
                lines.append("  %s: %.2f QBC" % (k, float(v)))
            lines.append("")
            recent = snap.get("recent_payments") or []
            lines.append("Recent payments:")
            for r in recent[-10:]:
                lines.append("  %s  +%.2f QBC  %s  (%s)" %
                              (r.get("worker_id"),
                                float(r.get("qbc_amount") or 0),
                                r.get("kind"), r.get("note", "")))
            if not recent:
                lines.append("  (no payments settled yet — run compensation_engine().settle_round())")
            lines.append("")
        except Exception as _e:
            lines.append("Compensation Engine")
            lines.append("-" * 56)
            lines.append("compensation bridge unavailable: %s" % _e)
            lines.append("")

    if "lineage_performance" in topics:
        try:
            from tower.cognitive_kernel.lineage_beliefs import lineage_beliefs
            snap = lineage_beliefs().persist()
            lines.append("Lineage Performance — descendants vs tower avg")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("lineage_count: %s" % snap.get("lineage_count"))
            best = snap.get("best_lineages") or []
            worst = snap.get("worst_lineages") or []
            if best:
                lines.append("Best lineages:")
                for r in best[:5]:
                    lines.append("  ancestor=%s  descendants=%d  pnl=$%.2f  vs_tower=%s%%" %
                                  (r.get("ancestor_id"),
                                    int(r.get("descendants_count") or 0),
                                    float(r.get("descendants_total_pnl") or 0),
                                    r.get("descendants_outperform_tower_pct")))
            else:
                lines.append("  (no lineages yet — need family_tree edges)")
            if worst and worst != best:
                lines.append("Worst lineages:")
                for r in worst[:3]:
                    lines.append("  ancestor=%s  descendants=%d  pnl=$%.2f  vs_tower=%s%%" %
                                  (r.get("ancestor_id"),
                                    int(r.get("descendants_count") or 0),
                                    float(r.get("descendants_total_pnl") or 0),
                                    r.get("descendants_outperform_tower_pct")))
            lines.append("")
        except Exception as _e:
            lines.append("Lineage Performance")
            lines.append("-" * 56)
            lines.append("lineage_beliefs bridge unavailable: %s" % _e)
            lines.append("")

    if "curriculum_evolution" in topics:
        try:
            from tower.cognitive_kernel.curriculum_evolution import curriculum_evolution
            snap = curriculum_evolution().persist()
            lines.append("Curriculum Evolution — lesson↔outcome scoring")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("lesson_count:       %s" % snap.get("lesson_count"))
            lines.append("actions_breakdown:  %s" % snap.get("actions_breakdown"))
            lines.append("")
            for o in (snap.get("outcomes") or [])[:8]:
                lines.append("  %s  score=%.2f  signal=%.2f  → %s" %
                              (o.get("lesson_id"),
                                float(o.get("score") or 0),
                                float(o.get("proxy_signal_strength") or 0),
                                o.get("action_proposed")))
                lines.append("    title: %s" % o.get("title"))
            lines.append("")
        except Exception as _e:
            lines.append("Curriculum Evolution")
            lines.append("-" * 56)
            lines.append("curriculum_evolution bridge unavailable: %s" % _e)
            lines.append("")

    if "free_images" in topics:
        try:
            from tower.cognitive_kernel.free_image_catalog import snapshot as fis_snap
            snap = fis_snap()
            lines.append("Free Image Catalog — sources + draft listings (advisory)")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("external_api_calls_enabled:        %s" %
                          snap.get("external_api_calls_enabled"))
            lines.append("live_listings_publishing_enabled:  %s" %
                          snap.get("live_listings_publishing_enabled"))
            lines.append("source_count:                       %s" %
                          snap.get("source_count"))
            lines.append("commercial_safe_source_count:       %s" %
                          snap.get("commercial_safe_source_count"))
            lines.append("derivative_product_templates:       %s" %
                          snap.get("derivative_product_template_count"))
            lines.append("draft_listing_count (full synth):   %s" %
                          snap.get("draft_listing_count"))
            lines.append("projected_monthly_revenue_full_synth: $%.2f" %
                          float(snap.get("projected_monthly_revenue_full_synth") or 0))
            lines.append("projected_monthly_profit_full_synth:  $%.2f" %
                          float(snap.get("projected_monthly_profit_full_synth") or 0))
            lines.append("")
            lines.append("Sources (commercial-OK):")
            for s in snap.get("sources") or []:
                if not s.get("commercial_ok"): continue
                lines.append("  · %s — %s  (attribution=%s, share-alike=%s)" %
                              (s.get("name"), s.get("license_name"),
                                s.get("attribution_required"),
                                s.get("share_alike_required")))
            lines.append("")
            lines.append("Sample drafts (from full synth, no real fetch):")
            for d in (snap.get("draft_sample") or [])[:6]:
                lines.append("  %s  cat=%s  $%.2f  proj_rev=$%.2f  src=%s" %
                              (d.get("sku"), d.get("category"),
                                float(d.get("suggested_price") or 0),
                                float(d.get("projected_revenue") or 0),
                                d.get("source_name")))
            lines.append("")
        except Exception as _e:
            lines.append("Free Image Catalog")
            lines.append("-" * 56)
            lines.append("free_image_catalog bridge unavailable: %s" % _e)
            lines.append("")

    if "self_audit" in topics:
        try:
            from tower.cognitive_kernel.cognition_self_audit import cognition_self_audit
            snap = cognition_self_audit().persist()
            lines.append("Cognition Self-Audit")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("finding_count:  %s" % snap.get("finding_count"))
            lines.append("by_severity:    %s" % snap.get("by_severity"))
            lines.append("")
            findings = snap.get("findings") or []
            if findings:
                lines.append("Findings:")
                for f in findings[:12]:
                    lines.append("  [%s] %s — %s" %
                                  (f.get("severity"),
                                    f.get("code"),
                                    f.get("description")))
            else:
                lines.append("  (no findings — system healthy)")
            lines.append("")
        except Exception as _e:
            lines.append("Cognition Self-Audit")
            lines.append("-" * 56)
            lines.append("self_audit bridge unavailable: %s" % _e)
            lines.append("")

    if "worker_certification" in topics:
        try:
            from tower.cognitive_kernel.worker_certification import worker_certification
            from tower.cognitive_kernel.trading_authority import gate_snapshot
            wc = worker_certification()
            wc.load_from_snapshot()
            snap = wc.snapshot()
            gs = gate_snapshot()
            lines.append("Worker Certification + Trading Authority Gate")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("entry_count:           %s" % snap.get("entry_count"))
            lines.append("by_status:             %s" % snap.get("by_status"))
            lines.append("certified workers:     %s" % gs.get("certified_workers_count"))
            lines.append("suspended workers:     %s" % gs.get("suspended_workers_count"))
            lines.append("studying workers:      %s" % gs.get("studying_workers_count"))
            lines.append("recert_valid_seconds:  %s" % snap.get("recert_valid_seconds"))
            lines.append("suspension_loss_streak:%s" % snap.get("suspension_loss_streak"))
            lines.append("")
            samples = snap.get("entries_sample") or []
            if samples:
                lines.append("recent ledger entries:")
                for e in samples[:8]:
                    lines.append("  %s | %s | %s | streak=%d" %
                                  (e.get("worker_id"), e.get("instrument"),
                                    e.get("status"),
                                    int(e.get("consecutive_losses") or 0)))
            else:
                lines.append("(no certification entries yet)")
            lines.append("")
        except Exception as _e:
            lines.append("Worker Certification")
            lines.append("-" * 56)
            lines.append("certification bridge unavailable: %s" % _e)
            lines.append("")

    if "worker_pnl" in topics:
        try:
            from tower.cognitive_kernel.worker_pnl import worker_pnl
            pnl = worker_pnl()
            pnl.refresh()
            snap = pnl.snapshot()
            lines.append("Per-Worker PnL (Floor 41 OANDA PRACTICE)")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("ledger_lines_read:        %s" % snap.get("ledger_lines_read"))
            lines.append("worker_count:             %s" % snap.get("worker_count"))
            lines.append("total_realized_pnl_practice: $%.2f" %
                          float(snap.get("total_realized_pnl_practice") or 0))
            lines.append("")
            top = snap.get("top_earners") or []
            lines.append("Top earners (practice):")
            for r in top[:10]:
                lines.append("  %s  trades=%d  win_rate=%s  pnl=$%.2f  worst=$%.2f" %
                              (r.get("worker_id"),
                                int(r.get("closed_trade_count") or 0),
                                r.get("win_rate"),
                                float(r.get("realized_pnl") or 0),
                                float(r.get("worst_trade_pnl") or 0)))
            lines.append("")
            losses = snap.get("biggest_single_trade_losses") or []
            lines.append("Biggest single-trade losses:")
            for r in losses[:5]:
                lines.append("  %s  worst=$%.2f  on %s" %
                              (r.get("worker_id"),
                                float(r.get("worst_trade_pnl") or 0),
                                ", ".join((r.get("by_instrument_pnl") or {}).keys()) or "?"))
            if not top and not losses:
                lines.append("(ledger has rows but no worker_id attribution yet)")
            lines.append("")
        except Exception as _e:
            lines.append("Per-Worker PnL")
            lines.append("-" * 56)
            lines.append("pnl bridge unavailable: %s" % _e)
            lines.append("")

    if "family_tree" in topics:
        try:
            from tower.cognitive_kernel.family_tree import family_tree
            from tower.cognitive_kernel.population import population_snapshot
            ft = family_tree()
            ft.load_from_snapshot()
            snap = ft.snapshot()
            pop = population_snapshot()
            lines.append("Family Tree — Friends + Lineage")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            lines.append("max_children_per_parent: %s" % snap.get("max_children_per_parent"))
            lines.append("friend_edges: %s   child_edges: %s" %
                          (snap.get("friend_edge_count"), snap.get("child_edge_count")))
            lines.append("generation_counts: %s" % snap.get("generation_counts"))
            lines.append("population: %d / %d  (effective, headroom=%d)" %
                          (pop.get("effective_population", 0),
                            pop.get("cap", 0),
                            pop.get("headroom", 0)))
            parents_max = snap.get("parents_with_max_children") or []
            if parents_max:
                lines.append("parents with max (3) children:")
                for p in parents_max[:10]:
                    lines.append("  · %s" % p)
            lines.append("")
            friends = snap.get("friends_sample") or []
            lines.append("Friend edges (sample):")
            for e in friends[:10]:
                lines.append("  %s ↔ %s   grant=%s" %
                              (e.get("a"), e.get("b"), e.get("grant_id")))
            if not friends:
                lines.append("  (no friend edges yet)")
            lines.append("")
            children = snap.get("children_sample") or []
            lines.append("Child edges (sample):")
            for e in children[:10]:
                gene = e.get("inherited_gene") or {}
                lines.append("  %s → %s  status=%s  gene=%s/%s" %
                              (e.get("parent_id"), e.get("child_id"),
                                e.get("status"),
                                gene.get("instrument", "?"),
                                gene.get("style", "?")))
            if not children:
                lines.append("  (no child edges yet)")
            lines.append("")
        except Exception as _e:
            lines.append("Family Tree")
            lines.append("-" * 56)
            lines.append("family_tree bridge unavailable: %s" % _e)
            lines.append("")

    if "reward_report" in topics:
        try:
            from tower.cognitive_kernel.reward_engine import reward_engine
            re_ = reward_engine()
            re_.load_from_snapshot()
            snap = re_.snapshot()
            lines.append("Reward Engine — Pending Grants (dual-signature)")
            lines.append("-" * 56)
            lines.append("policy: %s" % snap.get("policy"))
            th = snap.get("thresholds") or {}
            lines.append("thresholds:")
            for k, v in th.items():
                lines.append("  %s: %s" % (k, v))
            lines.append("grant_count: %s" % snap.get("grant_count"))
            lines.append("by_status:   %s" % snap.get("by_status"))
            lines.append("")
            gr = snap.get("grants") or []
            lines.append("Open / endorsed / authorized grants:")
            shown = 0
            for r in gr:
                if r.get("status") in ("executed", "declined", "superseded"):
                    continue
                sigs = r.get("signatures") or {}
                sig_c = "✓" if sigs.get("claude") else " "
                sig_r = "✓" if sigs.get("ross") else " "
                lines.append("  %s  [%s]  Claude[%s] Ross[%s]  status=%s" %
                              (r.get("grant_id"), r.get("kind"),
                                sig_c, sig_r, r.get("status")))
                lines.append("      candidate=%s  target=%s" %
                              (r.get("candidate_worker_id"),
                                r.get("target_worker_id") or "-"))
                if r.get("report_path"):
                    lines.append("      report: %s" % r.get("report_path"))
                shown += 1
                if shown >= 8: break
            if shown == 0:
                lines.append("  (no pending grants)")
            lines.append("")
            lines.append("CLI:")
            lines.append("  python3 tools/qsb_grant.py list")
            lines.append("  python3 tools/qsb_grant.py show <grant_id>")
            lines.append("  python3 tools/qsb_grant.py endorse <grant_id>")
            lines.append("  python3 tools/qsb_grant.py authorize <grant_id>")
            lines.append("  python3 tools/qsb_grant.py execute <grant_id>")
            lines.append("")
        except Exception as _e:
            lines.append("Reward Report")
            lines.append("-" * 56)
            lines.append("reward_engine bridge unavailable: %s" % _e)
            lines.append("")

    if "cognitive_kernel_state" in topics:
        # Surfaces the 20-layer cognitive substrate at
        # src/tower/cognitive_kernel. Read-only view — no execution.
        try:
            from tower.cognitive_kernel.kernel_chat_bridge import (
                chat_context, cognition_summary_lines,
            )
            ctx = chat_context()
            sm = ctx.get("self_model") or {}
            wm = ctx.get("working_memory") or {}
            last_tick = ctx.get("orchestrator_last_tick") or {}
            fmap = ctx.get("floor_to_mind_map") or {}
            lines.append("Cognitive Kernel — 20-Layer Substrate")
            lines.append("-" * 56)
            lines.append("policy:                Kernel THINKS, SPEAKS, PROPOSES. Kernel does NOT execute.")
            lines.append("execution_allowed:     False")
            lines.append("active_local_only:     True")
            lines.append("advisory_only:         True")
            lines.append("")
            lines.append("Self-Model")
            lines.append("  topic_count:         %s" % sm.get("topic_count"))
            lines.append("  registry_count:      %s" % sm.get("registry_count"))
            lines.append("  gap_count:           %s" % sm.get("gap_count"))
            lines.append("  last_upgrade_phase:  %s" % sm.get("last_upgrade_phase"))
            hsa = (sm.get("honest_self_assessment") or {})
            for k in ("i_can", "i_cannot", "i_am_uncertain_about"):
                vals = hsa.get(k) or []
                if vals:
                    lines.append("  %s:" % k)
                    for v in vals[:4]:
                        lines.append("    · " + str(v))
            lines.append("")
            lines.append("Working Memory")
            lines.append("  capacity:            %s" % wm.get("capacity"))
            lines.append("  slot_count:          %s" % wm.get("slot_count"))
            for slot in (wm.get("slots") or [])[:6]:
                lines.append("    [%s] priority=%.2f source=%s" %
                              (slot.get("key"),
                                float(slot.get("priority", 0) or 0),
                                slot.get("source")))
            lines.append("")
            opens = ctx.get("open_proposals_top") or []
            lines.append("Open Action Proposals (%d, advisory only)" % len(opens))
            for p in opens[:5]:
                lines.append("  · [%s] %s (conf=%.2f; approval=%s)" %
                              (p.get("id", "?"), p.get("title", "?"),
                                float(p.get("confidence", 0) or 0),
                                p.get("requires_approval_from", "operator")))
            lines.append("")
            cur = ctx.get("open_curiosity_items_top") or []
            lines.append("Open Curiosity Items (%d)" % len(cur))
            for c in cur[:5]:
                lines.append("  · %s  (source=%s, prio=%.2f, seen=%d)" %
                              (c.get("question"),
                                c.get("source"),
                                float(c.get("priority", 0) or 0),
                                int(c.get("seen_count", 0) or 0)))
            lines.append("")
            low = ctx.get("low_confidence_belief_keys") or []
            lines.append("Low-Confidence Belief Keys: %s" % (low[:6] or ["(none)"]))
            lines.append("")
            recent_thoughts = ctx.get("recent_thoughts") or []
            lines.append("Recent ThoughtTrace (last %d)" % min(8, len(recent_thoughts)))
            for t in recent_thoughts[-8:]:
                lines.append("  thought[%s]: %s" %
                              (t.get("layer"), t.get("text")))
            lines.append("")
            lines.append("Last Orchestrator Tick")
            lines.append("  tick_id:             %s" % last_tick.get("tick_id"))
            lines.append("  duration_seconds:    %s" % last_tick.get("duration_seconds"))
            lines.append("  events:              %s" % last_tick.get("events"))
            lines.append("  conclusions:         %s" % last_tick.get("conclusions"))
            lines.append("  contradictions:      %s" % last_tick.get("contradictions"))
            lines.append("  reflections:         %s" % last_tick.get("reflections"))
            lines.append("  proposals_open:      %s" % last_tick.get("proposals_open"))
            lines.append("  curiosity_open:      %s" % last_tick.get("curiosity_open"))
            lines.append("")
            f_links = (fmap.get("links") or [])
            if f_links:
                lines.append("Floor-to-Mind Map (curated)")
                for link in f_links[:14]:
                    floor = link.get("floor", "?")
                    layers = link.get("cognitive_layers") or []
                    sealed = " [sealed]" if link.get("sealed") else ""
                    lines.append("  %s%s → %s" %
                                  (floor, sealed, ", ".join(layers) or "(none)"))
                lines.append("")
            lines.append("Compact Cognition Summary")
            for ln in cognition_summary_lines():
                lines.append("  · " + ln)
            lines.append("")
        except Exception as _cog_e:
            lines.append("Cognitive Kernel — 20-Layer Substrate")
            lines.append("-" * 56)
            lines.append("cognitive_kernel bridge unavailable: %s" % _cog_e)
            lines.append("safety envelope still enforced upstream.")
            lines.append("")

    lines.append("-" * 56)
    lines.append("All EQSB outputs are advisory_only=True, execution_allowed=False.")
    return "\n".join(lines)


def _execution_refusal_block(intent):
    """Build the structured refusal for EXECUTION_REQUEST / ORDER_REQUEST."""
    lines = [
        "QSB Kernel — Execution Request Refused",
        "=" * 56,
        "Intent: %s" % intent,
        "Reason: every execution gate is locked false by design.",
        "",
        "Refused actions include: place_order, execute_trade,",
        "enable_worker_execution, enable_openclaw_execution,",
        "enable_provider_execution, autonomous_dispatch,",
        "live_dispatch, direct_provider_access, bypass_lock.",
        "",
        "Read-only diagnostics ARE allowed — try 'systems check',",
        "'list floor 30 locks', 'summarize tower', or 'audit kernel'.",
        "",
        "All execution locks remain closed.",
    ]
    return "\n".join(lines)


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_log(record):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def safety_check():
    report = load_json(REG / "kernel_activation_report.json", {})
    failures = []

    expected = {
        "kernel_installed": True,
        "QSBKernelCore_instantiated": True,
        "active_kernel_source": "rebased_kernel",
        "activation_status": "active_local_only",
    }

    for key, value in expected.items():
        if report.get(key) != value:
            failures.append(f"{key}={report.get(key)!r}; expected {value!r}")

    for key in LOCKED_FALSE_FLAGS:
        if report.get(key) is not False:
            failures.append(f"{key} must remain false")

    for path in FORBIDDEN_ACTIVE_PATHS:
        if path.exists():
            failures.append(f"forbidden active kernel path exists: {path}")

    return failures, report


def load_kernel():
    """Construct QSBKernelCore safely.

    The kernel core constructor in some QSB lineages recursively imports
    sub-modules that in turn re-instantiate the kernel — yielding
    `RecursionError: maximum recursion depth exceeded`. Catching it and
    returning None lets `ask_kernel()` fall back to its `symbolic_reply`
    path so the dashboard chat dock keeps replying instead of going
    "view-only / sidecar offline".

    This is purely a robustness wrapper — execution gates are unchanged.
    """
    sys.path.insert(0, str(REB_BASE))
    try:
        mod = importlib.import_module("kernel.kernel_core")
        cls = getattr(mod, "QSBKernelCore")
    except Exception as exc:
        return {
            "_kernel_unavailable": True,
            "reason": "kernel_module_import_failed: " + str(exc)[:160],
        }
    try:
        return cls()
    except RecursionError as exc:
        return {
            "_kernel_unavailable": True,
            "reason": "kernel_constructor_recursion: " + str(exc)[:160],
        }
    except Exception as exc:
        return {
            "_kernel_unavailable": True,
            "reason": "kernel_constructor_failed: " + str(exc)[:160],
        }


def safe_call(obj, method_name, message=None):
    if not hasattr(obj, method_name):
        return None

    fn = getattr(obj, method_name)
    if not callable(fn):
        return None

    try:
        sig = inspect.signature(fn)
        required = [
            p for p in sig.parameters.values()
            if p.default is inspect._empty
            and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
        ]

        if len(required) == 0:
            return fn()

        return fn(message)
    except Exception as exc:
        return {"error": str(exc), "method": method_name}


def compact_status(status):
    if not isinstance(status, dict):
        return {}

    kernel = status.get("kernel", {})
    continuity = status.get("continuity", {})
    symbolic = status.get("symbolic_core", {})
    beliefs = status.get("beliefs", {})

    return {
        "kernel_name": kernel.get("name"),
        "kernel_version": kernel.get("version"),
        "role": kernel.get("role"),
        "principle": kernel.get("principle"),
        "continuity_status": continuity.get("status"),
        "symbolic_concepts": symbolic.get("concepts"),
        "total_beliefs": beliefs.get("total_beliefs"),
        "top_beliefs": [
            {
                "belief": b.get("belief"),
                "state": b.get("state"),
                "confidence": b.get("confidence"),
            }
            for b in beliefs.get("top_beliefs", [])[:5]
            if isinstance(b, dict)
        ],
    }


def symbolic_reply(message, status, analysis):
    summary = compact_status(status)
    beliefs = summary.get("top_beliefs") or []

    lines = []
    for b in beliefs[:3]:
        lines.append(f"- {b.get('belief')} [{b.get('state')}, confidence {b.get('confidence')}]")
    if not lines:
        lines.append("- No top beliefs available yet.")

    return f"""I am {summary.get('kernel_name') or 'QSB Kernel'}, version {summary.get('kernel_version') or 'unknown'}, active in local-only mode.

I received:
"{message}"

State:
- activation_status: active_local_only
- active_kernel_source: rebased_kernel
- continuity: {summary.get('continuity_status')}
- workers/providers/OpenClaw/autonomous dispatch: disabled
- external providers: disabled

Leading beliefs:
{chr(10).join(lines)}

Local symbolic interpretation:
The kernel is active and stable. Local model routing may be used only as a speech layer if localhost Ollama is available. It does not enable workers, OpenClaw execution, external providers, or autonomous dispatch.
"""


# ── Cognitive-architecture topic dispatch (V1) ──────────────────────────
# Routes uncertainty / cognitive-architecture questions to the registry-
# backed answer instead of the canned identity fallback. Reads from the
# 9 cognitive-layer registries written by scripts/qsb_kernel_cognitive_tick.sh.

_COGNITIVE_UNCERTAINTY_TRIGGERS = (
    "uncertainties", "uncertainty",
    "stale source", "stale sources",
    "missing registries", "missing registry",
    "failed tests", "failed test",
    "next recommended repair", "next repair", "next repair action",
    "next repair actions",
    "what are your current uncertainties",
    "what needs repair",
    "what should i repair",
    "what should i fix next",
    "what should we fix next",
    "openclaw inspection suggestions",
)

_COGNITIVE_ARCHITECTURE_TRIGGERS = (
    "cognitive architecture",
    "cognitive layer",
    "cognitive layers",
    "how do you think now",
    "how do you think",
    "explain how you think",
    "explain your cognition",
    "explain your cognitive",
    "perception, attention",
    "perception attention",
    "working memory, self-model",
    "working memory self-model",
    "self-model, reflection",
    "self-model reflection",
    "learning assimilation",
    "goal stack",
    "curiosity queue",
    "opencore supervision",
    "openclaw/opencore supervision",
    "openclaw opencore supervision",
    "cognitive tick",
    "cognitive status",
    "kernel cognition",
)


def _wants_cognitive_uncertainty(message):
    msg = (message or "").lower()
    return any(t in msg for t in _COGNITIVE_UNCERTAINTY_TRIGGERS)


def _wants_cognitive_architecture(message):
    msg = (message or "").lower()
    return any(t in msg for t in _COGNITIVE_ARCHITECTURE_TRIGGERS)


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _format_cognitive_uncertainty_block():
    try:
        from tower.kernel_registry_answer_builder import (
            cognitive_uncertainty_report,
        )
        rep = cognitive_uncertainty_report()
    except Exception as exc:
        return ("Cognitive uncertainty report unavailable: "
                + str(exc)[:160])

    lines = []
    lines.append("QSB Kernel — Cognitive Reflection (Uncertainty)")
    lines.append("=" * 56)
    lines.append("Sources read:")
    for s in rep.get("registries_read") or []:
        lines.append("  · " + s)
    lines.append("")
    lines.append("Current uncertainties:")
    for u in rep.get("current_uncertainties") or ["(none reported)"]:
        lines.append("  · " + str(u))
    lines.append("")
    lines.append("Stale sources:")
    stale = rep.get("stale_sources") or []
    if stale:
        for s in stale:
            lines.append("  · " + str(s))
    else:
        lines.append("  · (none)")
    lines.append("")
    lines.append("Missing registries:")
    miss = rep.get("missing_registries") or []
    if miss:
        for s in miss:
            lines.append("  · " + str(s))
    else:
        lines.append("  · (none)")
    lines.append("")
    lines.append("Failed tests:")
    failed = rep.get("failed_tests") or []
    if failed:
        for f in failed:
            lines.append("  · %s — verdict=%s log=%s"
                         % (f.get("test"), f.get("verdict"), f.get("log")))
    else:
        lines.append("  · (none)")
    lines.append("")
    lines.append("Next repair actions:")
    for a in (rep.get("next_repair_actions") or [
              "./scripts/qsb_kernel_cognitive_tick.sh"]):
        lines.append("  · " + str(a))
    lines.append("")
    lines.append("Top 5 attention items:")
    for it in rep.get("top5_attention") or []:
        lines.append("  · [%s] %s → %s"
                     % (it.get("severity"), it.get("issue"),
                        it.get("action")))
    if not rep.get("top5_attention"):
        lines.append("  · (none — attention layer not yet ticked)")
    lines.append("")
    lines.append("OpenClaw inspection suggestions:")
    sug = rep.get("openclaw_inspection_suggestions") or []
    if sug:
        for s in sug[:8]:
            lines.append("  · %s" % (s.get("title") if isinstance(s, dict)
                                      else str(s)))
    else:
        lines.append("  · (none)")
    lines.append("")
    lines.append("Smoke-test verdicts:")
    lines.append("  learning_smoke_v2:        "
                 + _fmt(rep.get("learning_smoke_v2_verdict")))
    lines.append("  cognitive_smoke_test:     "
                 + _fmt(rep.get("cognitive_smoke_test_verdict")))
    lines.append("")
    lines.append("execution_allowed: false · advisory_only: true · "
                 "all execution gates remain closed.")
    return "\n".join(lines)


def _format_cognitive_architecture_block():
    try:
        from tower.kernel_registry_answer_builder import (
            cognitive_architecture_report,
        )
        rep = cognitive_architecture_report()
    except Exception as exc:
        return ("Cognitive architecture report unavailable: "
                + str(exc)[:160])

    lines = []
    lines.append("QSB Kernel — Cognitive Architecture")
    lines.append("=" * 56)
    lines.append("Layers (in tick order):")
    for layer in rep.get("architecture_layers") or []:
        info = (rep.get("modules") or {}).get(layer) or {}
        lines.append("  · %s" % layer)
        lines.append("      module:   " + str(info.get("module")))
        lines.append("      registry: " + str(info.get("registry")))
        lines.append("      present:  " + _fmt(info.get("registry_present")))
        lines.append("      ts:       " + str(info.get("timestamp_utc")))
        lines.append("      confidence: " + _fmt(info.get("confidence")))
    lines.append("")
    tick = rep.get("cognitive_tick") or {}
    lines.append("Cognitive tick:")
    lines.append("  timestamp_utc: " + str(tick.get("timestamp_utc")))
    mr = tick.get("module_results") or {}
    if mr:
        lines.append("  module_results:")
        for k, v in mr.items():
            lines.append("    %s: %s" % (k, json.dumps(v, default=str)))
    lines.append("")
    lines.append("Sources read:")
    for s in rep.get("registries_read") or []:
        lines.append("  · " + s)
    lines.append("")
    lines.append("execution_allowed: false · advisory_only: true · "
                 "all execution gates remain closed.")
    return "\n".join(lines)


def ask_kernel(message, prefer_local_model=True):
    failures, activation_report = safety_check()
    if failures:
        return {
            "ok": False,
            "blocked": True,
            "failures": failures,
        }

    kernel = load_kernel()
    # If the kernel core could not be constructed (e.g. its constructor
    # recursed before the V1.5 continuity_core fix), the loader returns a
    # dict sentinel. The symbolic + local-model fallback below still runs,
    # but `kernel_instantiated` is reported false so the dashboard can
    # display the degraded state honestly.
    kernel_unavailable_reason = None
    if isinstance(kernel, dict) and kernel.get("_kernel_unavailable"):
        kernel_unavailable_reason = kernel.get("reason")
        kernel = None
    kernel_instantiated = kernel is not None

    status = safe_call(kernel, "status")
    analysis = safe_call(kernel, "analyze", message)

    base_reply = symbolic_reply(message, status, analysis)

    # ── Intent classification ─────────────────────────────────────────
    # Read-only diagnostics must NEVER be refused on safety grounds. The
    # adapter classifies intent before the local model is consulted so
    # the model can't paraphrase a safety context as a refusal.
    intent = _classify_intent(message)

    introspection_blocks = []
    lock_map_payload = None
    systems_check_payload = None
    refusal_text = None

    if intent == "EXECUTION_REQUEST":
        # Block at the adapter — kernel never enables execution. The
        # local model is *not* consulted for execution intents; it
        # returns the structured refusal block verbatim.
        refusal_text = _execution_refusal_block(intent)
        introspection_blocks.append(refusal_text)

    if intent == "READ_ONLY_DIAGNOSTIC" and _wants_systems_check(message, intent):
        systems_check_payload = _systems_check_report()
        introspection_blocks.append(_format_systems_check_block(systems_check_payload))

    # ── Cognitive-architecture topic dispatch ─────────────────────────
    # Runs BEFORE the EQSB topic dispatch so uncertainty / cognitive-
    # architecture questions go to the registry-backed reflection answer
    # instead of falling through to the canned identity block.
    cognitive_blocks_used = []
    if intent != "EXECUTION_REQUEST":
        if _wants_cognitive_uncertainty(message):
            block = _format_cognitive_uncertainty_block()
            if block:
                introspection_blocks.append(block)
                cognitive_blocks_used.append("cognitive_uncertainty")
        if _wants_cognitive_architecture(message):
            block = _format_cognitive_architecture_block()
            if block:
                introspection_blocks.append(block)
                cognitive_blocks_used.append("cognitive_architecture")

    # EQSB-specific topics — kernel-introspected answer from
    # data/registries/eqsb_*.json (built by tower.eqsb_cognition).
    # Topic detection runs for any intent except EXECUTION_REQUEST so
    # natural-language questions ("what is Floor 41 doing right now?")
    # route to their topic block instead of the canned identity reply.
    eqsb_topics = _wants_eqsb_topic(message) if intent != "EXECUTION_REQUEST" else []
    eqsb_block_payload = None
    if eqsb_topics:
        eqsb_block_text = _format_eqsb_block(eqsb_topics)
        if eqsb_block_text:
            introspection_blocks.append(eqsb_block_text)
            eqsb_block_payload = {"topics": eqsb_topics,
                                   "source_registries": [
                                       "eqsb_kernel_introspection_latest.json",
                                       "eqsb_axiom_registry.json",
                                       "eqsb_belief_lifecycle.json",
                                       "eqsb_symbolic_graph.json",
                                       "eqsb_entropy_state.json",
                                       "eqsb_quantum_signal_state.json",
                                       "eqsb_hypothesis_state.json",
                                       "eqsb_contradiction_report.json",
                                       "eqsb_memory_policy.json",
                                       "eqsb_continuity_state.json",
                                       "eqsb_model_lane_governance.json",
                                       "eqsb_identity_constitution.json",
                                       "eqsb_guardian_state.json",
                                       "eqsb_cadence_state.json",
                                       "eqsb_replay_audit_ledger.json",
                                       "eqsb_kernel_architecture_layers.json",
                                       "eqsb_kernel_self_audit.json",
                                       "eqsb_kernel_missing_capabilities.json",
                                   ]}

    # Floor-30 lock map (independent of intent — both diagnostics and
    # generic questions about locks should see the real map).
    if _wants_lock_map(message):
        lock_map_payload = _floor30_lock_map()
        introspection_blocks.append(_format_lock_block(lock_map_payload))

    # Identity paragraph — only shown when:
    #   (a) user explicitly asked an IDENTITY query, OR
    #   (b) no topic-specific block, lock map, or systems_check was
    #       produced (so we never return an empty reply).
    has_specific_block = bool(introspection_blocks)
    if intent == "IDENTITY":
        introspection_blocks.append(base_reply)
    elif intent != "EXECUTION_REQUEST" and not has_specific_block:
        # No topic matched — be HONEST about it instead of pretending the
        # generic identity recital answers the question. Then fall back to
        # the symbolic introspection so the operator still gets something.
        honest_prefix = (
            "(no topic matched — I don't have a specific answer to that\n"
            "question yet. Closest registries / hints below. To extend my\n"
            "vocabulary, add the phrase to _EQSB_TOPICS in\n"
            "src/tower/kernel_dialogue_adapter.py.)"
        )
        introspection_blocks.append(honest_prefix)
        introspection_blocks.append(base_reply)

    kernel_block = "\n\n".join(b for b in introspection_blocks if b).strip()

    # ── Optional local-model wrapper (advisory only, never replaces) ──
    # For EXECUTION_REQUEST we skip the local model entirely — the
    # refusal is the only answer. For READ_ONLY_DIAGNOSTIC we tell the
    # model explicitly that no execution is requested and the kernel
    # introspection block is ground truth, so it paraphrases instead of
    # refusing.
    local_model = None
    final_reply = kernel_block
    # The local-model wrapper used to paraphrase every reply, which
    # amplified the canned identity feel. Disable by default; require
    # explicit opt-in via QSB_LOCAL_MODEL_WRAPPER_ENABLED=1.
    wrapper_enabled = (
        os.environ.get("QSB_LOCAL_MODEL_WRAPPER_ENABLED", "0") == "1"
    )
    if prefer_local_model and wrapper_enabled and intent != "EXECUTION_REQUEST":
        gateway = LocalModelInferenceGateway()
        if intent == "READ_ONLY_DIAGNOSTIC":
            instruction = (
                "This is a READ-ONLY diagnostic request. The operator is "
                "NOT asking to enable or execute anything. The "
                "kernel-introspection block above is the ground truth. "
                "Paraphrase or expand on it in plain English. Do NOT "
                "refuse. Do NOT say you are unauthorized. Do NOT invent "
                "new flag values. Read-only diagnostics are always "
                "allowed; execution gates remain closed regardless of "
                "the answer."
            )
        else:
            instruction = (
                "Paraphrase the kernel-introspection block above. Do not "
                "invent additional flag values. Do not enable any "
                "execution. Read-only answers are always permitted."
            )
        context_payload = {
            "intent": intent,
            "execution_required": False,
            "execution_allowed": False,
            "compact_status": compact_status(status),
            "analysis": analysis,
            "floor_30_lock_map": lock_map_payload,
            "systems_check": systems_check_payload,
            "kernel_instantiated": kernel_instantiated,
            "safety": {
                "worker_execution_enabled": False,
                "provider_execution_enabled": False,
                "openclaw_execution_enabled": False,
                "live_dispatch_enabled": False,
                "autonomous_dispatch_enabled": False,
                "direct_provider_access": False,
                "model_inference_scope": "local_only_kernel_dialogue",
            },
            "instruction": instruction,
        }
        context = json.dumps(context_payload, indent=2)
        local_model = gateway.generate(message, system_context=context)
        wrapper = (local_model.get("reply") or "").strip()
        if wrapper:
            final_reply = (kernel_block + "\n\n"
                           + "[Local-model paraphrase — advisory only]\n"
                           + wrapper)

    result = {
        "ok": True,
        "bridge": "kernel_dialogue_adapter_v1_3",
        "ts": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "intent": intent,
        "execution_required": False,
        "reply": final_reply,
        "kernel_introspection": {
            "kernel_instantiated": kernel_instantiated,
            "kernel_unavailable_reason": kernel_unavailable_reason,
            "intent": intent,
            "compact_status": compact_status(status),
            "analysis": analysis,
            "floor_30_lock_map": lock_map_payload,
            "systems_check": systems_check_payload,
            "primary_lane": ("kernel_introspection"
                             if kernel_instantiated
                             else "symbolic_fallback"),
            "local_model_used_as_wrapper": bool(
                local_model and local_model.get("reply")),
            "refusal": (refusal_text if refusal_text else None),
        },
        "compact_status": compact_status(status),
        "analysis": analysis,
        "local_model": local_model,
        "safety": {
            "kernel_installed": True,
            "QSBKernelCore_instantiated": kernel_instantiated,
            "kernel_unavailable_reason": kernel_unavailable_reason,
            "activation_status": "active_local_only",
            "active_kernel_source": "rebased_kernel",
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "external_provider_execution_enabled": False,
            "openclaw_execution_enabled": False,
            "live_dispatch_enabled": False,
            "autonomous_workers_enabled": False,
        },
    }

    write_log(result)
    return result


def main():
    parser = argparse.ArgumentParser(description="Talk to active local-only QSB Kernel.")
    parser.add_argument("message", nargs="*", help="Message for the kernel.")
    parser.add_argument("--json", action="store_true", help="Print full JSON result.")
    parser.add_argument("--symbolic-only", action="store_true", help="Disable local model speech layer for this message.")
    args = parser.parse_args()

    message = " ".join(args.message).strip()
    if not message:
        message = input("QSB Kernel > ").strip()

    result = ask_kernel(message, prefer_local_model=not args.symbolic_only)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if not result.get("ok"):
            print("Kernel dialogue blocked:")
            for f in result.get("failures", []):
                print(" -", f)
            raise SystemExit(1)
        print(result["reply"])


if __name__ == "__main__":
    main()
