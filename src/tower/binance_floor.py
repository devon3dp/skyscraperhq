#!/usr/bin/env python3
"""
QSB Tower V1.3 — Floor 42 Binance Trading Floor

Phase: BINANCE_FLOOR_42_TRADING_FLOOR_V1

Read-only / paper-only Binance floor.

Safety:
- Public market data only by default (no credentials required).
- Optional Binance read-only account check if BINANCE_API_KEY and
  BINANCE_API_SECRET are present in the environment.
- Order endpoints are blocked at the gateway layer even if creds are present
  and even if BINANCE_ORDER_EXECUTION_ENABLED=true is set.
- BINANCE_API_SECRET is never logged, never printed, never persisted to JSON,
  never returned in any dashboard payload.
"""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOG = ROOT / "data/logs/binance_floor.jsonl"

POLICY_PATH = REG / "binance_floor_policy.json"
STATUS_PATH = REG / "binance_floor_status.json"
SNAPSHOT_PATH = REG / "binance_market_snapshot_latest.json"

ENV_FILE = ROOT / ".env.binance"

LOCKED_FALSE = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
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


class BinanceOrderBlocked(RuntimeError):
    pass


class BinanceGateway:
    """
    Public market data + optional read-only account access.
    Order endpoints are unconditionally refused.
    """

    def __init__(self):
        load_local_env_file()
        self.policy = load_json(POLICY_PATH, {})

        env_name = (os.environ.get("BINANCE_ENV") or "testnet").strip().lower()
        if env_name not in ("testnet", "live"):
            env_name = "testnet"
        self.env_name = env_name

        if env_name == "live":
            self.base_url = self.policy.get("base_url_live") or "https://api.binance.com"
        else:
            # Prefer the explicit QSB_BINANCE_TESTNET_URL from the vault (lets
            # Ross point at e.g. testnet.binancefuture.com if the credentials
            # were issued there). Falls back to policy and then to spot testnet.
            self.base_url = (
                (os.environ.get("QSB_BINANCE_TESTNET_URL") or "").strip()
                or self.policy.get("base_url_testnet")
                or "https://testnet.binance.vision"
            )

        # Accept either the BINANCE_* convention OR the QSB_BINANCE_TESTNET_*
        # convention used in the Floor 28 vault. Vault values win when both set.
        self.api_key = (
            (os.environ.get("QSB_BINANCE_TESTNET_API_KEY") or "").strip()
            or (os.environ.get("BINANCE_API_KEY") or "").strip()
        )
        self._api_secret = (
            (os.environ.get("QSB_BINANCE_TESTNET_API_SECRET") or "").strip()
            or (os.environ.get("BINANCE_API_SECRET") or "").strip()
        )

        self.read_only = _truthy(os.environ.get("BINANCE_READ_ONLY", "true"))

        # Operator intent flag. Even if true, order endpoints stay refused in V1.
        self._order_intent_flag = _truthy(
            os.environ.get("BINANCE_ORDER_EXECUTION_ENABLED", "false")
        )

    # ------------------------------------------------------------------ creds

    def credentials_status(self):
        """
        Returns booleans only. Never includes the key or secret value.
        """
        return {
            "credentials_source": "environment_variables_only",
            "api_key_present": bool(self.api_key),
            "api_secret_present": bool(self._api_secret),
            "read_only_mode": self.read_only,
            "env_file_path": str(ENV_FILE),
            "env_file_exists": ENV_FILE.exists(),
        }

    # ------------------------------------------------------------------ http

    def _public_get(self, path, params=None, timeout=10):
        if not path.startswith("/api/v3/"):
            raise RuntimeError("Blocked non-/api/v3/ Binance path: {}".format(path))
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _signed_get(self, path, params=None, timeout=10):
        if not self.api_key or not self._api_secret:
            raise RuntimeError("Binance signed read requires BINANCE_API_KEY and BINANCE_API_SECRET")
        if not path.startswith("/api/v3/"):
            raise RuntimeError("Blocked non-/api/v3/ Binance path: {}".format(path))
        params = dict(params or {})
        params["timestamp"] = int(time.time() * 1000)
        params.setdefault("recvWindow", 5000)
        query = urllib.parse.urlencode(params, doseq=True)
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        url = self.base_url + path + "?" + query + "&signature=" + signature
        req = urllib.request.Request(url, method="GET")
        req.add_header("X-MBX-APIKEY", self.api_key)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ------------------------------------------------------------------ orders (blocked)

    def place_order(self, *args, **kwargs):
        raise BinanceOrderBlocked(
            "Blocked: Binance order endpoints are disabled in V1 "
            "(binance_order_execution_enabled=false)."
        )

    def cancel_order(self, *args, **kwargs):
        raise BinanceOrderBlocked(
            "Blocked: Binance order endpoints are disabled in V1."
        )

    def _signed_post_or_delete(self, *args, **kwargs):
        raise BinanceOrderBlocked(
            "Blocked: Binance signed write endpoints are disabled in V1."
        )

    # ------------------------------------------------------------------ public market data

    def ping(self):
        return self._public_get("/api/v3/ping")

    def server_time(self):
        return self._public_get("/api/v3/time")

    def exchange_info(self, symbols=None):
        params = {}
        if symbols:
            if isinstance(symbols, str):
                symbols = [s.strip() for s in symbols.split(",") if s.strip()]
            params["symbols"] = json.dumps(symbols)
        return self._public_get("/api/v3/exchangeInfo", params or None)

    def ticker_24h(self, symbols=None):
        params = {}
        if symbols:
            if isinstance(symbols, str):
                symbols = [s.strip() for s in symbols.split(",") if s.strip()]
            params["symbols"] = json.dumps(symbols)
        return self._public_get("/api/v3/ticker/24hr", params or None)

    def ticker_price(self, symbols=None):
        params = {}
        if symbols:
            if isinstance(symbols, str):
                symbols = [s.strip() for s in symbols.split(",") if s.strip()]
            params["symbols"] = json.dumps(symbols)
        return self._public_get("/api/v3/ticker/price", params or None)

    def order_book(self, symbol, limit=5):
        return self._public_get("/api/v3/depth", {"symbol": symbol, "limit": limit})

    def klines(self, symbol, interval="5m", limit=80):
        return self._public_get(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )

    # ------------------------------------------------------------------ account read

    def account_info(self):
        return self._signed_get("/api/v3/account")

    # ------------------------------------------------------------------ status / snapshot

    def market_data_ready(self):
        try:
            self.server_time()
            return True, None
        except Exception as exc:
            return False, str(exc)

    def account_read_ready(self):
        if not self.api_key or not self._api_secret:
            return False, "credentials_absent"
        try:
            info = self.account_info()
            return True, {
                "canTrade": info.get("canTrade"),
                "canDeposit": info.get("canDeposit"),
                "canWithdraw": info.get("canWithdraw"),
                "accountType": info.get("accountType"),
                "permissions": info.get("permissions"),
                "balance_asset_count": len(info.get("balances") or []),
            }
        except Exception as exc:
            return False, str(exc)

    def status(self):
        market_ok, market_err = self.market_data_ready()
        account_ok, account_detail = self.account_read_ready()

        status = {
            "status_ts": datetime.now(timezone.utc).isoformat(),
            "floor": "floor_42",
            "department": "Binance Trading Floor",
            "phase": "BINANCE_FLOOR_42_TRADING_FLOOR_V1",
            "environment": self.env_name,
            "base_url": self.base_url,
            "credentials": self.credentials_status(),
            "public_market_data_ready": market_ok,
            "public_market_data_error": market_err,
            "account_read_ready": account_ok,
            "account_read_detail": account_detail if account_ok else None,
            "account_read_error": account_detail if not account_ok else None,
            "default_symbols": self.policy.get("default_symbols") or [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"
            ],
            "order_intent_flag_observed": self._order_intent_flag,
            "order_endpoints_blocked": True,
            "order_endpoints_blocked_reason": (
                "Binance Trading Floor V1 refuses all order endpoints regardless of env flag."
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
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"
            ]
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.split(",") if s.strip()]

        snap = {
            "snapshot_ts": datetime.now(timezone.utc).isoformat(),
            "floor": "floor_42",
            "department": "Binance Trading Floor",
            "phase": "BINANCE_FLOOR_42_TRADING_FLOOR_V1",
            "environment": self.env_name,
            "base_url": self.base_url,
            "symbols": symbols,
            "tickers": [],
            "order_books": {},
            "account_summary": None,
            "credentials": self.credentials_status(),
            "errors": [],
            **LOCKED_FALSE,
            "paper_only": True,
            "not_financial_advice": True,
        }

        try:
            snap["tickers"] = self.ticker_24h(symbols)
        except Exception as exc:
            snap["errors"].append("ticker_24h: {}".format(exc))

        for sym in symbols:
            try:
                snap["order_books"][sym] = self.order_book(sym, limit=5)
            except Exception as exc:
                snap["errors"].append("depth {}: {}".format(sym, exc))

        ok, detail = self.account_read_ready()
        if ok:
            snap["account_summary"] = detail
        elif detail and detail != "credentials_absent":
            snap["errors"].append("account_info: {}".format(detail))

        write_json(SNAPSHOT_PATH, snap)
        # Logged record never contains the key or secret.
        append_log({
            "ts": snap["snapshot_ts"],
            "floor": "floor_42",
            "phase": snap["phase"],
            "environment": snap["environment"],
            "symbols": symbols,
            "ticker_count": len(snap["tickers"]) if isinstance(snap["tickers"], list) else 0,
            "errors": snap["errors"],
            "order_endpoints_blocked": True,
            **LOCKED_FALSE,
            "paper_only": True,
        })
        return snap


class BinanceTradingFloor:
    def __init__(self):
        self.gateway = BinanceGateway()

    def dashboard(self):
        status = self.gateway.status()
        return {
            "floor": "floor_42",
            "department": "Binance Trading Floor",
            "phase": "BINANCE_FLOOR_42_TRADING_FLOOR_V1",
            "status": "healthy" if status.get("public_market_data_ready") else "waiting_for_market_data",
            "mode": (
                "binance_testnet_paper_only"
                if status.get("environment") == "testnet"
                else "binance_live_read_only_paper_only"
            ),
            "environment": status.get("environment"),
            "credentials": status.get("credentials"),
            "public_market_data_ready": status.get("public_market_data_ready"),
            "account_read_ready": status.get("account_read_ready"),
            "default_symbols": status.get("default_symbols"),
            "order_endpoints_blocked": True,
            **LOCKED_FALSE,
            "updated_ts": datetime.now(timezone.utc).isoformat(),
        }

    def snapshot(self, symbols=None):
        return self.gateway.snapshot(symbols)


def dashboard():
    return BinanceTradingFloor().dashboard()


if __name__ == "__main__":
    print(json.dumps(dashboard(), indent=2))
