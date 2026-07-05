"""Trading telemetry — wires existing OANDA / Binance / Stocks gateways.

Returns LIVE READ-ONLY data when credentials + read endpoints exist.
Returns {ok:false, status:'not_configured'} otherwise. NEVER fakes account,
position, P&L, or trade data. NEVER places orders.

Account IDs are redacted to last-4 chars before being returned.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .safety_contract import LOCKED_FALSE, stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LOG_PATH = ROOT / "logs/tower_ops/trading_telemetry.jsonl"


def _now(): return datetime.now(timezone.utc).isoformat()


def _append_log(rec):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", _now()); rec.setdefault("execution_allowed", False)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _redact_id(s):
    if not s: return None
    s = str(s)
    if len(s) <= 4: return "****" + s[-2:]
    return "****" + s[-4:]


def _not_configured(reason):
    return stamp_safe({
        "ok": False,
        "status": "not_configured",
        "reason": reason,
        "execution_allowed": False,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
    })


def _load_oanda_env():
    """Mirror the OANDA gateway's env-file lookup."""
    for env_file in (ROOT / ".env.oanda_practice", ROOT / ".env.oanda"):
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"): continue
                if line.startswith("export "): line = line[len("export "):]
                k, _, v = line.partition("=")
                k = k.strip(); v = v.strip().strip("'").strip('"')
                if k: os.environ.setdefault(k, v)


def _oanda_credentials_present():
    """Real OANDA env uses OANDA_API_TOKEN (not _API_KEY) + OANDA_ACCOUNT_ID."""
    return bool(os.environ.get("OANDA_API_TOKEN", "").strip() and
                 os.environ.get("OANDA_ACCOUNT_ID", "").strip())


# ── OANDA telemetry (LIVE READ-ONLY when configured) ────────────────
def oanda_account():
    _load_oanda_env()
    if not _oanda_credentials_present():
        return _not_configured("OANDA_API_TOKEN + OANDA_ACCOUNT_ID required (env vars or .env.oanda_practice)")
    try:
        from tower.oanda_gateway import OANDAGateway
        gw = OANDAGateway()
        info = gw.account_summary()
        acct = (info or {}).get("account") or info or {}
        _append_log({"event": "oanda_account_read"})
        return stamp_safe({
            "ok": True, "status": "LIVE_READ_ONLY", "label": "LIVE READ-ONLY",
            "ts": _now(),
            "environment": (info or {}).get("environment") or os.environ.get("OANDA_ENV", "practice"),
            "account_id_redacted": _redact_id(acct.get("id")),
            "balance":            acct.get("balance"),
            "NAV":                acct.get("NAV"),
            "margin_used":        acct.get("marginUsed"),
            "margin_available":   acct.get("marginAvailable"),
            "unrealized_pl":      acct.get("unrealizedPL"),
            "realized_pl_today":  acct.get("pl"),
            "open_position_count":acct.get("openPositionCount"),
            "open_trade_count":   acct.get("openTradeCount"),
            "currency":           acct.get("currency"),
            "live_trading_enabled":   False,
            "order_execution_enabled":False,
        })
    except Exception as exc:
        return _not_configured("oanda_gateway error: " + str(exc)[:160])


def oanda_positions():
    _load_oanda_env()
    if not _oanda_credentials_present():
        return _not_configured("OANDA_API_TOKEN + OANDA_ACCOUNT_ID required (env vars or .env.oanda_practice)")
    try:
        from tower.oanda_gateway import OANDAGateway
        gw = OANDAGateway()
        data = gw._get(f"/v3/accounts/{gw.account_id}/openPositions")
        positions = (data or {}).get("positions") or []
        _append_log({"event": "oanda_positions_read", "count": len(positions)})
        return stamp_safe({"ok": True, "status": "LIVE_READ_ONLY", "label": "LIVE READ-ONLY",
                            "ts": _now(),
                            "open_positions": positions,
                            "open_position_count": len(positions),
                            "order_execution_enabled": False})
    except Exception as exc:
        return _not_configured("oanda positions error: " + str(exc)[:160])


def oanda_trades():
    _load_oanda_env()
    if not _oanda_credentials_present():
        return _not_configured("OANDA_API_TOKEN + OANDA_ACCOUNT_ID required (env vars or .env.oanda_practice)")
    try:
        from tower.oanda_gateway import OANDAGateway
        gw = OANDAGateway()
        data = gw._get(f"/v3/accounts/{gw.account_id}/trades")
        trades = (data or {}).get("trades") or []
        _append_log({"event": "oanda_trades_read", "count": len(trades)})
        return stamp_safe({"ok": True, "status": "LIVE_READ_ONLY", "label": "LIVE READ-ONLY",
                            "ts": _now(),
                            "open_trades": trades, "open_trade_count": len(trades),
                            "order_execution_enabled": False})
    except Exception as exc:
        return _not_configured("oanda trades error: " + str(exc)[:160])


