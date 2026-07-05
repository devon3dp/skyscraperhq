"""Accounts Department V1 — Floor 44.

Read-only collection of P&L summaries from trading-telemetry endpoints +
paper ledger entries. Labels every datum LIVE_READ_ONLY / PAPER_ONLY /
NOT_CONFIGURED. Never moves money. Never enables trading.
"""

from datetime import datetime, timezone
from pathlib import Path
import json

from .safety_contract import stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LOG_PATH = ROOT / "logs/tower_ops/accounts_events.jsonl"


def _now(): return datetime.now(timezone.utc).isoformat()


def _label_for(d):
    if not d: return "NOT_CONFIGURED"
    if d.get("label") == "LIVE READ-ONLY": return "LIVE_READ_ONLY"
    if d.get("status") == "not_configured": return "NOT_CONFIGURED"
    if d.get("paper_only"): return "PAPER_ONLY"
    return "NOT_CONFIGURED"


def trading_summary():
    from .trading_telemetry import (oanda_account, oanda_pnl, binance_account,
                                     binance_pnl, stocks_account, stocks_pnl)
    oa = oanda_account();  op = oanda_pnl()
    ba = binance_account(); bp = binance_pnl()
    sa = stocks_account();  sp = stocks_pnl()
    return stamp_safe({
        "ok": True, "ts": _now(),
        "oanda": {
            "account_label": _label_for(oa),
            "pnl_label":     _label_for(op),
            "balance":       oa.get("balance"),
            "NAV":           oa.get("NAV"),
            "unrealized_pl": op.get("unrealized_pl") if op.get("ok") else None,
            "realized_pl_today": op.get("realized_pl_today") if op.get("ok") else None,
            "currency":      oa.get("currency"),
            "account_id_redacted": oa.get("account_id_redacted"),
            "live_trading_enabled": False, "order_execution_enabled": False,
        },
        "binance": {
            "account_label": _label_for(ba),
            "pnl_label":     _label_for(bp),
            "environment":   ba.get("environment"),
            "balance_count": ba.get("balance_count"),
            "binance_order_execution_enabled": False,
        },
        "stocks": {
            "account_label": _label_for(sa),
            "pnl_label":     _label_for(sp),
            "environment":   sa.get("environment"),
            "stock_order_execution_enabled": False,
        },
    })


def paper_ledger_summary():
    ledger = ROOT / "data/registries/floor41_paper_ledger.json"
    out = {"label": "PAPER_ONLY", "entry_count": 0, "latest_count": 0,
            "updated_ts": None, "latest_entries": []}
    if ledger.exists():
        try:
            d = json.loads(ledger.read_text(encoding="utf-8"))
            out["entry_count"]    = d.get("entry_count") or 0
            out["latest_count"]   = d.get("latest_entry_count") or 0
            out["updated_ts"]     = d.get("updated_ts")
            out["latest_entries"] = (d.get("latest_entries") or [])[:6]
        except Exception: pass
    return stamp_safe({"ok": True, "ts": _now(), "paper_ledger": out})


def floor_summary(n):
    """Per-floor accounting summary — paper-only / advisory."""
    return stamp_safe({"ok": True, "ts": _now(), "floor_number": n,
                        "floor_id": "floor_{:02d}".format(n) if 1 <= n <= 53 else (
                            "penthouse" if n == 55 else None),
                        "data_label": "PAPER_ONLY",
                        "summary": "Floor accounting is paper-only / advisory. " +
                                    "No real funds are tracked. Execution gates closed."})


def floor_accountants_list():
    """Return one Floor Accountant per populated floor."""
    from .worker_registry import workers as worker_list
    workers = (worker_list().get("workers") or [])
    by_floor = {}
    for w in workers:
        by_floor.setdefault(w.get("floor_assignment"), []).append(w.get("display_name"))
    accountants = []
    for fid, names in by_floor.items():
        accountants.append({"floor_id": fid,
                             "accountant": names[0] if names else None,
                             "team_count": len(names)})
    return stamp_safe({"ok": True, "ts": _now(),
                        "floor_accountants": accountants,
                        "policy": "READ_ONLY — never moves funds"})


def not_configured():
    """List every account/P&L endpoint that's currently not configured."""
    from .trading_telemetry import (oanda_account, binance_account, binance_orders,
                                     binance_pnl, stocks_account, stocks_positions, stocks_pnl)
    items = [
        ("oanda_account",   oanda_account),
        ("binance_account", binance_account),
        ("binance_orders",  binance_orders),
        ("binance_pnl",     binance_pnl),
        ("stocks_account",  stocks_account),
        ("stocks_positions",stocks_positions),
        ("stocks_pnl",      stocks_pnl),
    ]
    out = []
    for name, fn in items:
        d = fn()
        if d.get("status") == "not_configured":
            out.append({"endpoint": name, "reason": d.get("reason")})
    return stamp_safe({"ok": True, "ts": _now(), "not_configured": out})


def status():
    t = trading_summary()
    p = paper_ledger_summary()
    return stamp_safe({"ok": True, "ts": _now(),
                        "overall_status": "healthy",
                        "department": "Accounts Department",
                        "floor_number": 44,
                        "floor_id": "floor_44",
                        "policy": "READ_ONLY — never moves funds, never enables trading",
                        "trading_summary": t,
                        "paper_ledger": p["paper_ledger"]})
