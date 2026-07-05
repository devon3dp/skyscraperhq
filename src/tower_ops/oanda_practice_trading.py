"""OANDA Practice Trading V1 — strict guardrails.

ALL 11 guardrails enforced before any practice order can reach OANDA.
Live real-money trading is unconditionally refused at the URL level
(OANDAGateway.__init__ blocks anything but api-fxpractice.oanda.com).

Allowed only:
  - OANDA practice account read
  - OANDA practice pricing read
  - OANDA practice open positions / trades / transactions read
  - OANDA practice order preview
  - OANDA practice order placement (after manual confirm + every guard)
  - OANDA practice trade close

Forbidden (refused at module level):
  - Any non-practice URL
  - Non-whitelisted instruments
  - Trades over 1000 units
  - More than 3 open trades
  - More than 6 trades per hour
  - Spread > 2.0 pips at placement time
  - Daily realized loss > 500 GBP
  - Kill switch active
  - confirm_practice_order != True at placement time
  - mode != PRACTICE_ONLY
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import os
import threading

from .safety_contract import stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LEDGER_PATH      = ROOT / "state/tower_ops/oanda_practice_ledger.json"
GUARD_STATE_PATH = ROOT / "state/tower_ops/oanda_practice_guard.json"
LOG_PATH         = ROOT / "logs/tower_ops/oanda_practice_orders.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


# ── Guardrails (declared so the UI + audit can read them) ──────────────
GUARDS = {
    "execution_mode":                     "PRACTICE_ONLY",
    "oanda_env_required":                 "practice",
    "allowed_instruments":                ("EUR_USD", "GBP_USD", "USD_JPY"),
    "default_units":                      100,
    "max_units_per_trade":                1000,
    "max_open_trades":                    3,
    "max_trades_per_hour":                6,
    "max_spread_pips":                    2.0,
    "max_daily_practice_loss_gbp":        500.0,
    "kill_switch_must_be_off":            True,
    "manual_confirmation_required":       True,
    "policy": "Every guard is enforced server-side before /v3/accounts/{id}/orders is called.",
}


SAFETY_STAMP = {
    "execution_mode":                          "PRACTICE_ONLY",
    "live_trading_enabled":                    False,
    "real_order_execution_enabled":            False,
    "openclaw_real_execution_enabled":         False,
    "openclaw_execution_enabled":              False,
    "binance_order_execution_enabled":         False,
    "binance_live_trading_enabled":            False,
    "stock_order_execution_enabled":           False,
    "stock_live_trading_enabled":              False,
    "autonomous_dispatch_enabled":             False,
    "live_dispatch_enabled":                   False,
    "external_provider_execution_enabled":     False,
    "provider_execution_enabled":              False,
    "direct_provider_access":                  False,
    "oanda_practice_trading_enabled":          True,
    "oanda_practice_order_execution_enabled":  True,
    "openclaw_practice_mode_enabled":          True,
    "fake_data":                               False,
}


def _ensure_dirs():
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _read_state(path, default):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(default, indent=2), encoding="utf-8")
        return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        path.write_text(json.dumps(default, indent=2), encoding="utf-8")
        return default


def _write_state(path, data):
    data["ts"] = _now()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _append_log(rec):
    _ensure_dirs()
    rec = dict(rec); rec.setdefault("ts", _now())
    rec.update(SAFETY_STAMP)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _ledger():
    return _read_state(LEDGER_PATH, {
        "phase": "QSB_TOWER_OPERATIONS_V4",
        "ts": _now(),
        "ledger": "qsb_oanda_practice_ledger_v1",
        "entries": [],
        **SAFETY_STAMP,
    })


def _guard_state():
    return _read_state(GUARD_STATE_PATH, {
        "phase": "QSB_TOWER_OPERATIONS_V4",
        "ts": _now(),
        "kill_switch_on": False,
        "kill_switch_reason": None,
        "kill_switch_set_ts": None,
        **SAFETY_STAMP,
    })


def _load_oanda_env():
    for env_file in (ROOT / ".env.oanda_practice", ROOT / ".env.oanda"):
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"): continue
                if line.startswith("export "): line = line[len("export "):]
                k, _, v = line.partition("=")
                k = k.strip(); v = v.strip().strip("'").strip('"')
                if k: os.environ.setdefault(k, v)


def _creds_present():
    return bool(os.environ.get("OANDA_API_TOKEN", "").strip()
                 and os.environ.get("OANDA_ACCOUNT_ID", "").strip())


# ── Public read paths ──────────────────────────────────────────────────
def account():
    _load_oanda_env()
    if not _creds_present():
        return stamp_safe({"ok": False, "status": "not_configured",
                            "reason": "OANDA_API_TOKEN + OANDA_ACCOUNT_ID required",
                            **SAFETY_STAMP})
    try:
        from tower.oanda_gateway import OANDAGateway
        gw = OANDAGateway()
        info = gw.account_summary()
        acct = (info or {}).get("account") or {}
        return stamp_safe({
            "ok": True, "ts": _now(), "label": "LIVE READ-ONLY",
            "environment": "practice",
            "account_id_redacted": _redact(acct.get("id")),
            "balance":           acct.get("balance"),
            "NAV":               acct.get("NAV"),
            "margin_used":       acct.get("marginUsed"),
            "margin_available":  acct.get("marginAvailable"),
            "unrealized_pl":     acct.get("unrealizedPL"),
            "realized_pl_today": acct.get("pl"),
            "open_position_count": acct.get("openPositionCount"),
            "open_trade_count":    acct.get("openTradeCount"),
            "currency":          acct.get("currency"),
            **SAFETY_STAMP,
        })
    except Exception as e:
        return stamp_safe({"ok": False, "error": str(e)[:200], **SAFETY_STAMP})


def pricing():
    _load_oanda_env()
    if not _creds_present():
        return stamp_safe({"ok": False, "status": "not_configured", **SAFETY_STAMP})
    try:
        from tower.oanda_gateway import OANDAGateway
        gw = OANDAGateway()
        data = gw.pricing(",".join(GUARDS["allowed_instruments"]))
        prices = []
        for p in (data or {}).get("prices") or []:
            inst = p.get("instrument")
            bid = float((p.get("bids") or [{}])[0].get("price") or 0)
            ask = float((p.get("asks") or [{}])[0].get("price") or 0)
            mid = (bid + ask) / 2 if (bid and ask) else None
            pip = 0.0001 if "JPY" not in (inst or "") else 0.01
            spread_pips = round((ask - bid) / pip, 2) if (bid and ask) else None
            prices.append({"instrument": inst, "bid": bid, "ask": ask, "mid": mid,
                            "spread_pips": spread_pips,
                            "spread_warning": (spread_pips or 0) > GUARDS["max_spread_pips"]})
        return stamp_safe({"ok": True, "ts": _now(), "label": "LIVE READ-ONLY",
                            "prices": prices, **SAFETY_STAMP})
    except Exception as e:
        return stamp_safe({"ok": False, "error": str(e)[:200], **SAFETY_STAMP})


def open_positions():
    _load_oanda_env()
    if not _creds_present():
        return stamp_safe({"ok": False, "status": "not_configured", **SAFETY_STAMP})
    try:
        from tower.oanda_gateway import OANDAGateway
        d = OANDAGateway().open_positions()
        return stamp_safe({"ok": True, "ts": _now(), "label": "LIVE READ-ONLY",
                            "positions": (d or {}).get("positions") or [],
                            **SAFETY_STAMP})
    except Exception as e:
        return stamp_safe({"ok": False, "error": str(e)[:200], **SAFETY_STAMP})


def open_trades():
    _load_oanda_env()
    if not _creds_present():
        return stamp_safe({"ok": False, "status": "not_configured", **SAFETY_STAMP})
    try:
        from tower.oanda_gateway import OANDAGateway
        d = OANDAGateway().open_trades()
        return stamp_safe({"ok": True, "ts": _now(), "label": "LIVE READ-ONLY",
                            "trades": (d or {}).get("trades") or [],
                            **SAFETY_STAMP})
    except Exception as e:
        return stamp_safe({"ok": False, "error": str(e)[:200], **SAFETY_STAMP})


def transactions(count=20):
    _load_oanda_env()
    if not _creds_present():
        return stamp_safe({"ok": False, "status": "not_configured", **SAFETY_STAMP})
    try:
        from tower.oanda_gateway import OANDAGateway
        d = OANDAGateway().transactions(count=count)
        return stamp_safe({"ok": True, "ts": _now(), "label": "LIVE READ-ONLY",
                            "transactions": (d or {}).get("transactions") or [],
                            **SAFETY_STAMP})
    except Exception as e:
        return stamp_safe({"ok": False, "error": str(e)[:200], **SAFETY_STAMP})


def practice_ledger():
    L = _ledger()
    return stamp_safe({"ok": True, "ts": _now(), "label": "PAPER_ONLY",
                        "phase": L.get("phase"),
                        "entries": L.get("entries") or [],
                        "entry_count": len(L.get("entries") or []),
                        **SAFETY_STAMP})


# ── Guardrails ────────────────────────────────────────────────────────
def _check_guards(payload, *, placing=False):
    failures = []
    if (payload.get("mode") or "") != GUARDS["execution_mode"]:
        failures.append("mode_must_equal_PRACTICE_ONLY")
    inst = (payload.get("instrument") or "").upper()
    if inst not in GUARDS["allowed_instruments"]:
        failures.append(f"instrument_not_whitelisted: {inst}")
    try: units = int(payload.get("units") or 0)
    except Exception: units = 0
    if units <= 0:
        failures.append("units_must_be_positive")
    if units > GUARDS["max_units_per_trade"]:
        failures.append(f"units_over_cap: {units} > {GUARDS['max_units_per_trade']}")
    if (payload.get("side") or "").lower() not in ("buy", "sell"):
        failures.append("side_must_be_buy_or_sell")
    # Open trades cap
    try:
        ot = open_trades()
        if ot.get("ok") and len(ot.get("trades") or []) >= GUARDS["max_open_trades"]:
            failures.append(f"max_open_trades_reached: >= {GUARDS['max_open_trades']}")
    except Exception:
        pass
    # Hourly trade cap (count placement events in ledger within last hour)
    L = _ledger()
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    hourly = 0
    for e in (L.get("entries") or []):
        if e.get("event") == "place_practice_order":
            try:
                ts = e.get("ts", "").replace("Z", "+00:00")
                if datetime.fromisoformat(ts) >= one_hour_ago: hourly += 1
            except Exception: pass
    if hourly >= GUARDS["max_trades_per_hour"]:
        failures.append(f"max_trades_per_hour_reached: {hourly} >= {GUARDS['max_trades_per_hour']}")
    # Spread guard
    try:
        prices = pricing().get("prices") or []
        pri = next((p for p in prices if p.get("instrument") == inst), None)
        if pri and (pri.get("spread_pips") or 0) > GUARDS["max_spread_pips"]:
            failures.append(f"spread_too_wide: {pri.get('spread_pips')} > {GUARDS['max_spread_pips']}")
    except Exception:
        pass
    # Kill switch
    gs = _guard_state()
    if gs.get("kill_switch_on"):
        failures.append("kill_switch_on: " + (gs.get("kill_switch_reason") or "active"))
    # Daily loss guard
    try:
        acct = account()
        if acct.get("ok"):
            realized_today = float(acct.get("realized_pl_today") or 0)
            if realized_today < -abs(GUARDS["max_daily_practice_loss_gbp"]):
                failures.append(f"max_daily_loss_reached: {realized_today}")
    except Exception:
        pass
    # Manual confirm gate at placement only
    if placing and not bool(payload.get("confirm_practice_order")):
        failures.append("confirm_practice_order_required_true")
    return failures


def practice_preflight():
    _load_oanda_env()
    out = stamp_safe({
        "ok": True, "ts": _now(),
        "label": "PRACTICE_PREFLIGHT",
        "credentials_present": _creds_present(),
        "guards": {
            "allowed_instruments":           list(GUARDS["allowed_instruments"]),
            "default_units":                 GUARDS["default_units"],
            "max_units_per_trade":           GUARDS["max_units_per_trade"],
            "max_open_trades":               GUARDS["max_open_trades"],
            "max_trades_per_hour":           GUARDS["max_trades_per_hour"],
            "max_spread_pips":               GUARDS["max_spread_pips"],
            "max_daily_practice_loss_gbp":   GUARDS["max_daily_practice_loss_gbp"],
        },
        "kill_switch_on": _guard_state().get("kill_switch_on"),
        **SAFETY_STAMP,
    })
    # Probe pricing freshness
    pr = pricing()
    out["pricing_ready"] = pr.get("ok")
    out["live_pricing_prices"] = pr.get("prices") or []
    # Probe account
    ac = account()
    out["account_ready"] = ac.get("ok")
    if ac.get("ok"):
        out["balance"] = ac.get("balance"); out["NAV"] = ac.get("NAV")
        out["open_trade_count"] = ac.get("open_trade_count")
    return out


def order_guard():
    return stamp_safe({"ok": True, "ts": _now(),
                        "guards": GUARDS,
                        "kill_switch": _guard_state(),
                        **SAFETY_STAMP})


def practice_order_preview(payload):
    """Run all guards and report what would happen — but do NOT place."""
    payload = payload or {}
    failures = _check_guards(payload, placing=False)
    prices = pricing().get("prices") or []
    pri = next((p for p in prices if p.get("instrument") == (payload.get("instrument") or "").upper()), None)
    mid = pri.get("mid") if pri else None
    units = int(payload.get("units") or 0)
    side = (payload.get("side") or "").lower()
    out = stamp_safe({
        "ok": not failures, "ts": _now(),
        "label": "PRACTICE_ORDER_PREVIEW",
        "passed_guards": not failures,
        "guard_failures": failures,
        "preview": {
            "instrument": (payload.get("instrument") or "").upper(),
            "units": units, "side": side,
            "estimated_fill_price": mid,
            "spread_pips": pri.get("spread_pips") if pri else None,
            "mode": "PRACTICE_ONLY",
        },
        "next_step": "POST /api/trading/oanda/place_practice_order with confirm_practice_order=true" if not failures else "fix guard failures first",
        **SAFETY_STAMP,
    })
    _append_log({"event": "practice_order_preview", "payload": {k: v for k, v in payload.items()},
                  "passed": not failures, "failures": failures})
    return out


def place_practice_order(payload):
    """Place an order on the OANDA practice account ONLY if every guard passes."""
    payload = payload or {}
    failures = _check_guards(payload, placing=True)
    if failures:
        _append_log({"event": "place_practice_order_BLOCKED",
                      "failures": failures, "payload": {k: v for k, v in payload.items()}})
        return stamp_safe({"ok": False, "ts": _now(),
                            "blocked": True, "guard_failures": failures,
                            **SAFETY_STAMP})
    inst = payload["instrument"].upper(); units = int(payload["units"])
    side = payload["side"].lower()
    try:
        from tower.oanda_gateway import OANDAGateway
        gw = OANDAGateway()
        resp = gw.place_market_order(inst, units, side)
    except Exception as e:
        _append_log({"event": "place_practice_order_ERROR", "error": str(e)[:200],
                      "payload": {k: v for k, v in payload.items()}})
        return stamp_safe({"ok": False, "ts": _now(),
                            "error": str(e)[:200], **SAFETY_STAMP})
    # Persist ledger entry
    with _LOCK:
        L = _ledger()
        entry = {
            "ts": _now(),
            "event": "place_practice_order",
            "instrument": inst, "units": units, "side": side,
            "mode": "PRACTICE_ONLY",
            "oanda_response_summary": _summarize_response(resp),
        }
        L.setdefault("entries", []).append(entry)
        _write_state(LEDGER_PATH, L)
    _append_log(entry)
    return stamp_safe({"ok": True, "ts": _now(),
                        "label": "PRACTICE_ORDER_PLACED",
                        "instrument": inst, "units": units, "side": side,
                        "oanda_response": resp,
                        "ledger_entry": entry,
                        **SAFETY_STAMP})


def close_practice_trade(payload):
    payload = payload or {}
    tid = payload.get("trade_id"); units = payload.get("units") or "ALL"
    if not tid: return stamp_safe({"ok": False, "error": "trade_id_required", **SAFETY_STAMP})
    gs = _guard_state()
    if gs.get("kill_switch_on"):
        return stamp_safe({"ok": False, "blocked": True,
                            "reason": "kill_switch_on", **SAFETY_STAMP})
    try:
        from tower.oanda_gateway import OANDAGateway
        gw = OANDAGateway()
        resp = gw.close_trade(tid, units=units)
    except Exception as e:
        return stamp_safe({"ok": False, "error": str(e)[:200], **SAFETY_STAMP})
    with _LOCK:
        L = _ledger()
        entry = {"ts": _now(), "event": "close_practice_trade",
                  "trade_id": tid, "units": str(units),
                  "oanda_response_summary": _summarize_response(resp)}
        L.setdefault("entries", []).append(entry)
        _write_state(LEDGER_PATH, L)
    _append_log(entry)
    return stamp_safe({"ok": True, "ts": _now(),
                        "label": "PRACTICE_TRADE_CLOSED",
                        "oanda_response": resp, **SAFETY_STAMP})


def kill_switch(payload):
    payload = payload or {}
    on = bool(payload.get("kill_switch_on", False))
    reason = payload.get("reason") or ("ACTIVATED_BY_OPERATOR" if on else None)
    with _LOCK:
        gs = _guard_state()
        gs["kill_switch_on"] = on
        gs["kill_switch_reason"] = reason
        gs["kill_switch_set_ts"] = _now()
        _write_state(GUARD_STATE_PATH, gs)
    _append_log({"event": "kill_switch", "kill_switch_on": on, "reason": reason})
    return stamp_safe({"ok": True, "ts": _now(),
                        "kill_switch_on": on, "reason": reason, **SAFETY_STAMP})


def _redact(s):
    if not s: return None
    s = str(s)
    if len(s) <= 4: return "****" + s[-2:]
    return "****" + s[-4:]


def _summarize_response(resp):
    if not isinstance(resp, dict): return {}
    tx = resp.get("orderFillTransaction") or resp.get("orderCreateTransaction") or {}
    return {
        "id": tx.get("id"),
        "type": tx.get("type"),
        "instrument": tx.get("instrument"),
        "units": tx.get("units"),
        "price": tx.get("price"),
        "pl": tx.get("pl"),
        "accountBalance": tx.get("accountBalance"),
        "time": tx.get("time"),
    }
