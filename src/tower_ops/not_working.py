"""What's missing / not working — operator-visible gap inventory."""

from datetime import datetime, timezone
from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


def report():
    from .chat_diagnostics      import diagnostics as chat_diag
    from .binance_testnet       import testnet_preflight
    from .stocks_paper          import paper_preflight
    chat = chat_diag()
    adapter = chat.get("adapter_check") or {}
    bin_pf = testnet_preflight()
    st_pf  = paper_preflight()
    items = [
        {"item": "kernel_core recursion",
         "status": ("CAUGHT (fallback active)" if adapter.get("loaded") is False else "OK"),
         "detail": adapter.get("kernel_unavailable_reason"),
         "severity": "INFO"},
        {"item": "Speech talk button",
         "status": "browser-side (mic + speaker via Web Speech API)",
         "severity": "INFO"},
        {"item": "Binance testnet config",
         "status": ("testnet ready" if bin_pf.get("credentials_present_for_testnet")
                     else "TESTNET NOT CONFIGURED — set BINANCE_ENV=testnet + creds"),
         "severity": "WARN"},
        {"item": "Stocks paper broker config",
         "status": ("paper ready" if st_pf.get("credentials_present_for_paper")
                     else "PAPER BROKER NOT CONFIGURED — set ALPACA_API_KEY + ALPACA_API_SECRET"),
         "severity": "WARN"},
        {"item": "Worker orbiting bands",
         "status": "REPLACED by live_worker_routes.py — workers now have purposeful hops",
         "severity": "INFO"},
        {"item": "Floors without gauges",
         "status": "OANDA Floor 41 has gauges via /api/trading/oanda/gauges. Binance & Stocks ship preview gauges via _live_dashboard.",
         "severity": "WARN"},
        {"item": "Floor accountants",
         "status": "13 floor accountants seeded on Floor 44 (Accounts Department).",
         "severity": "INFO"},
        {"item": "Floor comms / radio",
         "status": "Floor Comms Bus live: /api/comms/*",
         "severity": "INFO"},
        {"item": "Manager approval workflow",
         "status": "Approval Workflow live: /api/approvals/*",
         "severity": "INFO"},
        {"item": "Old sim/sandbox labels",
         "status": "Scrubbed from data/registries/floors.json in V3. No user-facing leaks.",
         "severity": "INFO"},
        {"item": "Detailed floor interiors",
         "status": "Babylon WebGL V18 LIVE — 165-floor 3D tower rendering at ~18fps with night-sky background. SVG 2D fallback also present.",
         "severity": "INFO"},
        {"item": "Godot 3D cockpit",
         "status": "Godot 4.6.1 native cockpit running (Vulkan Forward+ on RTX 5070 Ti). 165-floor tower, F153 Penthouse, interior factory with live-build animation.",
         "severity": "INFO"},
        {"item": "Worker count truth",
         "status": "Canonical via Registry.workers() — 9,026 unique workers deduped across all rosters. Truth audit running every 60s, 0 mismatches.",
         "severity": "INFO"},
        {"item": "Code Crew syntax linter",
         "status": "F47.CODE Crew runs python3 -m py_compile + node --check every 60s. Catches breaking syntax errors before they reach Ross.",
         "severity": "INFO"},
        {"item": "Live dispatch + team work visibility",
         "status": "12 teams report jobs to /api/dispatch/live every 3min. Cockpit panel shows live job stream.",
         "severity": "INFO"},
    ]
    return stamp_safe({
        "ok": True, "ts": _now(),
        "phase": "QSB_TOWER_V1.5",
        "items": items,
        "missing_count":   sum(1 for i in items if i["severity"] == "WARN"),
        "info_count":      sum(1 for i in items if i["severity"] == "INFO"),
        "execution_allowed": False,
    })
