"""qsb_broker_place.py — gate-checked broker order placement.

Per Ross Knechtel 2026-06-22T16:25Z signed authorization for paper/practice/testnet
ONLY across OANDA practice + Alpaca paper + Binance testnet. Zero real-money exposure.

ALL placements pass through this module — gates can refuse + audit trail logs every call.

Team co-write 2026-06-22:
  Wren-fast: added HTTP 2xx response check (her addition)
  Hermes-8b: critical audit fields (venue, worker, qty) + cross-venue rate-limit
  Claude:    integrator — gate file load, URL-contains check, whitelist enforcement,
             per-venue + per-worker rate window, atomic gate refuse-default.

API:
  from qsb_broker_place import place_order
  result = place_order(venue, instrument, side, qty, worker_id)
  # result: {"ok": bool, "broker_order_id": str|None, "reason": str, "response": dict|None}
"""
from __future__ import annotations
import hmac
import hashlib
import json
import os
import time
import urllib.request
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
GATE_FILE = ROOT / "data/registries/qsb_broker_placement_gate.json"
AUDIT_FILE = ROOT / "data/registries/qsb_broker_place_audit.jsonl"
VAULT_DIR = ROOT / "floors/floor_28_security_department/vault"

# Per Ross 2026-06-24: fleet-wide £5000 net pot. BUY reserves, SELL releases.
try:
    from qsb_portfolio_pot import try_reserve as _pot_reserve, release as _pot_release
    _POT_ENABLED = True
except Exception:
    _POT_ENABLED = False

# Daily P&L drawdown stop (Ross 2026-06-24 "make it all happen", DeepSeek -£75 cap)
try:
    from qsb_session_pnl_stop import session_pnl_check as _pnl_check
    _PNL_STOP_ENABLED = True
except Exception:
    _PNL_STOP_ENABLED = False

# Track tick prices per (venue, instrument) so we can value notional on BUY.
# Filled by qsb_broker_place when the trader calls place_order — we infer price
# from the trader's recent OPEN log, but the cleanest hook is for the trader to
# pass entry_px. For now, broker_place imports nothing from the bus; we accept
# qty + an optional ref_price arg (added below).


# Per-venue + per-worker rate-window state (in-process; reset on restart).
_recent_orders: dict[str, deque] = defaultdict(deque)
_recent_orders_per_worker: dict[str, deque] = defaultdict(deque)


def _load_gate() -> dict:
    try:
        return json.loads(GATE_FILE.read_text())
    except Exception:
        return {"global_kill_switch": True, "venues": {}}


def _load_vault_env(filename: str) -> dict:
    p = VAULT_DIR / filename
    env = {}
    if p.exists():
        for ln in p.read_text().splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln:
                continue
            # Handle "export VAR=value" form too
            if ln.startswith("export "):
                ln = ln[len("export "):]
            k, v = ln.split("=", 1)
            env[k.strip()] = v.strip().strip("\"'")
    return env


def _audit(row: dict) -> None:
    row.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_FILE, "a") as fh:
        fh.write(json.dumps(row) + "\n")


def _rate_window_ok(venue: str, worker_id: str, gate_venue: dict) -> tuple[bool, str]:
    """Cleans windows + enforces per-venue and per-worker rate limits."""
    now = time.time()
    cutoff = now - 3600
    # per-venue
    dq_v = _recent_orders[venue]
    while dq_v and dq_v[0] < cutoff:
        dq_v.popleft()
    max_v = gate_venue.get("max_orders_per_hour", 10)
    if len(dq_v) >= max_v:
        return False, f"venue_rate_limit ({len(dq_v)}/{max_v}/hr)"
    # per-worker cross-venue (Hermes's addition)
    dq_w = _recent_orders_per_worker[worker_id]
    while dq_w and dq_w[0] < cutoff:
        dq_w.popleft()
    if len(dq_w) >= 600:   # 2026-06-24 raised 60→600 for fast trading per Ross
        return False, f"worker_rate_limit_cross_venue ({len(dq_w)}/600/hr)"
    return True, "ok"


def _record_order(venue: str, worker_id: str) -> None:
    now = time.time()
    _recent_orders[venue].append(now)
    _recent_orders_per_worker[worker_id].append(now)