def oanda_pnl():
    """Derived from account summary — unrealized + realized."""
    acct = oanda_account()
    if not acct.get("ok"): return acct
    return stamp_safe({"ok": True, "status": "LIVE_READ_ONLY", "label": "LIVE READ-ONLY",
                        "ts": _now(),
                        "unrealized_pl":     acct.get("unrealized_pl"),
                        "realized_pl_today": acct.get("realized_pl_today"),
                        "currency":          acct.get("currency"),
                        "NAV":               acct.get("NAV"),
                        "balance":           acct.get("balance"),
                        "order_execution_enabled": False})


# ── Binance telemetry (LIVE READ-ONLY when configured) ──────────────
def binance_account():
    if not (os.environ.get("BINANCE_API_KEY") and os.environ.get("BINANCE_API_SECRET")):
        return _not_configured("BINANCE_API_KEY + BINANCE_API_SECRET required")
    try:
        from tower.binance_floor import BinanceGateway
        gw = BinanceGateway()
        info = gw.account_info()
        _append_log({"event": "binance_account_read"})
        balances = [b for b in (info or {}).get("balances", []) if float(b.get("free", 0)) > 0 or float(b.get("locked", 0)) > 0]
        return stamp_safe({"ok": True, "status": "LIVE_READ_ONLY", "label": "LIVE READ-ONLY",
                            "ts": _now(),
                            "environment": gw.env_name,
                            "account_type": info.get("accountType"),
                            "can_trade_flag_reported_by_api": info.get("canTrade"),
                            "balance_count": len(balances),
                            "balances_top10": balances[:10],
                            "binance_order_execution_enabled": False,
                            "binance_live_trading_enabled": False})
    except Exception as exc:
        return _not_configured("binance gateway error: " + str(exc)[:160])


def binance_positions():
    # Binance spot has balances, not positions. Treat balances as the position view.
    return binance_account()


def binance_orders():
    if not (os.environ.get("BINANCE_API_KEY") and os.environ.get("BINANCE_API_SECRET")):
        return _not_configured("BINANCE_API_KEY + BINANCE_API_SECRET required")
    # Reading open orders requires signed GET /api/v3/openOrders; the existing
    # gateway only exposes account_info. Return not_configured for safety so
    # we never display a misleading order list.
    return _not_configured("open-order read endpoint not wired in V1 gateway — to enable, add gateway helper")


def binance_pnl():
    # Spot account does not have a built-in P&L endpoint. Return not_configured.
    return _not_configured("Binance spot has no native P&L endpoint")


# ── Stocks telemetry ────────────────────────────────────────────────
def stocks_account():
    if not (os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_API_SECRET")):
        return _not_configured("ALPACA_API_KEY + ALPACA_API_SECRET required")
    try:
        from tower.stock_exchange_floor import AlpacaProvider, _load_policy_safe  # noqa
    except Exception:
        # Fall back to a direct AlpacaProvider construct
        from tower.stock_exchange_floor import AlpacaProvider
    try:
        from tower.stock_exchange_floor import AlpacaProvider
        from pathlib import Path as _P
        policy = {}
        ppath = ROOT / "data/registries/stock_floor_policy.json"
        if ppath.exists():
            try: policy = json.loads(ppath.read_text(encoding="utf-8"))
            except Exception: pass
        provider = AlpacaProvider(policy)
        ok, detail = provider.account_read_ready()
        _append_log({"event": "stocks_account_read", "ok": ok})
        if not ok:
            return _not_configured("alpaca account read not ready: " + str(detail)[:120])
        return stamp_safe({"ok": True, "status": "LIVE_READ_ONLY", "label": "LIVE READ-ONLY",
                            "ts": _now(),
                            "environment": provider.env_name,
                            "account_read": detail,
                            "stock_order_execution_enabled": False,
                            "stock_live_trading_enabled": False})
    except Exception as exc:
        return _not_configured("alpaca provider error: " + str(exc)[:160])


def stocks_positions():
    # The Floor 43 stock gateway in V1 has no positions endpoint wired.
    return _not_configured("Stock positions endpoint not wired in V1 gateway — to enable, add /v2/positions helper")


def stocks_pnl():
    return _not_configured("Stock P&L endpoint not wired in V1 gateway")
