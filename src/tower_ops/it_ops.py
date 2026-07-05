"""IT / Networking department — Floor 35 (Infrastructure Services).

Observability only. Reports listening ports, known sidecars, connectivity
probes, and which env-credentials are loaded (names only — never values).
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import socket
import threading

from .safety_contract import LOCKED_FALSE, stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LOG_PATH = ROOT / "logs/tower_ops/it_events.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


KNOWN_PORTS = [
    (8765, "qsb_dashboard"),
    (8766, "qsb_kernel_chat_sidecar"),
    (8767, "oanda_floor41_sidecar"),
    (8768, "worker_sandbox_sidecar"),
    (8769, "sandbox_performance_sidecar"),
    (8770, "openclaw_visual_sidecar"),
    (8771, "strategy_intelligence_sidecar"),
    (8772, "strategy_autoloop_correlation_sidecar"),
    (8773, "paper_trade_simulator_sidecar"),
    (8774, "paper_trade_simulator_sidecar"),
    (11434, "ollama_local_inference"),
]


CREDENTIAL_ENV_NAMES = [
    ("OANDA_API_KEY",        "oanda"),
    ("OANDA_ACCOUNT_ID",     "oanda"),
    ("OANDA_ENV",            "oanda"),
    ("BINANCE_API_KEY",      "binance"),
    ("BINANCE_API_SECRET",   "binance"),
    ("BINANCE_ENV",          "binance"),
    ("ALPACA_API_KEY",       "alpaca_stocks"),
    ("ALPACA_API_SECRET",    "alpaca_stocks"),
    ("ALPACA_ENV",           "alpaca_stocks"),
]


def _port_listen(host, port, timeout=0.15):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _dns_probe(host, timeout=0.6):
    try:
        socket.setdefaulttimeout(timeout)
        socket.gethostbyname(host)
        return True
    except Exception:
        return False
    finally:
        socket.setdefaulttimeout(None)


def _append_log(rec):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", _now())
    rec.setdefault("execution_allowed", False)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def status():
    return stamp_safe({
        "ok": True, "ts": _now(),
        "overall_status": "healthy",
        "policy": "OBSERVABILITY ONLY — no autonomous web · no firewall mutation · no service mutation",
        "dashboard_port":   8765,
        "kernel_chat_port": 8766,
        "web_access_autonomous_enabled": False,
        "it_network_observability_enabled": True,
    })


def ports():
    out = []
    for p, label in KNOWN_PORTS:
        out.append({"port": p, "label": label, "listening": _port_listen("127.0.0.1", p)})
    return stamp_safe({"ok": True, "ts": _now(), "ports": out})


def sidecars():
    p = ports().get("ports") or []
    sidecar_rows = []
    for row in p:
        if row["port"] in (8765, 11434): continue
        sidecar_rows.append({"port": row["port"], "label": row["label"],
                             "status": "alive" if row["listening"] else "offline"})
    return stamp_safe({"ok": True, "ts": _now(), "sidecars": sidecar_rows})


def connectivity():
    targets = [
        ("api-fxpractice.oanda.com",  "oanda_practice"),
        ("api.oanda.com",             "oanda_live"),
        ("testnet.binance.vision",    "binance_testnet"),
        ("api.binance.com",           "binance_live"),
        ("paper-api.alpaca.markets",  "alpaca_paper"),
        ("data.alpaca.markets",       "alpaca_data"),
        ("registry.ollama.ai",        "ollama_registry"),
    ]
    rows = [{"host": h, "label": l, "dns_resolvable": _dns_probe(h)} for h, l in targets]
    return stamp_safe({"ok": True, "ts": _now(),
                        "connectivity": rows,
                        "policy": "DNS_PROBE ONLY — no autonomous outbound HTTP"})


def routes():
    """List the dashboard's own /api/* routes we know about. Documentation only."""
    return stamp_safe({
        "ok": True, "ts": _now(),
        "dashboard_routes": [
            "GET /api/unified",
            "GET /api/floor_detail?floor=N",
            "GET /api/kernel_chat_status",
            "GET /api/kernel_chat_history",
            "POST /api/kernel_chat",
            "GET /api/recruitment/status",
            "GET /api/recruitment/workers",
            "POST /api/recruitment/recruit",
            "POST /api/recruitment/assign",
            "POST /api/recruitment/retire",
            "POST /api/recruitment/openclaw_review",
            "GET /api/maintenance/status",
            "GET /api/maintenance/checks",
            "POST /api/maintenance/run_check",
            "POST /api/maintenance/ack_alert",
            "GET /api/security/status",
            "GET /api/security/locks",
            "GET /api/security/incidents",
            "POST /api/security/ack_incident",
            "GET /api/it/status",
            "GET /api/it/ports",
            "GET /api/it/sidecars",
            "GET /api/it/connectivity",
            "GET /api/it/routes",
            "GET /api/research/status",
            "GET /api/research/tasks",
            "POST /api/research/create_task",
            "POST /api/research/complete_task",
            "GET /api/research/reports",
            "GET /api/overseers/status",
            "GET /api/overseers/reports",
            "POST /api/overseers/run_check",
            "GET /api/trading/oanda/account",
            "GET /api/trading/oanda/positions",
            "GET /api/trading/oanda/trades",
            "GET /api/trading/oanda/transactions",
            "GET /api/trading/oanda/pnl",
            "GET /api/trading/binance/account",
            "GET /api/trading/binance/positions",
            "GET /api/trading/binance/orders",
            "GET /api/trading/binance/pnl",
            "GET /api/trading/stocks/account",
            "GET /api/trading/stocks/positions",
            "GET /api/trading/stocks/pnl",
        ],
    })


def credentials_loaded():
    """Boolean-presence map only — NEVER values."""
    out = {}
    for name, group in CREDENTIAL_ENV_NAMES:
        out[name] = {"present": bool(os.environ.get(name, "").strip()), "group": group}
    return stamp_safe({"ok": True, "ts": _now(), "credentials": out,
                        "policy": "NAMES_ONLY — values never returned"})