def place_order(venue: str, instrument: str, side: str, qty: float,
                  worker_id: str = "anon", ref_price: float = 0.0,
                  open_order_id: str = "",
                  stop_distance: float = 0.0,
                  take_distance: float = 0.0) -> dict:
    """Gate-checked place. Returns dict with ok + reason.

    ref_price: tick price at the time of order. Used for pot reserve.
    open_order_id: on SELL close, pass original BUY id for pot release.
    stop_distance: 2026-06-24 broker-side stop. Price-units distance from fill
                   for OANDA stopLossOnFill. 0 = no broker stop, use event-driven.
    take_distance: same for OANDA takeProfitOnFill.
    """
    gate = _load_gate()
    # 1. global kill switch
    if gate.get("global_kill_switch"):
        result = {"ok": False, "reason": "global_kill_switch_on",
                   "broker_order_id": None, "response": None}
        _audit({"venue": venue, "worker_id": worker_id, "instrument": instrument,
                 "side": side, "qty": qty, **result})
        return result
    # 2. venue gate
    gv = (gate.get("venues") or {}).get(venue)
    if not gv:
        result = {"ok": False, "reason": f"unknown_venue:{venue}",
                   "broker_order_id": None, "response": None}
        _audit({"venue": venue, "worker_id": worker_id, "instrument": instrument,
                 "side": side, "qty": qty, **result})
        return result
    if not gv.get("enabled"):
        result = {"ok": False, "reason": f"venue_disabled:{venue}",
                   "broker_order_id": None, "response": None}
        _audit({"venue": venue, "worker_id": worker_id, "instrument": instrument,
                 "side": side, "qty": qty, **result})
        return result
    # 3. whitelist
    if instrument not in (gv.get("whitelist_instruments") or []):
        result = {"ok": False, "reason": f"instrument_not_whitelisted:{instrument}",
                   "broker_order_id": None, "response": None}
        _audit({"venue": venue, "worker_id": worker_id, "instrument": instrument,
                 "side": side, "qty": qty, **result})
        return result
    # 4. qty cap — 2026-06-25 CLAMP instead of refuse (was blocking 30%+ of opens
    # because Kelly-scaling pushed sizing over the per-venue cap. Better to ship
    # at the cap than to refuse outright.).
    qty_cap = gv.get("max_qty_per_order") or gv.get("max_units_per_order") or 0
    if qty_cap and qty > qty_cap:
        print(f"[broker_place] qty CLAMP {qty:.4f} → {qty_cap:.4f} "
               f"({worker_id} {instrument})", flush=True)
        qty = qty_cap
    # 5. rate windows
    ok_rate, rate_reason = _rate_window_ok(venue, worker_id, gv)
    if not ok_rate:
        result = {"ok": False, "reason": rate_reason,
                   "broker_order_id": None, "response": None}
        _audit({"venue": venue, "worker_id": worker_id, "instrument": instrument,
                 "side": side, "qty": qty, **result})
        return result
    # 5.4 Daily P&L drawdown stop — refuse new BUYs when session is tripped.
    if _PNL_STOP_ENABLED and side.upper() == "BUY":
        ok_pnl, pnl_reason = _pnl_check()
        if not ok_pnl:
            result = {"ok": False, "reason": pnl_reason,
                       "broker_order_id": None, "response": None}
            _audit({"venue": venue, "worker_id": worker_id, "instrument": instrument,
                     "side": side, "qty": qty, **result})
            return result
    # 5.5 £5000 net pot reserve — only on BUY (opens), with a ref_price.
    # SELL releases regardless of pot state (closes always freed).
    notional_gbp_reserved = 0.0
    pot_order_id = ""  # the id we used for the pot reservation
    if _POT_ENABLED and side.upper() == "BUY" and ref_price > 0:
        # Pre-reserve with a temporary id; we replace it post-placement
        # with the real broker_order_id so release() can find it on close.
        pot_order_id = f"pre_{worker_id}_{int(time.time()*1000)}"
        ok_pot, pot_reason, notional_gbp_reserved = _pot_reserve(
            venue, instrument, qty, ref_price, pot_order_id, worker_id)
        if not ok_pot:
            result = {"ok": False, "reason": pot_reason,
                       "broker_order_id": None, "response": None}
            _audit({"venue": venue, "worker_id": worker_id, "instrument": instrument,
                     "side": side, "qty": qty, **result})
            return result
    # 6. dispatch to venue-specific placer
    if venue == "oanda_practice":
        result = _place_oanda(instrument, side, qty, gv,
                              stop_distance=stop_distance,
                              take_distance=take_distance)
    elif venue == "alpaca_paper":
        result = _place_alpaca(instrument, side, qty, gv)
    elif venue == "binance_testnet":
        result = _place_binance(instrument, side, qty, gv)
    else:
        result = {"ok": False, "reason": f"no_handler:{venue}",
                   "broker_order_id": None, "response": None}
    if result["ok"]:
        _record_order(venue, worker_id)
        # Re-key the pot reservation under the actual broker order id so close-side
        # can release it. If broker rejected, release the pre-reservation.
        if _POT_ENABLED and pot_order_id:
            real_id = result.get("broker_order_id") or ""
            if real_id:
                _pot_release(pot_order_id)
                # Re-reserve under real id (rare race window; idempotent via order_id)
                _pot_reserve(venue, instrument, qty, ref_price, str(real_id), worker_id)
    else:
        # Broker rejected after we reserved — give the GBP back.
        if _POT_ENABLED and pot_order_id:
            _pot_release(pot_order_id)
    # On SELL, release the original open-side reservation.
    if _POT_ENABLED and side.upper() == "SELL" and open_order_id:
        _pot_release(open_order_id)
    _audit({"venue": venue, "worker_id": worker_id, "instrument": instrument,
             "side": side, "qty": qty, "notional_gbp": notional_gbp_reserved,
             **result})
    return result


