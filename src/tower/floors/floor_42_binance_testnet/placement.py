"""Binance testnet placement adapter.

This is the SOLE path a worker order takes to reach Binance testnet.
Mirrors the OANDA structure: certified-worker gate over a guarded
adapter that refuses to act without credentials and manual confirm.

Until credentials are set, every call raises BinanceTestnetNotConfigured.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error

from tower.cognitive_kernel import ROOT, REG, append_log, now, SAFETY
from tower.cognitive_kernel.worker_certification import worker_certification
from .state import GUARDS, FLAGS, creds_present


class BinanceTestnetNotConfigured(RuntimeError):
    """Raised when credentials are missing for any order operation."""


BASE_URL = GUARDS["base_url_testnet"]   # ALWAYS testnet
WORKER_LEDGER_PATH = ROOT / "data/logs/qsb_floor42_binance_trade_ledger.jsonl"
OWNERSHIP_PATH    = ROOT / "data/registries/qsb_floor42_binance_trade_ownership.json"


# ── HTTP helpers ─────────────────────────────────────────────────────

def _sign(query: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"),
                     hashlib.sha256).hexdigest()


class BinanceTestnetClient:
    def __init__(self):
        if not creds_present():
            raise BinanceTestnetNotConfigured(
                "QSB_BINANCE_TESTNET_API_KEY + QSB_BINANCE_TESTNET_API_SECRET "
                "required. Set them in /vaults/nvme0/qsb_tower_v1/.env.binance_testnet."
            )
        self.api_key = os.environ["QSB_BINANCE_TESTNET_API_KEY"]
        self.api_secret = os.environ["QSB_BINANCE_TESTNET_API_SECRET"]
        # Hard URL pin
        if BASE_URL != "https://testnet.binance.vision":
            raise RuntimeError("Blocked: only testnet.binance.vision allowed.")

    def _signed_get(self, path: str, params: Dict[str, Any]) -> Any:
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        q = urllib.parse.urlencode(params)
        sig = _sign(q, self.api_secret)
        url = f"{BASE_URL}{path}?{q}&signature={sig}"
        req = urllib.request.Request(url, headers={"X-MBX-APIKEY": self.api_key})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _signed_post(self, path: str, params: Dict[str, Any]) -> Any:
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        q = urllib.parse.urlencode(params)
        sig = _sign(q, self.api_secret)
        body = f"{q}&signature={sig}".encode("utf-8")
        url = f"{BASE_URL}{path}"
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"X-MBX-APIKEY": self.api_key,
                      "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _signed_delete(self, path: str, params: Dict[str, Any]) -> Any:
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        q = urllib.parse.urlencode(params)
        sig = _sign(q, self.api_secret)
        url = f"{BASE_URL}{path}?{q}&signature={sig}"
        req = urllib.request.Request(url, method="DELETE",
                                       headers={"X-MBX-APIKEY": self.api_key})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ── public read paths ─────────────────────────────────────────────
    def account(self) -> Dict[str, Any]:
        return self._signed_get("/api/v3/account", {})

    def open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if symbol: params["symbol"] = symbol
        return self._signed_get("/api/v3/openOrders", params)

    def ticker_price(self, symbol: str) -> Dict[str, Any]:
        # Unsigned + public
        url = f"{BASE_URL}/api/v3/ticker/price?symbol={symbol}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ── order ops ────────────────────────────────────────────────────
    def place_market_order(self, symbol: str, side: str,
                             quote_order_qty_usdt: float) -> Dict[str, Any]:
        if side not in ("BUY", "SELL"):
            raise RuntimeError(f"invalid side {side!r}")
        return self._signed_post("/api/v3/order", {
            "symbol": symbol, "side": side,
            "type": "MARKET",
            "quoteOrderQty": f"{quote_order_qty_usdt:.2f}",
        })

    def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        return self._signed_delete("/api/v3/order",
                                     {"symbol": symbol, "orderId": order_id})


# ── ownership map ────────────────────────────────────────────────────

def _load_ownership() -> Dict[str, str]:
    if not OWNERSHIP_PATH.exists():
        return {}
    try:
        return (json.loads(OWNERSHIP_PATH.read_text(encoding="utf-8"))
                .get("ownership") or {})
    except Exception:
        return {}


def _save_ownership(o: Dict[str, str]) -> None:
    OWNERSHIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    OWNERSHIP_PATH.write_text(json.dumps({
        "ok": True,
        "kind": "qsb_floor42_binance_trade_ownership",
        "generated_ts": now(),
        "ownership": o,
    }, indent=2), encoding="utf-8")


def _append_worker_ledger(row: Dict[str, Any]) -> None:
    WORKER_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with WORKER_LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# ── guardrails ───────────────────────────────────────────────────────

def _check_guards(symbol: str, side: str, quote_qty_usdt: float,
                    confirm: bool) -> List[str]:
    fails = []
    if symbol not in GUARDS["allowed_symbols"]:
        fails.append(f"symbol_not_whitelisted: {symbol}")
    if side.upper() not in ("BUY", "SELL"):
        fails.append("side_must_be_BUY_or_SELL")
    if quote_qty_usdt <= 0:
        fails.append("quote_qty_must_be_positive")
    if quote_qty_usdt > GUARDS["max_quantity_per_order_quote_usdt"]:
        fails.append(f"qty_over_cap: {quote_qty_usdt} > "
                     f"{GUARDS['max_quantity_per_order_quote_usdt']}")
    if not confirm:
        fails.append("manual_confirm_required")
    if FLAGS.get("kill_switch_on"):
        fails.append("kill_switch_on")
    return fails


# ── preflight ────────────────────────────────────────────────────────

def preflight() -> Dict[str, Any]:
    if not creds_present():
        return {"ok": False, "status": "not_configured",
                "reason": "credentials_missing",
                "policy": "Set QSB_BINANCE_TESTNET_API_KEY + _API_SECRET in env."}
    try:
        c = BinanceTestnetClient()
        acct = c.account()
        balances = [b for b in acct.get("balances") or []
                    if float(b.get("free") or 0) > 0
                    or float(b.get("locked") or 0) > 0]
        prices = []
        for s in GUARDS["allowed_symbols"]:
            try:
                p = c.ticker_price(s)
                prices.append({"symbol": s, "price": p.get("price")})
            except Exception as e:
                prices.append({"symbol": s, "error": str(e)[:80]})
        return {
            "ok": True,
            "label": "BINANCE_TESTNET_PREFLIGHT",
            "account_ready": True,
            "balances_nonzero": balances[:8],
            "live_prices": prices,
            "guards": dict(GUARDS),
            "safety_envelope": dict(SAFETY),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ── certified-worker placement ───────────────────────────────────────

def place_for_worker(worker_id: str, symbol: str, side: str,
                       quote_qty_usdt: float, entry_reason: str,
                       confirm_practice_order: bool) -> Dict[str, Any]:
    if not creds_present():
        return {"ok": False, "blocked": True,
                "blocked_by": "credentials_missing",
                "reason": ("set QSB_BINANCE_TESTNET_API_KEY + _API_SECRET "
                            "in .env.binance_testnet first")}
    symbol = symbol.upper(); side = side.upper()
    wc = worker_certification(); wc.load_from_snapshot()
    # Use symbol as the cert key for testnet
    if not wc.is_authorized(worker_id, symbol):
        e = wc.get_or_create(worker_id, symbol)
        return {"ok": False, "blocked": True,
                "blocked_by": "worker_certification_gate",
                "reason": f"worker {worker_id} not certified for {symbol} "
                           f"(status={e.status})"}
    fails = _check_guards(symbol, side, quote_qty_usdt, confirm_practice_order)
    if fails:
        append_log("binance_testnet.jsonl",
                   {"event": "place_blocked",
                    "worker_id": worker_id, "symbol": symbol,
                    "failures": fails})
        return {"ok": False, "blocked": True,
                "guard_failures": fails}
    try:
        c = BinanceTestnetClient()
        resp = c.place_market_order(symbol, side, quote_qty_usdt)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    order_id = str(resp.get("orderId") or "")
    fills = resp.get("fills") or []
    fill_price = float(fills[0]["price"]) if fills else None
    fill_qty = sum(float(f.get("qty") or 0) for f in fills)
    row = {
        "ts": now(),
        "event": "open_filled",
        "execution_mode": "binance_testnet_real",
        "worker_id": worker_id,
        "symbol": symbol, "side": side,
        "quote_qty_usdt": quote_qty_usdt,
        "entry_reason": entry_reason,
        "binance_order_id": order_id,
        "broker_order_id": order_id,
        "fill_price": fill_price,
        "fill_qty": fill_qty,
        "realized_pnl": 0.0,
        "safety_envelope": dict(SAFETY),
    }
    _append_worker_ledger(row)
    o = _load_ownership(); o[order_id] = worker_id; _save_ownership(o)
    append_log("binance_testnet.jsonl", {
        "event": "place_executed",
        "worker_id": worker_id, "symbol": symbol,
        "order_id": order_id, "fill_price": fill_price,
    })
    return {"ok": True, "worker_id": worker_id,
            "symbol": symbol, "side": side,
            "binance_order_id": order_id,
            "fill_price": fill_price, "fill_qty": fill_qty,
            "binance_response": resp,
            "safety_envelope": dict(SAFETY)}


def close_for_worker(worker_id: str, symbol: str,
                       binance_order_id: str,
                       close_reason: str) -> Dict[str, Any]:
    """Cancel an open order. For market-filled orders, 'close' means
    placing an opposing market order — that's a separate flow we don't
    implement until you choose a hedging policy."""
    o = _load_ownership()
    owner = o.get(str(binance_order_id))
    if owner is None:
        return {"ok": False, "blocked": True,
                "blocked_by": "ownership_unknown",
                "reason": f"no ownership for order {binance_order_id}"}
    if owner != worker_id:
        return {"ok": False, "blocked": True,
                "blocked_by": "ownership_mismatch",
                "reason": (f"worker {worker_id} tried to close order "
                            f"{binance_order_id} owned by {owner}")}
    try:
        c = BinanceTestnetClient()
        resp = c.cancel_order(symbol.upper(), binance_order_id)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    _append_worker_ledger({
        "ts": now(), "event": "cancel",
        "execution_mode": "binance_testnet_real",
        "worker_id": worker_id, "symbol": symbol.upper(),
        "binance_order_id": binance_order_id,
        "close_reason": close_reason,
        "binance_response": resp,
    })
    return {"ok": True, "binance_response": resp}
