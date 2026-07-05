"""Binance testnet/paper floor V5 — public market data + testnet-gated orders."""

from datetime import datetime, timezone
import os

from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


def _get_env_either(*names):
    """Pick the first env var that's set, across the alternate naming forms."""
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v: return v
    return ""


def _testnet_creds_present():
    # Accept either the BINANCE_* convention OR the QSB_BINANCE_TESTNET_*
    # convention used in the Floor 28 vault. Env=testnet is implied when the
    # QSB_BINANCE_TESTNET_URL points at the official testnet host.
    key = _get_env_either("BINANCE_API_KEY", "QSB_BINANCE_TESTNET_API_KEY")
    secret = _get_env_either("BINANCE_API_SECRET", "QSB_BINANCE_TESTNET_API_SECRET")
    if not key or not secret:
        return False
    env = (os.environ.get("BINANCE_ENV") or "").lower()
    if env == "testnet":
        return True
    url = (os.environ.get("QSB_BINANCE_TESTNET_URL") or "").lower()
    return "testnet" in url


def testnet_preflight():
    out = {
        "ok": True, "ts": _now(),
        "phase": "QSB_TOWER_V1.5",
        "BINANCE_ENV": os.environ.get("BINANCE_ENV") or "not_set",
        "credentials_present_for_testnet": _testnet_creds_present(),
        "public_market_data_enabled": True,
        "testnet_order_execution_enabled": False,    # always false until creds + flag align
        "live_trading_enabled": False,
        "real_order_execution_enabled": False,
        "binance_order_execution_enabled": False,
        "binance_live_trading_enabled": False,
        "policy": ("TESTNET ORDER EXECUTION BLOCKED. Set BINANCE_ENV=testnet AND provide "
                    "BINANCE_API_KEY + BINANCE_API_SECRET via .env.binance to enable testnet "
                    "preview/placement. Real-money execution is unconditionally blocked."),
    }
    return stamp_safe(out)


def gauges():
    try:
        from tower.binance_floor import BinanceGateway
        gw = BinanceGateway()
        tickers = gw.ticker_24h(["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"])
        if isinstance(tickers, dict): tickers = [tickers]
        rows = []
        for t in tickers or []:
            sym = t.get("symbol")
            last = float(t.get("lastPrice") or 0)
            chg  = float(t.get("priceChangePercent") or 0)
            vol  = float(t.get("quoteVolume") or 0)
            rows.append({"symbol": sym, "last": last, "pct_change_24h": chg,
                          "quote_volume_24h": vol})
        return stamp_safe({"ok": True, "ts": _now(),
                            "label": "BINANCE_PUBLIC_GAUGES",
                            "gauges": rows,
                            "binance_order_execution_enabled": False,
                            "binance_live_trading_enabled": False})
    except Exception as e:
        return stamp_safe({"ok": False, "error": str(e)[:200],
                            "binance_order_execution_enabled": False})


def open_orders():
    if not _testnet_creds_present():
        return stamp_safe({"ok": False, "status": "TESTNET_NOT_CONFIGURED",
                            "reason": "BINANCE_ENV=testnet + BINANCE_API_KEY + BINANCE_API_SECRET required",
                            "binance_order_execution_enabled": False,
                            "binance_live_trading_enabled": False})
    try:
        from tower.binance_floor import BinanceGateway
        gw = BinanceGateway()
        data = gw._signed_get("/api/v3/openOrders")
        return stamp_safe({"ok": True, "ts": _now(),
                            "label": "LIVE_READ_ONLY_TESTNET",
                            "open_orders": data,
                            "binance_order_execution_enabled": False,
                            "binance_live_trading_enabled": False})
    except Exception as e:
        return stamp_safe({"ok": False, "error": str(e)[:200],
                            "binance_order_execution_enabled": False})


def testnet_order_preview(payload):
    # Always preview — never auto-execute.
    payload = payload or {}
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "BINANCE_TESTNET_ORDER_PREVIEW",
        "blocked_for_placement": True,
        "reason": "Testnet order placement endpoint is gated. Preview only.",
        "preview": {
            "symbol": (payload.get("symbol") or "").upper(),
            "side":   (payload.get("side") or "").upper(),
            "units":  payload.get("units"),
            "mode":   "TESTNET_ONLY",
        },
        "binance_order_execution_enabled": False,
        "binance_live_trading_enabled": False,
        "live_trading_enabled": False,
    })


def place_testnet_order(payload):
    # Hard refuse — V1.5 does not place Binance orders, even testnet,
    # without a separate explicit unlock command from Ross.
    return stamp_safe({
        "ok": False, "ts": _now(),
        "blocked": True,
        "reason": "Binance testnet order placement requires a separate explicit unlock command (V1.5 ships preview-only).",
        "binance_order_execution_enabled": False,
        "binance_live_trading_enabled": False,
        "live_trading_enabled": False,
    })


def live_dashboard():
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "BINANCE_LIVE_DASHBOARD",
        "preflight": testnet_preflight(),
        "gauges":    gauges(),
        "open_orders": open_orders(),
        "policy": "PUBLIC MARKET DATA LIVE · TESTNET ORDER EXECUTION BLOCKED · REAL-MONEY OFF",
        "binance_order_execution_enabled": False,
        "binance_live_trading_enabled": False,
    })