def _place_oanda(instrument: str, side: str, qty: float, gv: dict,
                 stop_distance: float = 0.0,
                 take_distance: float = 0.0) -> dict:
    env = _load_vault_env(".env.oanda_practice")
    tok = env.get("OANDA_API_TOKEN") or env.get("OANDA_PRACTICE_TOKEN")
    acct = env.get("OANDA_ACCOUNT_ID") or env.get("OANDA_PRACTICE_ACCOUNT_ID")
    url = f"https://api-fxpractice.oanda.com/v3/accounts/{acct}/orders"
    if gv["url_must_contain"] not in url:
        return {"ok": False, "reason": "url_safety_check_failed",
                 "broker_order_id": None, "response": None}
    units = int(qty) if side.upper() == "BUY" else -int(qty)
    order = {"units": str(units), "instrument": instrument,
             "timeInForce": "FOK", "type": "MARKET",
             "positionFill": "DEFAULT"}
    # Broker-side stop / take. 2026-06-26 fix: per-instrument decimal precision.
    # OANDA rejects with TAKE_PROFIT_ON_FILL_DISTANCE_PRECISION_EXCEEDED if too
    # many decimals. JPY pairs use 3 dp, most majors use 5 dp, indices+metals 2 dp.
    inst_dp_map = {"USD_JPY": 3, "EUR_JPY": 3, "GBP_JPY": 3, "AUD_JPY": 3, "CHF_JPY": 3,
                    "XAU_USD": 2, "XAG_USD": 3,
                    "SPX500_USD": 1, "NAS100_USD": 1, "US30_USD": 1, "DE30_EUR": 1,
                    "JP225_USD": 1, "NATGAS_USD": 3, "WTICO_USD": 2, "BCO_USD": 2,
                    "WHEAT_USD": 2, "XCU_USD": 4, "USB10Y_USD": 3, "UK10YB_GBP": 3}
    inst_dp = inst_dp_map.get(instrument, 5)  # default 5 for fx majors
    if side.upper() == "BUY" and stop_distance > 0:
        order["stopLossOnFill"] = {"distance": f"{stop_distance:.{inst_dp}f}",
                                     "timeInForce": "GTC"}
    if side.upper() == "BUY" and take_distance > 0:
        order["takeProfitOnFill"] = {"distance": f"{take_distance:.{inst_dp}f}",
                                       "timeInForce": "GTC"}
    body = json.dumps({"order": order}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                   headers={"Authorization": f"Bearer {tok}",
                                            "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            status = r.status
            d = json.loads(r.read())
        if status // 100 != 2:
            return {"ok": False, "reason": f"oanda_http_{status}",
                     "broker_order_id": None, "response": d}
        tx = d.get("orderFillTransaction") or d.get("orderCreateTransaction")
        oid = tx.get("id") if tx else None
        return {"ok": True, "reason": "placed", "broker_order_id": oid, "response": d}
    except urllib.error.HTTPError as he:
        # 2026-06-26 — capture response body + extract rejectReason field
        try:
            body_resp = he.read().decode("utf-8", errors="ignore")
            try:
                rb = json.loads(body_resp)
                ort = rb.get("orderRejectTransaction", {}) or {}
                reject_reason = ort.get("rejectReason") or rb.get("errorMessage") or "?"
                body_resp = f"reject={reject_reason}"
            except Exception:
                body_resp = body_resp[:150]
        except Exception:
            body_resp = "(body read fail)"
        return {"ok": False,
                "reason": f"oanda_http_{he.code}:{body_resp}",
                "broker_order_id": None, "response": None}
    except Exception as e:
        return {"ok": False, "reason": f"oanda_err:{str(e)[:80]}",
                 "broker_order_id": None, "response": None}


def _place_alpaca(symbol: str, side: str, qty: float, gv: dict) -> dict:
    env = _load_vault_env(".env.alpaca_paper")
    key = env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_API_SECRET")
    url = "https://paper-api.alpaca.markets/v2/orders"
    if gv["url_must_contain"] not in url:
        return {"ok": False, "reason": "url_safety_check_failed",
                 "broker_order_id": None, "response": None}
    body = json.dumps({"symbol": symbol, "qty": str(qty),
                         "side": side.lower(), "type": "market",
                         "time_in_force": "day"}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                   headers={"APCA-API-KEY-ID": key,
                                            "APCA-API-SECRET-KEY": secret,
                                            "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            status = r.status
            d = json.loads(r.read())
        if status // 100 != 2:
            return {"ok": False, "reason": f"alpaca_http_{status}",
                     "broker_order_id": None, "response": d}
        return {"ok": True, "reason": "placed", "broker_order_id": d.get("id"),
                 "response": d}
    except Exception as e:
        return {"ok": False, "reason": f"alpaca_err:{str(e)[:80]}",
                 "broker_order_id": None, "response": None}


def _place_binance(symbol: str, side: str, qty: float, gv: dict) -> dict:
    env = _load_vault_env(".env.binance_testnet")
    key = env.get("QSB_BINANCE_TESTNET_API_KEY")
    secret = env.get("QSB_BINANCE_TESTNET_API_SECRET")
    base = (env.get("QSB_BINANCE_TESTNET_URL") or "https://testnet.binance.vision").rstrip("/")
    if gv["url_must_contain"] not in base:
        return {"ok": False, "reason": "url_safety_check_failed",
                 "broker_order_id": None, "response": None}
    # Per-symbol step-size rounding (Binance LOT_SIZE filter — varies per pair)
    step = (gv.get("per_symbol_step_size") or {}).get(symbol, 0.00001)
    # Round DOWN to nearest step (Binance is strict — over-precision = 400)
    import math
    qty = math.floor(qty / step) * step
    # Use enough decimals to render step exactly
    dp = max(0, -int(math.floor(math.log10(step))))
    qty = round(qty, dp)
    min_qty = (gv.get("per_symbol_min_qty") or {}).get(symbol, 0)
    if qty < min_qty:
        return {"ok": False, "reason": f"qty_below_symbol_min:{qty}<{min_qty}",
                 "broker_order_id": None, "response": None}
    qty_str = f"{qty:.{dp}f}"
    ts_ms = int(time.time() * 1000)
    qs = f"symbol={symbol}&side={side.upper()}&type=MARKET&quantity={qty_str}&timestamp={ts_ms}"
    sig = hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
    url = f"{base}/api/v3/order?{qs}&signature={sig}"
    req = urllib.request.Request(url, data=b"", method="POST",
                                   headers={"X-MBX-APIKEY": key})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            status = r.status
            d = json.loads(r.read())
        if status // 100 != 2:
            return {"ok": False, "reason": f"binance_http_{status}",
                     "broker_order_id": None, "response": d}
        return {"ok": True, "reason": "placed",
                 "broker_order_id": str(d.get("orderId")), "response": d}
    except urllib.error.HTTPError as he:
        # 2026-06-26 fix: HTTPError body contains the actual Binance code/msg
        # like {"code":-2010,"msg":"insufficient balance"}; old handler dropped it.
        try:
            body_raw = he.read().decode("utf-8", errors="ignore")
            body_obj = json.loads(body_raw)
            code = body_obj.get("code")
            msg = body_obj.get("msg", "")[:80]
            reason_str = f"binance_{he.code}_code{code}:{msg}"
        except Exception:
            reason_str = f"binance_http_{he.code}"
        # 2026-06-26: 429 = rate limited; sleep briefly so we don't immediately retry
        if he.code == 429:
            time.sleep(2.0)
        return {"ok": False, "reason": reason_str[:160],
                 "broker_order_id": None, "response": None}
    except Exception as e:
        return {"ok": False, "reason": f"binance_err:{str(e)[:80]}",
                 "broker_order_id": None, "response": None}


if __name__ == "__main__":
    # Self-test — calls with gate OFF should all refuse cleanly.
    print("=== self-test (gate file default OFF) ===")
    for venue, inst, qty in [("oanda_practice","EUR_USD",1000),
                              ("alpaca_paper","SPY",1),
                              ("binance_testnet","BTCUSDT",0.0001)]:
        r = place_order(venue, inst, "BUY", qty, worker_id="selftest")
        print(f"  {venue:16s}  {inst:8s}  ok={r['ok']}  reason={r['reason']}")
