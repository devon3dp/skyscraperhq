"""OANDA gauges + charts + approval workflow stream for Floor 41."""

from datetime import datetime, timezone
from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


def gauges():
    from .oanda_practice_trading import account, open_trades, pricing
    ac = account(); ot = open_trades(); pr = pricing()
    if not ac.get("ok"):
        return stamp_safe({"ok": False, "status": "not_configured",
                            "reason": ac.get("reason"),
                            "execution_allowed": False})
    spreads = [(p.get("instrument"), p.get("spread_pips")) for p in (pr.get("prices") or [])]
    return stamp_safe({
        "ok": True, "ts": _now(), "label": "LIVE READ-ONLY",
        "gauges": {
            "balance":         _g(ac.get("balance"),         0, 200000, "GBP"),
            "NAV":             _g(ac.get("NAV"),             0, 200000, "GBP"),
            "unrealized_pl":   _g(ac.get("unrealized_pl"),   -1000, 1000, "GBP"),
            "realized_pl_today":_g(ac.get("realized_pl_today"), -1000, 1000, "GBP"),
            "margin_used":     _g(ac.get("margin_used"),     0, 50000, "GBP"),
            "margin_available":_g(ac.get("margin_available"),0, 200000, "GBP"),
            "open_trades":     _g(ac.get("open_trade_count"),0, 3, "count"),
            "open_positions":  _g(ac.get("open_position_count"),0, 3, "count"),
            "spread_eur_usd":  _g(_pick(spreads, "EUR_USD"), 0, 5, "pips"),
            "spread_gbp_usd":  _g(_pick(spreads, "GBP_USD"), 0, 5, "pips"),
            "spread_usd_jpy":  _g(_pick(spreads, "USD_JPY"), 0, 5, "pips"),
        },
        "live_trading_enabled": False,
        "real_order_execution_enabled": False,
        "oanda_practice_order_execution_enabled": True,
    })


def _pick(rows, instr):
    for k, v in rows:
        if k == instr: return v
    return None


def _g(value, lo, hi, unit):
    if value is None: return {"value": None, "min": lo, "max": hi, "unit": unit, "pct": None}
    try: v = float(value)
    except Exception: v = 0
    rng = (hi - lo) or 1
    pct = max(0, min(100, int(round((v - lo) / rng * 100))))
    return {"value": v, "min": lo, "max": hi, "unit": unit, "pct": pct}


def charts():
    from .oanda_practice_trading import practice_ledger, transactions
    led = practice_ledger().get("entries") or []
    tx  = (transactions(50).get("transactions") or [])
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "OANDA_CHARTS_FROM_LIVE_HISTORY",
        "order_ledger_timeline": [{
            "ts": e.get("ts"), "event": e.get("event"),
            "instrument": e.get("instrument"), "units": e.get("units"), "side": e.get("side"),
        } for e in led],
        "recent_transactions": tx[:30],
        "data_source": "practice_ledger + /v3/accounts/{id}/transactions",
        "execution_allowed": False,
    })


def live_dashboard():
    from .oanda_practice_trading import (account, open_trades, open_positions,
                                          practice_ledger, transactions, pricing)
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "OANDA_LIVE_DASHBOARD",
        "phase": "QSB_TOWER_V1.5",
        "account":        account(),
        "open_trades":    open_trades(),
        "open_positions": open_positions(),
        "transactions":   transactions(20),
        "practice_ledger":practice_ledger(),
        "pricing":        pricing(),
        "gauges":         gauges(),
        "charts":         charts(),
        "approval_flow":  approval_flow(),
        "worker_activity":worker_activity(),
        "execution_mode": "PRACTICE_ONLY",
        "live_trading_enabled":         False,
        "real_order_execution_enabled": False,
        "oanda_practice_order_execution_enabled": True,
    })


def approval_flow():
    from .approval_workflow import pending, status
    return stamp_safe({"ok": True, "ts": _now(),
                        "label": "APPROVAL_FLOW",
                        "stages": ["Proposal", "Floor Manager", "Accounts", "Risk",
                                    "Manual Confirm Gate", "Practice Execution",
                                    "Ledger", "P&L"],
                        "pending":     pending(),
                        "summary":     status(),
                        "execution_allowed": False})


def worker_activity():
    from .live_worker_routes import live_routes
    routes = live_routes().get("worker_routes") or []
    rows = [r for r in routes if (r.get("current_floor") == "floor_41" or
                                    r.get("target_floor") == "floor_41")]
    return stamp_safe({"ok": True, "ts": _now(),
                        "label": "FLOOR_41_WORKER_ACTIVITY",
                        "active_workers": rows[:40],
                        "execution_allowed": False})
