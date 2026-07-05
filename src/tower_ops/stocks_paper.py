"""Stocks paper floor V5 — paper broker telemetry + paper-gated orders."""

from datetime import datetime, timezone
import os

from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


def _paper_creds_present():
    return bool(os.environ.get("ALPACA_API_KEY", "").strip()
                 and os.environ.get("ALPACA_API_SECRET", "").strip())


def paper_preflight():
    return stamp_safe({
        "ok": True, "ts": _now(),
        "phase": "QSB_TOWER_V1.5",
        "ALPACA_ENV": os.environ.get("ALPACA_ENV") or "paper",
        "credentials_present_for_paper": _paper_creds_present(),
        "market_data_enabled": True,
        "paper_order_execution_enabled": False,
        "live_trading_enabled": False,
        "stock_order_execution_enabled": False,
        "stock_live_trading_enabled": False,
        "policy": ("PAPER ORDER EXECUTION BLOCKED. Set ALPACA_API_KEY + ALPACA_API_SECRET via "
                    ".env.alpaca to enable paper preview/placement. Real-money execution is "
                    "unconditionally blocked."),
    })


def gauges():
    try:
        from tower_ops.trading_telemetry import stocks_account
        ac = stocks_account()
        return stamp_safe({"ok": True, "ts": _now(),
                            "label": "STOCKS_PAPER_GAUGES",
                            "account_label": ac.get("status") or ac.get("label"),
                            "stock_order_execution_enabled": False,
                            "stock_live_trading_enabled": False})
    except Exception as e:
        return stamp_safe({"ok": False, "error": str(e)[:200],
                            "stock_order_execution_enabled": False})


def quotes():
    return stamp_safe({"ok": True, "ts": _now(),
                        "watched_symbols": ["AAPL","MSFT","NVDA","TSLA","SPY","QQQ"],
                        "label": "STOCKS_QUOTES_PLACEHOLDER",
                        "policy": "Quote stream not wired in V1.5; see stock_exchange_floor module for details."})


def positions():
    if not _paper_creds_present():
        return stamp_safe({"ok": False, "status": "PAPER_BROKER_NOT_CONFIGURED",
                            "reason": "ALPACA_API_KEY + ALPACA_API_SECRET required",
                            "stock_order_execution_enabled": False})
    return stamp_safe({"ok": False, "status": "not_configured",
                        "reason": "positions helper not wired in V1.5 gateway",
                        "stock_order_execution_enabled": False})


def orders():
    if not _paper_creds_present():
        return stamp_safe({"ok": False, "status": "PAPER_BROKER_NOT_CONFIGURED",
                            "stock_order_execution_enabled": False})
    return stamp_safe({"ok": False, "status": "not_configured",
                        "reason": "orders helper not wired in V1.5 gateway",
                        "stock_order_execution_enabled": False})


def pnl():
    if not _paper_creds_present():
        return stamp_safe({"ok": False, "status": "PAPER_BROKER_NOT_CONFIGURED"})
    return stamp_safe({"ok": False, "status": "not_configured",
                        "reason": "P&L helper not wired in V1.5 gateway"})


def paper_order_preview(payload):
    payload = payload or {}
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "STOCKS_PAPER_ORDER_PREVIEW",
        "blocked_for_placement": True,
        "reason": "Paper order placement requires a separate explicit unlock command (V1.5 ships preview-only).",
        "preview": {
            "symbol": (payload.get("symbol") or "").upper(),
            "side":   (payload.get("side") or "").upper(),
            "units":  payload.get("units"),
            "mode":   "PAPER_ONLY",
        },
        "stock_order_execution_enabled": False,
        "stock_live_trading_enabled": False,
        "live_trading_enabled": False,
    })


def place_paper_order(payload):
    return stamp_safe({
        "ok": False, "ts": _now(),
        "blocked": True,
        "reason": "Stocks paper order placement requires a separate explicit unlock command (V1.5 ships preview-only).",
        "stock_order_execution_enabled": False,
        "stock_live_trading_enabled": False,
        "live_trading_enabled": False,
    })


def live_dashboard():
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "STOCKS_LIVE_DASHBOARD",
        "preflight": paper_preflight(),
        "gauges":    gauges(),
        "policy": "PAPER BROKER NOT CONFIGURED · MARKET DATA STATUS: placeholder · ORDER EXECUTION BLOCKED",
        "stock_order_execution_enabled": False,
        "stock_live_trading_enabled": False,
    })
