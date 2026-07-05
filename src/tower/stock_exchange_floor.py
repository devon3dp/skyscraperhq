#!/usr/bin/env python3
"""
QSB Tower V1.3 — Floor 43 Stock Exchange Trading Floor

Phase: FLOOR_43_CONNECTED_STOCK_EXCHANGE_FLOOR_V1

Read-only / paper-only US equities floor with provider abstraction.

Default provider: Alpaca (https://alpaca.markets). Selected via
ALPACA_API_KEY / ALPACA_API_SECRET. Stub provider returns
last-known/static safe data if credentials are absent.

Safety contract (enforced even if every environment variable says yes):

- Order endpoints are unconditionally refused at the gateway layer.
- ALPACA_API_SECRET is never logged, printed, persisted to JSON, or
  returned in any dashboard payload.
- Only Alpaca read-only paths are accepted (account, positions, assets,
  bars, quotes, snapshots, clock). All other paths are rejected.
- The dashboard payload only ever reports boolean credential presence.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import urllib.parse
import urllib.request
import urllib.error


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOG = ROOT / "data/logs/stock_floor.jsonl"

POLICY_PATH   = REG / "stock_floor_policy.json"
STATUS_PATH   = REG / "stock_floor_status.json"
SNAPSHOT_PATH = REG / "stock_market_snapshot_latest.json"

ENV_FILE = ROOT / ".env.alpaca"

LOCKED_FALSE = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "stock_order_execution_enabled": False,
    "stock_live_trading_enabled": False,
    # Tier B unlock (Ross, 2026-06-10): paper stock placement permitted so
    # workers can create paper orders against the broker sandbox. All real
    # / live / money flags above stay False.
    "stock_paper_order_execution_enabled": True,
    "binance_order_execution_enabled": False,
    "binance_live_trading_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "openclaw_real_tool_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False,
}

# Read-only Alpaca paths permitted by the gateway. Anything not in this
# allowlist is rejected, including all /v2/orders, /v2/positions/<sym>
# (DELETE), /v2/account/configurations, etc.
_ALPACA_READ_ALLOWLIST = (
    "/v2/account",
    "/v2/assets",
    "/v2/positions",
    "/v2/clock",
    "/v2/calendar",
    "/v2/stocks/quotes/latest",
    "/v2/stocks/bars/latest",
    "/v2/stocks/snapshots",
    "/v2/stocks/bars",
    "/v2/stocks/quotes",
    "/v2/stocks/trades/latest",
)


def load_local_env_file():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        k, _, v = line.partition("=")
        k = k.strip()
        if not k:
            continue
        v = v.strip().strip("'").strip('"')
        os.environ.setdefault(k, v)


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_log(record):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


class StockOrderBlocked(RuntimeError):
    pass


class StockProvider:
    """Abstract base. Subclasses implement read-only data fetches."""

    provider_name = "abstract"
    requires_credentials = False

    def credentials_status(self):
        return {
            "credentials_source": "environment_variables_only",
            "api_key_present": False,
            "api_secret_present": False,
            "read_only_mode": True,
            "env_file_path": str(ENV_FILE),
            "env_file_exists": ENV_FILE.exists(),
        }

    def market_data_ready(self):
        return False, "abstract_provider"

    def account_read_ready(self):
        return False, "abstract_provider"

    def market_status(self):
        return "unknown", None

    def snapshot_symbols(self, symbols):
        return {}, ["abstract_provider"]

    # Hard-blocked write methods on every provider, no matter what.
    def place_order(self, *args, **kwargs):
        raise StockOrderBlocked(
            "Blocked: stock order endpoints are disabled in V1 "
            "(stock_order_execution_enabled=false). No real, paper, or practice orders may be placed.")

    cancel_order = place_order


class AlpacaProvider(StockProvider):
    """Read-only Alpaca gateway. Order endpoints are unconditionally refused."""

    provider_name = "alpaca"
    requires_credentials = False  # public quote/bar data is gated behind creds, but the floor can still operate without them

    def __init__(self, policy):
        self.policy = policy or {}
        base_urls = (self.policy.get("alpaca_base_urls") or {})
        self.env_name = (os.environ.get("ALPACA_ENV") or self.policy.get("alpaca_env_default") or "paper").strip().lower()
        if self.env_name not in ("paper", "live", "live_data_readonly"):
            self.env_name = "paper"
        # Trading-host base URL (account, positions). NOT used for orders here.
        self.trading_base = base_urls.get("live") if self.env_name in ("live", "live_data_readonly") else base_urls.get("paper")
        if not self.trading_base:
            self.trading_base = "https://paper-api.alpaca.markets" if self.env_name == "paper" else "https://api.alpaca.markets"
        self.data_base = base_urls.get("data") or "https://data.alpaca.markets"

        self.api_key     = (os.environ.get("ALPACA_API_KEY") or "").strip()
        self._api_secret = (os.environ.get("ALPACA_API_SECRET") or "").strip()
        self.read_only   = _truthy(os.environ.get("ALPACA_READ_ONLY", "true"))
        self._order_intent_flag = _truthy(os.environ.get("ALPACA_ORDER_EXECUTION_ENABLED", "false"))

    def credentials_status(self):
        return {
            "credentials_source": "environment_variables_only",
            "api_key_present": bool(self.api_key),
            "api_secret_present": bool(self._api_secret),
            "read_only_mode": self.read_only,
            "env_file_path": str(ENV_FILE),
            "env_file_exists": ENV_FILE.exists(),
        }

    # ── http helpers — read-only only ──────────────────────────────────
    def _check_path_allowed(self, path):
        for prefix in _ALPACA_READ_ALLOWLIST:
            if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?"):
                return True
        return False

    def _read_get(self, base, path, params=None, timeout=10):
        if not self._check_path_allowed(path):
            raise RuntimeError(
                "Blocked non-read-only Alpaca path: {} (only read-only paths are permitted).".format(path)
            )
        url = base + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        req = urllib.request.Request(url, method="GET")
        if self.api_key:
            req.add_header("APCA-API-KEY-ID", self.api_key)
        if self._api_secret:
            req.add_header("APCA-API-SECRET-KEY", self._api_secret)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ── public-ish data ────────────────────────────────────────────────
    def market_data_ready(self):
        try:
            # Clock is the cheapest gate; available with valid creds.
            if not self.api_key or not self._api_secret:
                return False, "credentials_absent_for_alpaca_data"
            data = self._read_get(self.trading_base, "/v2/clock", timeout=8)
            return bool(data.get("timestamp")), None
        except Exception as exc:
            return False, str(exc)[:200]

    def market_status(self):
        try:
            if not self.api_key or not self._api_secret:
                return "credentials_absent", None
            clock = self._read_get(self.trading_base, "/v2/clock", timeout=8)
            return ("open" if clock.get("is_open") else "closed"), {
                "next_open":  clock.get("next_open"),
                "next_close": clock.get("next_close"),
                "timestamp":  clock.get("timestamp"),
            }
        except Exception as exc:
            return "error", {"detail": str(exc)[:200]}

    def account_read_ready(self):
        if not self.api_key or not self._api_secret:
            return False, "credentials_absent"
        try:
            info = self._read_get(self.trading_base, "/v2/account", timeout=8)
            return True, {
                "account_id_present": bool(info.get("id")),
                "status": info.get("status"),
                "trading_blocked": info.get("trading_blocked"),
                "account_blocked": info.get("account_blocked"),
                "pattern_day_trader": info.get("pattern_day_trader"),
                "currency": info.get("currency"),
                "shorting_enabled": info.get("shorting_enabled"),
                "buying_power_present": "buying_power" in info,
            }
        except Exception as exc:
            return False, str(exc)[:200]

    def snapshot_symbols(self, symbols):
        errors = []
        quotes = {}
        bars = {}
        if not symbols:
            return {"quotes": quotes, "bars": bars}, errors
        if not self.api_key or not self._api_secret:
            return {"quotes": quotes, "bars": bars}, ["credentials_absent_for_alpaca_data"]
        sym_csv = ",".join(symbols)
        try:
            data = self._read_get(self.data_base, "/v2/stocks/quotes/latest", {"symbols": sym_csv}, timeout=10)
            quotes = data.get("quotes") or {}
        except Exception as exc:
            errors.append("quotes_latest: {}".format(str(exc)[:200]))
        try:
            data = self._read_get(self.data_base, "/v2/stocks/bars/latest", {"symbols": sym_csv}, timeout=10)
            bars = data.get("bars") or {}
        except Exception as exc:
            errors.append("bars_latest: {}".format(str(exc)[:200]))
        return {"quotes": quotes, "bars": bars}, errors

    def recent_bars(self, symbol, timeframe="5Min", limit=40):
        if not self.api_key or not self._api_secret:
            raise RuntimeError("credentials_absent_for_alpaca_data")
        data = self._read_get(
            self.data_base, "/v2/stocks/bars",
            {"symbols": symbol, "timeframe": timeframe, "limit": limit},
            timeout=12,
        )
        bars_map = data.get("bars") or {}
        return bars_map.get(symbol) or []

    # ── PAPER ORDER PATH (Ross unlock 2026-06-10) ─────────────────────
    # Live (non-paper) order placement remains UNCONDITIONALLY blocked by
    # the base StockProvider.place_order — we only override here for paper
    # and we re-check env_name + intent flag at call time. CLAUDE.md still
    # forbids real-money stock execution; this method refuses if env_name
    # is anything other than "paper".
    def place_order(self, *, symbol, qty, side, type="market",
                    time_in_force="day", limit_price=None,
                    extended_hours=False, client_order_id=None,
                    reason="unspecified"):
        if self.env_name != "paper":
            raise StockOrderBlocked(
                "Blocked: Alpaca live/production order placement is unconditionally "
                "disabled. Paper env only. (env={})".format(self.env_name))
        if not self._order_intent_flag:
            raise StockOrderBlocked(
                "Blocked: ALPACA_ORDER_EXECUTION_ENABLED is false. Paper order intent flag must be true.")
        if not self.api_key or not self._api_secret:
            raise StockOrderBlocked(
                "Blocked: Alpaca credentials absent.")

        side = (side or "").lower()
        if side not in ("buy", "sell"):
            raise StockOrderBlocked("side must be buy or sell")
        type_ = (type or "market").lower()
        if type_ not in ("market", "limit"):
            raise StockOrderBlocked("type must be market or limit")

        body = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side,
            "type": type_,
            "time_in_force": time_in_force,
            "extended_hours": bool(extended_hours),
        }
        if type_ == "limit":
            if limit_price is None:
                raise StockOrderBlocked("limit order requires limit_price")
            body["limit_price"] = str(limit_price)
        if client_order_id:
            body["client_order_id"] = client_order_id

        # POST to paper-api.alpaca.markets /v2/orders
        url = self.trading_base + "/v2/orders"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("APCA-API-KEY-ID", self.api_key)
        req.add_header("APCA-API-SECRET-KEY", self._api_secret)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:300]
            raise StockOrderBlocked(
                "Alpaca paper order rejected: HTTP {} — {}".format(e.code, err_body))

        # Append to a paper ledger so F44 can read it
        ledger = ROOT / "data/registries/qsb_floor43_alpaca_paper_orders.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        _ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        try:
            with ledger.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": _ts, "reason": reason, "request": body,
                    "alpaca_id": result.get("id"),
                    "alpaca_status": result.get("status"),
                    "alpaca_qty": result.get("qty"),
                    "alpaca_filled_qty": result.get("filled_qty"),
                    "alpaca_filled_avg_price": result.get("filled_avg_price"),
                    "advisory_only": True,
                    "venue": "alpaca_paper",
                }) + "\n")
        except Exception:
            pass
        return {"ok": True, "env": "paper", "reason": reason,
                "alpaca_response": result}


class StubProvider(StockProvider):
    """No-network safe fallback used when no creds are configured."""

    provider_name = "stub"

    def __init__(self, policy):
        self.policy = policy or {}
        self.env_name = "paper"
        self.trading_base = ""
        self.data_base = ""
        self.api_key = ""
        self._api_secret = ""
        self.read_only = True
        self._order_intent_flag = False

    def market_data_ready(self):
        return False, "stub_provider_no_network"

    def market_status(self):
        return "unknown", None

    def account_read_ready(self):
        return False, "stub_provider_no_credentials"

    def snapshot_symbols(self, symbols):
        return {"quotes": {}, "bars": {}}, ["stub_provider_no_data"]


class StockGateway:
    """Provider-agnostic façade. Order endpoints unconditionally blocked here."""

    def __init__(self, provider_override=None):
        load_local_env_file()
        self.policy = load_json(POLICY_PATH, {})
        provider_name = (provider_override
                         or os.environ.get("STOCK_PROVIDER")
                         or self.policy.get("provider_default")
                         or "alpaca").strip().lower()
        if provider_name == "alpaca":
            self.provider = AlpacaProvider(self.policy)
        else:
            self.provider = StubProvider(self.policy)
        self.provider_name = self.provider.provider_name

    # creds
    def credentials_status(self):
        return self.provider.credentials_status()

    # blocked orders
    def place_order(self, *args, **kwargs):
        raise StockOrderBlocked(
            "Blocked: stock order endpoints are disabled in V1 "
            "(stock_order_execution_enabled=false). No real, paper, or practice orders.")

    cancel_order = place_order

    # status / snapshots
    def status(self):
        market_ok, market_err = self.provider.market_data_ready()
        account_ok, account_detail = self.provider.account_read_ready()
        market_status, market_status_detail = self.provider.market_status()

        env_name = getattr(self.provider, "env_name", "paper")
        creds = self.provider.credentials_status()
        order_intent_flag = bool(getattr(self.provider, "_order_intent_flag", False))

        status = {
            "status_ts": datetime.now(timezone.utc).isoformat(),
            "floor": "floor_43",
            "department": "Stock Exchange Trading Floor",
            "phase": "FLOOR_43_CONNECTED_STOCK_EXCHANGE_FLOOR_V1",
            "provider": self.provider_name,
            "environment": env_name,
            "credentials": creds,
            "public_market_data_ready": market_ok,
            "public_market_data_error": market_err,
            "account_read_ready": account_ok,
            "account_read_detail": account_detail if account_ok else None,
            "account_read_error": account_detail if not account_ok else None,
            "market_status": market_status,
            "market_status_detail": market_status_detail,
            "default_symbols": self.policy.get("default_symbols") or
                ["AAPL", "MSFT", "NVDA", "TSLA", "SPY", "QQQ"],
            "order_intent_flag_observed": order_intent_flag,
            "order_endpoints_blocked": True,
            "order_endpoints_blocked_reason": (
                "Stock Exchange Trading Floor V1 refuses all order endpoints "
                "regardless of provider env flags."
            ),
            **LOCKED_FALSE,
            "paper_only": True,
            "not_financial_advice": True,
        }

        write_json(STATUS_PATH, status)
        return status

    def snapshot(self, symbols=None):
        if not symbols:
            symbols = self.policy.get("default_symbols") or [
                "AAPL", "MSFT", "NVDA", "TSLA", "SPY", "QQQ"
            ]
        if isinstance(symbols, str):
            symbols = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        else:
            symbols = [s.strip().upper() for s in symbols if s and s.strip()]

        env_name = getattr(self.provider, "env_name", "paper")
        creds = self.provider.credentials_status()
        market_status, market_status_detail = self.provider.market_status()

        data, errors = self.provider.snapshot_symbols(symbols)
        quotes = (data or {}).get("quotes") or {}
        bars   = (data or {}).get("bars") or {}

        quality = "fresh" if quotes else ("partial" if bars else "no_data")
        stale = not bool(quotes or bars)

        snap = {
            "snapshot_ts": datetime.now(timezone.utc).isoformat(),
            "floor": "floor_43",
            "department": "Stock Exchange Trading Floor",
            "phase": "FLOOR_43_CONNECTED_STOCK_EXCHANGE_FLOOR_V1",
            "provider": self.provider_name,
            "environment": env_name,
            "symbols": symbols,
            "quotes": quotes,
            "bars": bars,
            "credentials": creds,
            "market_status": market_status,
            "market_status_detail": market_status_detail,
            "data_quality": quality,
            "stale": stale,
            "errors": errors,
            **LOCKED_FALSE,
            "execution_allowed": False,
            "order_created": False,
            "paper_order_created": False,
            "live_order_created": False,
            "paper_only": True,
            "not_financial_advice": True,
        }

        write_json(SNAPSHOT_PATH, snap)
        # Log record has no secrets.
        append_log({
            "ts": snap["snapshot_ts"],
            "floor": "floor_43",
            "phase": snap["phase"],
            "provider": snap["provider"],
            "environment": snap["environment"],
            "symbols": symbols,
            "quote_count": len(quotes),
            "bar_count":   len(bars),
            "data_quality": quality,
            "errors": errors,
            "order_endpoints_blocked": True,
            **LOCKED_FALSE,
            "paper_only": True,
        })
        return snap


class StockExchangeTradingFloor:
    def __init__(self, provider_override=None):
        self.gateway = StockGateway(provider_override=provider_override)

    def dashboard(self):
        status = self.gateway.status()
        return {
            "floor": "floor_43",
            "department": "Stock Exchange Trading Floor",
            "phase": "FLOOR_43_CONNECTED_STOCK_EXCHANGE_FLOOR_V1",
            "status": "healthy" if status.get("public_market_data_ready") else "waiting_for_market_data",
            "mode": (
                "stock_paper_only_read"
                if status.get("provider") == "alpaca"
                else "stock_stub_no_data"
            ),
            "provider": status.get("provider"),
            "environment": status.get("environment"),
            "credentials": status.get("credentials"),
            "public_market_data_ready": status.get("public_market_data_ready"),
            "account_read_ready": status.get("account_read_ready"),
            "market_status": status.get("market_status"),
            "default_symbols": status.get("default_symbols"),
            "order_endpoints_blocked": True,
            **LOCKED_FALSE,
            "updated_ts": datetime.now(timezone.utc).isoformat(),
        }

    def snapshot(self, symbols=None):
        return self.gateway.snapshot(symbols)


def dashboard():
    return StockExchangeTradingFloor().dashboard()


if __name__ == "__main__":
    print(json.dumps(dashboard(), indent=2))
