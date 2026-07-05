"""
QSB Floor 41 OANDA Full Trading Floor (V1)
Phase: QSB_FLOOR_41_OANDA_FULL_TRADING_FLOOR_REBUILD_V1

Orchestrator that produces the complete Floor 41 OANDA registry family
without replacing the existing oanda_trading_floor / paper_strategy_lab
modules. Adds:

  - department/room/worker map (13 rooms, 12 workers, deterministic
    placement)
  - trading engine snapshot (mode = oanda_practice_api / paper_simulator
    / disabled), account, instruments, prices, ticks, spreads
  - open trades + closed trades + PnL (sourced from existing OANDA
    practice API endpoints if reachable, else from paper ledger)
  - trade lifecycle (request, risk check, Guardian gate, action)
  - worker thoughts (source-backed, paper-labelled, no certainty)
  - OpenClaw Floor 41 findings + tickets
  - worker movements + packets when trades open/close
  - dashboard interior payload for the frontend

Safety:
  - All write operations are additive registry writes — no real-money
    orders, no live environment.
  - Engine mode is forced to paper_simulator if the practice API call
    fails or env is missing; never falls through to live.
  - Hard locks stamped on every payload.
"""

from datetime import datetime, timezone, timedelta
from hashlib import blake2b
from pathlib import Path
import json
import os
import re
import urllib.request

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

PHASE = "QSB_FLOOR_41_OANDA_FULL_TRADING_FLOOR_REBUILD_V1"

EVENTS_LOG = LOGS / "qsb_floor41_oanda_events.jsonl"
LEDGER_LOG = LOGS / "qsb_floor41_oanda_trade_ledger.jsonl"
THOUGHTS_LOG = LOGS / "qsb_floor41_oanda_worker_thoughts.jsonl"
EQSB_EVENTS = LOGS / "eqsb_kernel_events.jsonl"
EQSB_HISTORY = LOGS / "eqsb_phase_history.jsonl"

OANDA_PRACTICE_BASE = "https://api-fxpractice.oanda.com"
DEFAULT_INSTRUMENTS = [
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD",
    "EUR_GBP",   # cross used by eur_gbp_range strategy
    # ── Commodities (added 2026-06-10 for Wren strategy library) ──
    "XAU_USD",   # gold
    "XAG_USD",   # silver
    "BCO_USD",   # Brent crude
    "WTICO_USD", # WTI crude
    "NATGAS_USD",# natural gas
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safety():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "oanda_practice_paper_trading_allowed": True,
        "live_money_enabled": False,
        "oanda_live_environment_allowed": False,
        "real_production_trading_allowed": False,
        "real_money_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
        "worker_execution_enabled": False,
        "autonomous_dispatch_enabled": False,
    }


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _append_jsonl(path, rec):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def _eqsb_record(event, payload):
    rec = {"ts": _now(), "phase": PHASE, "event": event, "payload": payload}
    _append_jsonl(EQSB_EVENTS, rec)
    _append_jsonl(EQSB_HISTORY, rec)


def _stable_idx(seed, modulo):
    if modulo <= 0:
        return 0
    return int.from_bytes(blake2b(str(seed).encode("utf-8"), digest_size=4).digest(), "big") % modulo


# ── Engine mode detection ────────────────────────────────────────────


def _practice_creds_present():
    token = os.environ.get("OANDA_API_TOKEN") or os.environ.get("OANDA_TOKEN")
    acct = os.environ.get("OANDA_ACCOUNT_ID")
    return bool(token) and bool(acct)


def _try_practice_api():
    """Lightweight reachability probe — does NOT fetch live data here.
    The actual data pull is handled via tower_ops.trading_telemetry to
    keep this module's surface narrow."""
    if not _practice_creds_present():
        return False
    try:
        req = urllib.request.Request(
            OANDA_PRACTICE_BASE + "/v3/accounts",
            headers={"Authorization": "Bearer " + (os.environ.get("OANDA_API_TOKEN") or os.environ.get("OANDA_TOKEN", ""))},
        )
        with urllib.request.urlopen(req, timeout=4) as r:
            return r.status == 200
    except Exception:
        return False


def engine_mode():
    if _practice_creds_present() and _try_practice_api():
        return "oanda_practice_api"
    if _practice_creds_present():
        return "paper_simulator"
    # No creds — still allow paper_simulator (local prices), keep safe.
    return "paper_simulator"


# ── Department map + workers ─────────────────────────────────────────


ROOMS = [
    "Market Feed Desk",
    "Instrument Watch Board",
    "Spread Watch Station",
    "Strategy Desk",
    "Order Entry Desk",
    "Open Trades Board",
    "Close Trade Desk",
    "PnL Accounting Desk",
    "Risk / Guardian Station",
    "OpenClaw Inspection Post",
    "Audit Dispatch",
    "Lessons Output Desk",
    "Worker Thought Console",
]

WORKERS = [
    {
        "worker_id": "f41_floor_manager",
        "role": "OANDA Floor Manager",
        "room": "Strategy Desk",
        "default_task": "coordinate floor + approve trades",
    },
    {
        "worker_id": "f41_market_scout",
        "role": "FX Market Scout",
        "room": "Market Feed Desk",
        "default_task": "watch live practice quotes",
    },
    {
        "worker_id": "f41_spread_watcher",
        "role": "Spread Watcher",
        "room": "Spread Watch Station",
        "default_task": "compare bid/ask spread vs threshold",
    },
    {
        "worker_id": "f41_risk_sentinel",
        "role": "Risk Sentinel",
        "room": "Risk / Guardian Station",
        "default_task": "block trades over risk budget",
    },
    {
        "worker_id": "f41_paper_strategy_analyst",
        "role": "Paper Strategy Analyst",
        "room": "Strategy Desk",
        "default_task": "rank candidate strategies",
    },
    {
        "worker_id": "f41_order_entry_clerk",
        "role": "Order Entry Clerk",
        "room": "Order Entry Desk",
        "default_task": "format and submit practice/paper orders",
    },
    {
        "worker_id": "f41_close_trade_clerk",
        "role": "Close Trade Clerk",
        "room": "Close Trade Desk",
        "default_task": "format and submit practice/paper closes",
    },
    {
        "worker_id": "f41_pnl_accountant",
        "role": "PnL Accountant",
        "room": "PnL Accounting Desk",
        "default_task": "compute realized + unrealized PnL",
    },
    {
        "worker_id": "f41_trade_ledger_clerk",
        "role": "Trade Ledger Clerk",
        "room": "Audit Dispatch",
        "default_task": "append every trade event to ledger",
    },
    {
        "worker_id": "f41_lessons_clerk",
        "role": "Lessons Clerk",
        "room": "Lessons Output Desk",
        "default_task": "emit lessons from losing closed trades",
    },
    {
        "worker_id": "f41_openclaw_oanda_inspector",
        "role": "OpenClaw OANDA Inspector",
        "room": "OpenClaw Inspection Post",
        "default_task": "supervise floor — read-only, no execution",
    },
    {
        "worker_id": "f41_kernel_commentary_runner",
        "role": "Kernel Commentary Runner",
        "room": "Worker Thought Console",
        "default_task": "shape kernel chat answers for Floor 41",
    },
]


def build_department_map():
    rooms_meta = []
    for idx, room in enumerate(ROOMS):
        rooms_meta.append({
            "room_id": "f41_room_{:02d}".format(idx + 1),
            "name": room,
            "position": idx + 1,
            "responsibility": _room_responsibility(room),
        })
    payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_department_map",
        "phase": PHASE,
        "generated_ts": _now(),
        "floor": 41,
        "department": "OANDA Trading Floor",
        "zone": "ZONE C",
        "room_count": len(rooms_meta),
        "rooms": rooms_meta,
    }
    payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_department_map.json", payload)
    return payload


def _room_responsibility(room):
    return {
        "Market Feed Desk": "consume OANDA practice pricing stream",
        "Instrument Watch Board": "tile each instrument with bid/ask/spread",
        "Spread Watch Station": "alert when spread exceeds threshold",
        "Strategy Desk": "rank strategies, propose entries",
        "Order Entry Desk": "submit practice/paper open orders",
        "Open Trades Board": "show every open trade with mark + uPnL",
        "Close Trade Desk": "submit practice/paper close orders",
        "PnL Accounting Desk": "compute realized + unrealized + total",
        "Risk / Guardian Station": "veto trades over risk thresholds",
        "OpenClaw Inspection Post": "read-only supervisor checks",
        "Audit Dispatch": "append events to ledger + audit log",
        "Lessons Output Desk": "emit lessons from losing closed trades",
        "Worker Thought Console": "stream worker thoughts to dashboard",
    }.get(room, "general floor function")


def build_workers(packets_emitted=0):
    rec_workers = []
    ts = _now()
    for w in WORKERS:
        room = w["room"]
        station_idx = (_stable_idx(w["worker_id"], 12) + 1)
        station = "{} · station #{:02d}".format(room, station_idx)
        rec_workers.append({
            "worker_id": w["worker_id"],
            "role": w["role"],
            "room": room,
            "station": station,
            "current_task": w["default_task"],
            "state": "idle_at_station" if packets_emitted == 0 else "active",
            "last_update_ts": ts,
            "stable": True,
            "source": "qsb_floor41_oanda.py",
        })
    payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_workers",
        "phase": PHASE,
        "generated_ts": ts,
        "floor": 41,
        "worker_count": len(rec_workers),
        "workers": rec_workers,
    }
    payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_workers.json", payload)
    return payload


# ── Trading engine snapshot ──────────────────────────────────────────


def _fetch_oanda_account():
    try:
        from tower_ops.trading_telemetry import oanda_account
        return oanda_account()
    except Exception:
        return None


def _fetch_oanda_pricing():
    """Direct OANDA practice pricing fetch for the full DEFAULT_INSTRUMENTS list.
    The tower_ops wrapper only fetches its own 3-instrument whitelist; this
    path covers commodities (XAU/XAG/BCO/WTICO) and crosses (EUR_GBP) too.
    Read-only — does NOT touch any execution gate."""
    try:
        import os, urllib.request, json as _json
        token = os.environ.get("OANDA_API_TOKEN")
        account = os.environ.get("OANDA_ACCOUNT_ID")
        if not (token and account):
            from tower_ops import oanda_practice_pricing
            return oanda_practice_pricing()
        url = (f"https://api-fxpractice.oanda.com/v3/accounts/{account}"
                f"/pricing?instruments={','.join(DEFAULT_INSTRUMENTS)}")
        req = urllib.request.Request(url,
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return _json.loads(r.read().decode())
    except Exception:
        try:
            from tower_ops import oanda_practice_pricing
            return oanda_practice_pricing()
        except Exception:
            return None


def _fetch_oanda_open_trades():
    try:
        from tower_ops import oanda_open_trades_practice
        return oanda_open_trades_practice()
    except Exception:
        return None


def _fetch_oanda_transactions():
    try:
        from tower_ops import oanda_practice_transactions
        return oanda_practice_transactions()
    except Exception:
        return None


def _pip_size(instrument):
    # JPY pairs use 0.01; commodities have their own pip sizes; FX default 0.0001.
    if instrument in ("XAU_USD",):
        return 0.01
    if instrument in ("XAG_USD",):
        return 0.001
    if instrument in ("BCO_USD", "WTICO_USD"):
        return 0.01
    if instrument in ("NATGAS_USD",):
        return 0.001
    return 0.01 if "JPY" in instrument else 0.0001


def _paper_simulator_prices():
    """Deterministic local prices driven by EQSB cadence tick — NOT random
    visuals. Each refresh uses the cadence tick count to perturb the
    mid; same tick → same prices."""
    cad = _load("eqsb_cadence_state.json", {})
    tick = int(cad.get("tick_count") or 0)
    seeds = {
        "EUR_USD": 1.0865,
        "GBP_USD": 1.2710,
        "USD_JPY": 148.32,
        "AUD_USD": 0.6585,
        "USD_CAD": 1.3620,
        "EUR_GBP": 0.8550,
        # Commodities — seeded near recent prints; cadence drift handles micro-moves.
        "XAU_USD": 4126.6,
        "XAG_USD": 64.89,
        "BCO_USD": 95.76,
        "WTICO_USD": 92.09,
        "NATGAS_USD": 2.84,
    }
    prices = []
    for inst, mid in seeds.items():
        pip = _pip_size(inst)
        # Deterministic micro drift from tick
        drift = ((tick % 17) - 8) * pip * 0.3
        bid = round(mid + drift, 5)
        ask = round(bid + pip * 1.4, 5)
        prices.append({
            "instrument": inst,
            "bid": bid,
            "ask": ask,
            "spread": round(ask - bid, 6),
            "spread_pips": round((ask - bid) / pip, 2),
            "ts": _now(),
            "source": "paper_simulator (deterministic, EQSB cadence tick={})".format(tick),
        })
    return prices


def build_account_snapshot(mode):
    acct = _fetch_oanda_account() if mode == "oanda_practice_api" else None
    if isinstance(acct, dict) and acct.get("ok") is not False:
        # Normalize what tower_ops returns into our shape.
        a = acct.get("account") or acct
        payload = {
            "ok": True,
            "kind": "qsb_floor41_oanda_account_snapshot",
            "phase": PHASE,
            "generated_ts": _now(),
            "mode": mode,
            "account_id": a.get("id") or os.environ.get("OANDA_ACCOUNT_ID"),
            "currency": a.get("currency") or "USD",
            "balance": float(a.get("balance") or 100000),
            "NAV": float(a.get("NAV") or a.get("balance") or 100000),
            "margin_used": float(a.get("marginUsed") or 0),
            "margin_available": float(a.get("marginAvailable") or 0),
            "unrealized_PL": float(a.get("unrealizedPL") or 0),
            "open_trade_count": int(a.get("openTradeCount") or 0),
            "open_position_count": int(a.get("openPositionCount") or 0),
            "source": "oanda_practice_api",
        }
    else:
        payload = {
            "ok": True,
            "kind": "qsb_floor41_oanda_account_snapshot",
            "phase": PHASE,
            "generated_ts": _now(),
            "mode": mode,
            "account_id": os.environ.get("OANDA_ACCOUNT_ID") or "paper_account_001",
            "currency": "USD",
            "balance": 100000.0,
            "NAV": 100000.0,
            "margin_used": 0.0,
            "margin_available": 100000.0,
            "unrealized_PL": 0.0,
            "open_trade_count": 0,
            "open_position_count": 0,
            "source": "paper_simulator (account API unreachable or disabled)",
        }
    payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_account_snapshot.json", payload)
    return payload


def build_instruments():
    instruments = []
    for inst in DEFAULT_INSTRUMENTS:
        instruments.append({
            "instrument": inst,
            "display_name": inst.replace("_", "/"),
            "pip_location": -4 if "JPY" not in inst else -2,
            "active": True,
            "tradeable_in_paper": True,
            "tradeable_live": False,
        })
    payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_instruments",
        "phase": PHASE,
        "generated_ts": _now(),
        "instrument_count": len(instruments),
        "instruments": instruments,
    }
    payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_instruments.json", payload)
    return payload


def build_prices_and_ticks(mode):
    api_prices = _fetch_oanda_pricing() if mode == "oanda_practice_api" else None
    prices = []
    if isinstance(api_prices, dict):
        items = api_prices.get("prices") or api_prices.get("items") or []
        if isinstance(items, list):
            for p in items:
                if not isinstance(p, dict):
                    continue
                inst = p.get("instrument")
                try:
                    bids = p.get("bids") or []
                    asks = p.get("asks") or []
                    bid = float((bids[0] or {}).get("price")) if bids else None
                    ask = float((asks[0] or {}).get("price")) if asks else None
                except Exception:
                    bid, ask = None, None
                if inst and bid and ask:
                    pip = _pip_size(inst)
                    prices.append({
                        "instrument": inst,
                        "bid": bid,
                        "ask": ask,
                        "spread": round(ask - bid, 6),
                        "spread_pips": round((ask - bid) / pip, 2),
                        "ts": p.get("time") or _now(),
                        "source": "oanda_practice_api",
                    })
    if not prices:
        prices = _paper_simulator_prices()

    prices_payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_prices_latest",
        "phase": PHASE,
        "generated_ts": _now(),
        "mode": mode,
        "price_count": len(prices),
        "prices": prices,
    }
    prices_payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_prices_latest.json", prices_payload)

    ticks_payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_ticks_latest",
        "phase": PHASE,
        "generated_ts": _now(),
        "tick_count": len(prices),
        "ticks": [
            {
                "instrument": p["instrument"],
                "bid": p["bid"],
                "ask": p["ask"],
                "spread_pips": p["spread_pips"],
                "ts": p["ts"],
            }
            for p in prices
        ],
    }
    ticks_payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_ticks_latest.json", ticks_payload)
    return prices_payload


# ── Trade lifecycle ──────────────────────────────────────────────────


def _load_lifecycle_state():
    return _load("qsb_floor41_oanda_trade_lifecycle.json", {
        "open_trades": [],
        "closed_trades": [],
        "requests": [],
        "actions": [],
        "next_request_id": 1,
        "next_trade_id": 1,
    })


def _write_lifecycle_state(state):
    state["ok"] = True
    state["kind"] = "qsb_floor41_oanda_trade_lifecycle"
    state["phase"] = PHASE
    state["generated_ts"] = _now()
    state.update(_safety())
    _write(REG / "qsb_floor41_oanda_trade_lifecycle.json", state)


def _risk_check(instrument, units, prices):
    """Returns (allowed: bool, reasons: list[str])."""
    reasons_block = []
    p = next((x for x in (prices or []) if x.get("instrument") == instrument), None)
    if not p:
        reasons_block.append("no_quote_for_instrument")
    spread = p.get("spread_pips") if p else None
    if spread is not None and spread > 5.0:
        reasons_block.append("spread_too_wide_pips={:.1f}".format(spread))
    try:
        units = float(units)
    except Exception:
        reasons_block.append("units_invalid")
        units = 0.0
    if units > 50000:
        reasons_block.append("units_over_max_50000")
    # Allow fractional minimums (Gold: 0.1). Block only at or below zero.
    if units <= 0:
        reasons_block.append("units_must_be_positive")
    # Enforce max_open_trades from floor card guardrails so the cohort tool
    # can't open past the configured ceiling.
    try:
        guards = _load("qsb_floor41_oanda_state.json", {}).get("live_signals", {})
        cap = int(guards.get("max_open_trades", 3))
        cur_open = len(_load_lifecycle_state().get("open_trades", []))
        if cur_open >= cap:
            reasons_block.append("max_open_trades={}_reached(current={})".format(cap, cur_open))
    except Exception:
        pass
    return (len(reasons_block) == 0, reasons_block)


def _guardian_check():
    """Read Guardian state — block if not OK."""
    gov = _load("eqsb_guardian_state.json", {})
    state = (gov.get("safety_state") or "OK").upper()
    if state in ("OK", "DEGRADED", "DRIFTING"):
        return (True, "guardian_state={}".format(state))
    return (False, "guardian_state={}".format(state))


def open_paper_trade(instrument, direction, units, entry_reason, strategy_name="manual",
                     worker_id="f41_order_entry_clerk", execution_mode=None):
    """Open a paper/practice trade. Refuses live mode unconditionally."""
    if execution_mode == "live":
        return {"ok": False, "error": "live_mode_blocked_at_module"}
    if not entry_reason:
        return {"ok": False, "error": "entry_reason_required"}
    mode = execution_mode or "paper_simulator"
    # Force-paper fallback regardless of caller intent.
    if mode not in ("paper_simulator", "oanda_practice_api"):
        mode = "paper_simulator"

    prices_doc = _load("qsb_floor41_oanda_prices_latest.json", {})
    prices = prices_doc.get("prices") or []
    quote = next((p for p in prices if p.get("instrument") == instrument), None)
    if not quote:
        return {"ok": False, "error": "no_quote_for_instrument:{}".format(instrument)}

    risk_ok, risk_reasons = _risk_check(instrument, units, prices)
    guardian_ok, guardian_msg = _guardian_check()

    state = _load_lifecycle_state()
    rid = "req_{:08d}".format(state["next_request_id"])
    state["next_request_id"] += 1

    # OANDA accepts fractional units for some instruments (Gold at 0.1 minimum).
    # Cast to int when caller passed a whole number, keep float otherwise.
    units_recorded = (int(units) if (isinstance(units, int) or
                                        (isinstance(units, float) and units.is_integer()))
                                  else float(units))
    req = {
        "request_id": rid,
        "instrument": instrument,
        "direction": direction,
        "units": units_recorded,
        "entry_reason": entry_reason,
        "strategy_name": strategy_name,
        "worker_id": worker_id,
        "risk_check_status": "passed" if risk_ok else "blocked",
        "risk_check_reasons": risk_reasons,
        "manager_approval_status": "auto_approved_paper" if guardian_ok and risk_ok else "blocked",
        "guardian_status": guardian_msg,
        "created_ts": _now(),
        "execution_mode": mode,
    }
    state["requests"].append(req)

    if not (risk_ok and guardian_ok):
        action = {
            "request_id": rid,
            "action": "open_rejected",
            "reasons": risk_reasons + ([guardian_msg] if not guardian_ok else []),
            "ts": _now(),
        }
        state["actions"].append(action)
        _write_lifecycle_state(state)
        _append_jsonl(EVENTS_LOG, {"event": "open_rejected", **action, **req})
        _append_jsonl(LEDGER_LOG, {"event": "open_rejected", **action, **req})
        _emit_packets("open_rejected", req)
        return {"ok": False, "rejected": True, "request": req}

    tid = "trd_{:08d}".format(state["next_trade_id"])
    state["next_trade_id"] += 1
    # 2026-06-21 spread-bleed fix: paper_simulator was 0/595 wins because
    # prices barely move between open + close so the synthetic round-trip
    # ate the full bid-ask spread every time (~0.33 GBP per 100u trade,
    # matching observed -£0.33/trade). Use mid-price in paper_simulator;
    # real oanda_practice_api keeps bid/ask discipline. Team-decided:
    # Wren + OpenAI + iquest + qwen3.5 all picked mid-price; Hermes alone
    # picked widen-TP and was overruled.
    if mode == "paper_simulator":
        entry_price = round((quote["bid"] + quote["ask"]) / 2.0, 6)
    else:
        entry_price = quote["ask"] if direction == "buy" else quote["bid"]
    trade = {
        "trade_id": tid,
        "request_id": rid,
        "instrument": instrument,
        "direction": direction,
        "units": int(units),
        "entry_price": entry_price,
        "entry_reason": entry_reason,
        "strategy_name": strategy_name,
        "worker_id": worker_id,
        "opened_ts": _now(),
        "status": "open",
        "execution_mode": mode,
        "guardian_status": guardian_msg,
    }
    state["open_trades"].append(trade)
    state["actions"].append({
        "request_id": rid,
        "trade_id": tid,
        "action": "open_filled",
        "ts": _now(),
    })
    _write_lifecycle_state(state)
    _append_jsonl(EVENTS_LOG, {"event": "open_filled", **trade})
    _append_jsonl(LEDGER_LOG, {"event": "open_filled", **trade})
    _emit_packets("open_filled", trade)
    return {"ok": True, "trade": trade}


def close_paper_trade(trade_id, close_reason, worker_id="f41_close_trade_clerk"):
    if not close_reason:
        return {"ok": False, "error": "close_reason_required"}
    state = _load_lifecycle_state()
    trade = next((t for t in state.get("open_trades", []) if t.get("trade_id") == trade_id), None)
    if not trade:
        return {"ok": False, "error": "open_trade_not_found:{}".format(trade_id)}

    prices_doc = _load("qsb_floor41_oanda_prices_latest.json", {})
    prices = prices_doc.get("prices") or []
    quote = next((p for p in prices if p.get("instrument") == trade["instrument"]), None)
    if not quote:
        return {"ok": False, "error": "no_quote_for_close:{}".format(trade["instrument"])}
    # 2026-06-21 spread-bleed fix (paired with line 686).
    if trade.get("execution_mode") == "paper_simulator":
        exit_price = round((quote["bid"] + quote["ask"]) / 2.0, 6)
    else:
        exit_price = quote["bid"] if trade["direction"] == "buy" else quote["ask"]
    pip = _pip_size(trade["instrument"])
    direction_sign = 1 if trade["direction"] == "buy" else -1
    pnl_pips = direction_sign * (exit_price - trade["entry_price"]) / pip
    pnl_amount = round(direction_sign * (exit_price - trade["entry_price"]) * trade["units"], 4)

    guardian_ok, guardian_msg = _guardian_check()
    closed = dict(trade)
    closed.update({
        "exit_price": exit_price,
        "closed_ts": _now(),
        "close_reason": close_reason,
        "close_worker_id": worker_id,
        "pnl_amount": pnl_amount,
        "pnl_pips": round(pnl_pips, 2),
        "status": "closed",
        "guardian_status_at_close": guardian_msg,
    })
    state["open_trades"] = [t for t in state["open_trades"] if t.get("trade_id") != trade_id]
    state["closed_trades"].append(closed)
    state["actions"].append({
        "trade_id": trade_id,
        "action": "close_filled",
        "ts": _now(),
        "pnl_amount": pnl_amount,
    })
    _write_lifecycle_state(state)
    _append_jsonl(EVENTS_LOG, {"event": "close_filled", **closed})
    _append_jsonl(LEDGER_LOG, {"event": "close_filled", **closed})
    _emit_packets("close_filled", closed)
    return {"ok": True, "trade": closed}


def build_open_closed_pnl():
    state = _load_lifecycle_state()
    open_trades = state.get("open_trades") or []
    closed_trades = state.get("closed_trades") or []
    prices_doc = _load("qsb_floor41_oanda_prices_latest.json", {})
    prices = {p["instrument"]: p for p in (prices_doc.get("prices") or [])}

    # Mark open trades to compute uPnL.
    upnl_total = 0.0
    marked_open = []
    for t in open_trades:
        q = prices.get(t["instrument"])
        if q:
            # 2026-06-21 spread-bleed fix: unrealized mark same as open/close.
            if t.get("execution_mode") == "paper_simulator":
                exit_price = round((q["bid"] + q["ask"]) / 2.0, 6)
            else:
                exit_price = q["bid"] if t["direction"] == "buy" else q["ask"]
            sign = 1 if t["direction"] == "buy" else -1
            upnl = round(sign * (exit_price - t["entry_price"]) * t["units"], 4)
        else:
            exit_price = None
            upnl = 0.0
        upnl_total += upnl
        marked_open.append({**t, "mark_price": exit_price, "unrealized_pnl": upnl})

    realized_total = round(sum(float(c.get("pnl_amount") or 0) for c in closed_trades), 4)

    open_payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_open_trades",
        "phase": PHASE,
        "generated_ts": _now(),
        "trade_count": len(marked_open),
        "open_trades": marked_open,
        "unrealized_pnl_total": round(upnl_total, 4),
    }
    open_payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_open_trades.json", open_payload)

    closed_payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_closed_trades",
        "phase": PHASE,
        "generated_ts": _now(),
        "trade_count": len(closed_trades),
        "closed_trades": closed_trades,
        "realized_pnl_total": realized_total,
    }
    closed_payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_closed_trades.json", closed_payload)

    pnl_payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_pnl",
        "phase": PHASE,
        "generated_ts": _now(),
        "realized_pnl_total": realized_total,
        "unrealized_pnl_total": round(upnl_total, 4),
        "total_pnl": round(realized_total + upnl_total, 4),
        "closed_winners": sum(1 for c in closed_trades if (c.get("pnl_amount") or 0) > 0),
        "closed_losers": sum(1 for c in closed_trades if (c.get("pnl_amount") or 0) < 0),
        "closed_total": len(closed_trades),
        "open_total": len(marked_open),
    }
    pnl_payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_pnl.json", pnl_payload)
    return open_payload, closed_payload, pnl_payload


def build_trade_requests_actions_risk():
    state = _load_lifecycle_state()
    requests = state.get("requests") or []
    actions = state.get("actions") or []

    requests_payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_trade_requests",
        "phase": PHASE,
        "generated_ts": _now(),
        "request_count": len(requests),
        "requests": requests[-200:],
    }
    requests_payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_trade_requests.json", requests_payload)

    actions_payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_trade_actions",
        "phase": PHASE,
        "generated_ts": _now(),
        "action_count": len(actions),
        "actions": actions[-200:],
    }
    actions_payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_trade_actions.json", actions_payload)

    risk_payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_trade_risk_checks",
        "phase": PHASE,
        "generated_ts": _now(),
        "rules": [
            {"rule": "entry_reason_required", "blocking": True},
            {"rule": "close_reason_required", "blocking": True},
            {"rule": "guardian_state_in_OK_DEGRADED_DRIFTING", "blocking": True},
            {"rule": "no_live_environment_ever", "blocking": True},
            {"rule": "spread_pips_le_5.0", "blocking": True},
            {"rule": "units_in_1_to_50000", "blocking": True},
        ],
        "recent_blocks": [r for r in requests if r.get("risk_check_status") == "blocked"][-50:],
    }
    risk_payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_trade_risk_checks.json", risk_payload)
    return requests_payload, actions_payload, risk_payload


# ── Worker thoughts ──────────────────────────────────────────────────


def build_worker_thoughts():
    prices_doc = _load("qsb_floor41_oanda_prices_latest.json", {})
    state = _load_lifecycle_state()
    open_trades = state.get("open_trades", [])
    closed_trades = state.get("closed_trades", [])
    pnl = _load("qsb_floor41_oanda_pnl.json", {})

    thoughts = []
    ts = _now()

    # Spread observations
    for p in prices_doc.get("prices", []):
        inst = p.get("instrument")
        sp = p.get("spread_pips") or 0
        if sp > 3.0:
            thoughts.append({
                "worker_id": "f41_spread_watcher",
                "topic": "spread",
                "thought": "spread widened on {} to {:.1f} pips".format(inst, sp),
                "ts": ts,
                "source": "qsb_floor41_oanda_prices_latest.json",
            })
        elif sp <= 1.6:
            thoughts.append({
                "worker_id": "f41_market_scout",
                "topic": "observe",
                "thought": "{} stable at spread {:.1f} pips, observe only".format(inst, sp),
                "ts": ts,
                "source": "qsb_floor41_oanda_prices_latest.json",
            })

    # Open trade marks
    for t in open_trades:
        upnl = t.get("unrealized_pnl")
        if upnl is None:
            continue
        if upnl > 0:
            txt = "open trade {} on {} is in profit ({:+.4f} USD)".format(t["trade_id"], t["instrument"], upnl)
        elif upnl < 0:
            txt = "open trade {} on {} is in loss ({:+.4f} USD)".format(t["trade_id"], t["instrument"], upnl)
        else:
            txt = "open trade {} on {} is flat".format(t["trade_id"], t["instrument"])
        thoughts.append({
            "worker_id": "f41_pnl_accountant",
            "topic": "open_trade_mark",
            "thought": txt,
            "ts": ts,
            "source": "qsb_floor41_oanda_open_trades.json",
        })

    # Risk observation
    risk = _load("qsb_floor41_oanda_trade_risk_checks.json", {})
    if risk.get("recent_blocks"):
        thoughts.append({
            "worker_id": "f41_risk_sentinel",
            "topic": "risk",
            "thought": "risk recently blocked {} trade requests".format(len(risk["recent_blocks"])),
            "ts": ts,
            "source": "qsb_floor41_oanda_trade_risk_checks.json",
        })
    else:
        thoughts.append({
            "worker_id": "f41_risk_sentinel",
            "topic": "risk",
            "thought": "no risk blocks in recent window",
            "ts": ts,
            "source": "qsb_floor41_oanda_trade_risk_checks.json",
        })

    # PnL summary
    if pnl:
        thoughts.append({
            "worker_id": "f41_pnl_accountant",
            "topic": "pnl_summary",
            "thought": "realized {:+.4f} · unrealized {:+.4f} · total {:+.4f} (paper/practice)".format(
                pnl.get("realized_pnl_total", 0),
                pnl.get("unrealized_pnl_total", 0),
                pnl.get("total_pnl", 0),
            ),
            "ts": ts,
            "source": "qsb_floor41_oanda_pnl.json",
        })

    # Lessons from losing closed trades
    losers = [c for c in closed_trades if (c.get("pnl_amount") or 0) < 0]
    if losers:
        for c in losers[-3:]:
            thoughts.append({
                "worker_id": "f41_lessons_clerk",
                "topic": "lesson",
                "thought": "lesson from {} {} {}: pnl {:+.4f}, reason '{}'".format(
                    c.get("trade_id"), c.get("direction"), c.get("instrument"),
                    c.get("pnl_amount") or 0, c.get("close_reason") or "n/a"),
                "ts": ts,
                "source": "qsb_floor41_oanda_closed_trades.json",
            })

    # OpenClaw flag if data stale
    snap = _load("oanda_trading_floor_latest_snapshot.json", {})
    snap_ts = snap.get("snapshot_ts") or ""
    if _is_stale(snap_ts, hours=1):
        thoughts.append({
            "worker_id": "f41_openclaw_oanda_inspector",
            "topic": "data_freshness",
            "thought": "OpenClaw flagged stale OANDA snapshot ({})".format(snap_ts or "no_ts"),
            "ts": ts,
            "source": "oanda_trading_floor_latest_snapshot.json",
        })

    # Persist
    payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_worker_thoughts",
        "phase": PHASE,
        "generated_ts": ts,
        "thought_count": len(thoughts),
        "thoughts": thoughts,
        "paper_practice_label": "All thoughts paper/practice — not financial advice.",
    }
    payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_worker_thoughts.json", payload)
    for t in thoughts:
        _append_jsonl(THOUGHTS_LOG, t)
    return payload


def _is_stale(iso_ts, hours=1):
    if not iso_ts:
        return True
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt) > timedelta(hours=hours)
    except Exception:
        return True


# ── OpenClaw Floor 41 findings ───────────────────────────────────────


def build_openclaw_findings():
    findings = []
    tickets = []

    # Check practice mode only
    status = _load("oanda_trading_floor_status.json", {})
    if status.get("live_trading_enabled"):
        findings.append({"severity": "CRITICAL", "kind": "live_trading_enabled",
                         "detail": "live_trading_enabled flag is true — must be false"})
        tickets.append({"id": "oc_f41_001", "severity": "CRITICAL", "issue": "live_trading_enabled is true"})
    else:
        findings.append({"severity": "OK", "kind": "live_trading_off",
                         "detail": "live_trading_enabled=false (correct)"})

    # Tick data freshness
    snap = _load("oanda_trading_floor_latest_snapshot.json", {})
    if _is_stale(snap.get("snapshot_ts"), hours=1):
        findings.append({"severity": "WARN", "kind": "stale_snapshot",
                         "detail": "OANDA snapshot is older than 1h"})
        tickets.append({"id": "oc_f41_002", "severity": "WARN",
                        "issue": "OANDA snapshot stale — refresh required"})
    else:
        findings.append({"severity": "OK", "kind": "snapshot_fresh", "detail": "snapshot fresh"})

    # Spread sanity
    prices = _load("qsb_floor41_oanda_prices_latest.json", {})
    bad_spreads = [p for p in prices.get("prices", []) if (p.get("spread_pips") or 0) > 6.0]
    if bad_spreads:
        findings.append({"severity": "WARN", "kind": "wide_spread",
                         "detail": "{} instruments above 6 pips".format(len(bad_spreads))})
        tickets.append({"id": "oc_f41_003", "severity": "WARN",
                        "issue": "wide spread on " + ",".join(p["instrument"] for p in bad_spreads)})

    # Open trades count
    state = _load_lifecycle_state()
    open_count = len(state.get("open_trades", []))
    findings.append({"severity": "OK", "kind": "open_trades_count",
                     "detail": "open trades={}".format(open_count)})

    # Missing close reasons
    closed_missing_reason = [c for c in state.get("closed_trades", []) if not c.get("close_reason")]
    if closed_missing_reason:
        tickets.append({"id": "oc_f41_004", "severity": "HIGH",
                        "issue": "{} closed trades missing close_reason".format(len(closed_missing_reason))})

    # Missing entry reasons
    open_missing_reason = [t for t in state.get("open_trades", []) if not t.get("entry_reason")]
    if open_missing_reason:
        tickets.append({"id": "oc_f41_005", "severity": "HIGH",
                        "issue": "{} open trades missing entry_reason".format(len(open_missing_reason))})

    payload = {
        "ok": True,
        "kind": "qsb_openclaw_floor41_oanda_findings",
        "phase": PHASE,
        "generated_ts": _now(),
        "floor": 41,
        "finding_count": len(findings),
        "ticket_count": len(tickets),
        "findings": findings,
        "tickets": tickets,
        "recommended_fixes": _recommend_fixes(tickets),
        "supervisor_state": "active_local_only",
        "real_tool_execution_enabled": False,
    }
    payload.update(_safety())
    _write(REG / "qsb_openclaw_floor41_oanda_findings.json", payload)
    return payload


def _recommend_fixes(tickets):
    fixes = []
    for t in tickets:
        if "snapshot stale" in t.get("issue", ""):
            fixes.append("./scripts/qsb_floor41_oanda_refresh.sh")
        if "wide spread" in t.get("issue", ""):
            fixes.append("widen entry threshold or wait for normal spread")
        if "missing close_reason" in t.get("issue", ""):
            fixes.append("close trades only via close_paper_trade(reason=...)")
        if "missing entry_reason" in t.get("issue", ""):
            fixes.append("open trades only via open_paper_trade(entry_reason=...)")
        if "live_trading_enabled" in t.get("issue", ""):
            fixes.append("set live_trading_enabled=false in oanda_trading_floor_status.json")
    return sorted(set(fixes))


# ── Packets / movements / ledger ────────────────────────────────────


def _emit_packets(event, payload):
    """Append source-backed packets to qsb_floor41_oanda_packets_latest +
    update qsb_live_packets_latest + qsb_worker_movements_latest."""
    packets_doc = _load("qsb_floor41_oanda_packets_latest.json", {
        "ok": True, "packets": [], "packet_count": 0
    })
    pkts = packets_doc.get("packets") or []
    ts = _now()

    # Map event → worker chain
    chains = {
        "open_filled": [
            ("f41_order_entry_clerk", "Audit Dispatch"),
            ("f41_trade_ledger_clerk", "Audit Dispatch"),
            ("f41_pnl_accountant", "PnL Accounting Desk"),
            ("f41_risk_sentinel", "Risk / Guardian Station"),
            ("f41_openclaw_oanda_inspector", "OpenClaw Inspection Post"),
        ],
        "open_rejected": [
            ("f41_order_entry_clerk", "Risk / Guardian Station"),
            ("f41_risk_sentinel", "Risk / Guardian Station"),
            ("f41_openclaw_oanda_inspector", "OpenClaw Inspection Post"),
        ],
        "close_filled": [
            ("f41_close_trade_clerk", "PnL Accounting Desk"),
            ("f41_trade_ledger_clerk", "Audit Dispatch"),
        ],
    }
    chain = chains.get(event, [])

    # Lesson packet if losing close
    if event == "close_filled" and float(payload.get("pnl_amount") or 0) < 0:
        chain.append(("f41_lessons_clerk", "Lessons Output Desk"))

    for wid, dest in chain:
        pkt = {
            "packet_id": "pkt_f41_{}_{}_{}".format(event, wid, _stable_idx(str(payload) + wid + event, 1000000)),
            "kind": "floor41_oanda_packet",
            "event": event,
            "from_worker": wid,
            "to_room": dest,
            "trade_id": payload.get("trade_id"),
            "request_id": payload.get("request_id"),
            "instrument": payload.get("instrument"),
            "ts": ts,
            "source": "qsb_floor41_oanda.py",
        }
        pkts.append(pkt)
    # Cap retention
    pkts = pkts[-200:]
    packets_doc.update({
        "ok": True,
        "kind": "qsb_floor41_oanda_packets_latest",
        "phase": PHASE,
        "generated_ts": ts,
        "packet_count": len(pkts),
        "packets": pkts,
    })
    packets_doc.update(_safety())
    _write(REG / "qsb_floor41_oanda_packets_latest.json", packets_doc)

    # Mirror into qsb_live_packets_latest (append, capped)
    live = _load("qsb_live_packets_latest.json", {"packets": [], "packet_count": 0})
    live_pkts = live.get("packets") or []
    live_pkts.extend(pkts[-len(chain):] if chain else [])
    live_pkts = live_pkts[-200:]
    live.update({
        "ok": True,
        "kind": "qsb_live_packets_latest",
        "generated_ts": ts,
        "packet_count": len(live_pkts),
        "packets": live_pkts,
    })
    _write(REG / "qsb_live_packets_latest.json", live)

    # Mirror trade events as worker movements
    mv = _load("qsb_worker_movements_latest.json", {"movements": [], "movement_count": 0})
    mvs = mv.get("movements") or []
    for wid, dest in chain:
        mvs.append({
            "worker_id": wid,
            "from": "Order Entry Desk" if "order_entry" in wid else "station",
            "to": dest,
            "reason": event,
            "trade_id": payload.get("trade_id"),
            "ts": ts,
            "source": "qsb_floor41_oanda.py",
        })
    mvs = mvs[-200:]
    mv.update({
        "ok": True,
        "kind": "qsb_worker_movements_latest",
        "generated_ts": ts,
        "movement_count": len(mvs),
        "movements": mvs,
    })
    _write(REG / "qsb_worker_movements_latest.json", mv)


# ── Dashboard interior payload ───────────────────────────────────────


def build_dashboard_interior():
    """One consolidated payload the frontend Floor 41 panel polls."""
    payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_dashboard_interior",
        "phase": PHASE,
        "generated_ts": _now(),
        "floor": 41,
        "department": "OANDA Trading Floor",
        "engine_mode": _load("qsb_floor41_oanda_trading_engine.json", {}).get("mode"),
        "account": _load("qsb_floor41_oanda_account_snapshot.json", {}),
        "instruments": _load("qsb_floor41_oanda_instruments.json", {}).get("instruments", []),
        "prices": _load("qsb_floor41_oanda_prices_latest.json", {}).get("prices", []),
        "open_trades": _load("qsb_floor41_oanda_open_trades.json", {}).get("open_trades", []),
        "closed_trades": _load("qsb_floor41_oanda_closed_trades.json", {}).get("closed_trades", [])[-20:],
        "pnl": _load("qsb_floor41_oanda_pnl.json", {}),
        "thoughts": _load("qsb_floor41_oanda_worker_thoughts.json", {}).get("thoughts", []),
        "openclaw": _load("qsb_openclaw_floor41_oanda_findings.json", {}),
        "rooms": _load("qsb_floor41_oanda_department_map.json", {}).get("rooms", []),
        "workers": _load("qsb_floor41_oanda_workers.json", {}).get("workers", []),
        "risk_rules": _load("qsb_floor41_oanda_trade_risk_checks.json", {}).get("rules", []),
        "recent_actions": _load("qsb_floor41_oanda_trade_actions.json", {}).get("actions", [])[-20:],
        "packets": _load("qsb_floor41_oanda_packets_latest.json", {}).get("packets", [])[-20:],
        "paper_practice_label": "Paper/practice only — not financial advice.",
    }
    payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_dashboard_interior.json", payload)
    return payload


# ── Trading engine snapshot ──────────────────────────────────────────


def build_trading_engine_snapshot(mode, account, instruments, prices):
    payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_trading_engine",
        "phase": PHASE,
        "generated_ts": _now(),
        "mode": mode,
        "base_url": OANDA_PRACTICE_BASE if mode == "oanda_practice_api" else "local_paper_simulator",
        "credentials_present": _practice_creds_present(),
        "account_id": account.get("account_id"),
        "balance": account.get("balance"),
        "NAV": account.get("NAV"),
        "instrument_count": len(instruments.get("instruments", [])),
        "price_count": len(prices.get("prices", [])),
        "ready_for_open_paper_trade": True,
        "ready_for_close_paper_trade": True,
        "engine_modes_supported": ["oanda_practice_api", "paper_simulator", "disabled"],
        "live_money_enabled": False,
        "oanda_live_environment_allowed": False,
        "real_production_trading_allowed": False,
    }
    payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_trading_engine.json", payload)
    return payload


def build_floor_state():
    payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_state",
        "phase": PHASE,
        "generated_ts": _now(),
        "floor": 41,
        "department": "OANDA Trading Floor",
        "zone": "ZONE C",
        "status": "operational",
        "mode": _load("qsb_floor41_oanda_trading_engine.json", {}).get("mode"),
        "purpose": "Practice/paper FX trading, market observation, spread monitoring, trade lifecycle training, risk-controlled order opening/closing, PnL review, and lesson generation.",
        "rooms_count": len(ROOMS),
        "workers_count": len(WORKERS),
        "url": "http://127.0.0.1:8765/?v=unified&floor=41",
        # live_signals — read by the place-trade gate at line 604.
        # max_open_trades raised 3→24 per Ross 2026-06-19 so cohorts
        # of 6+ workers can each get their first trade in.
        "live_signals": {
            "max_open_trades": 24,
        },
    }
    payload.update(_safety())
    _write(REG / "qsb_floor41_oanda_state.json", payload)
    return payload


# ── Orchestrator ─────────────────────────────────────────────────────


def refresh_all():
    mode = engine_mode()
    department = build_department_map()
    workers = build_workers()
    account = build_account_snapshot(mode)
    instruments = build_instruments()
    prices = build_prices_and_ticks(mode)
    engine = build_trading_engine_snapshot(mode, account, instruments, prices)
    open_p, closed_p, pnl_p = build_open_closed_pnl()
    requests_p, actions_p, risk_p = build_trade_requests_actions_risk()
    thoughts = build_worker_thoughts()
    openclaw = build_openclaw_findings()
    interior = build_dashboard_interior()
    state = build_floor_state()
    summary = {
        "ok": True,
        "phase": PHASE,
        "generated_ts": _now(),
        "mode": mode,
        "department_rooms": department.get("room_count"),
        "workers": workers.get("worker_count"),
        "instrument_count": instruments.get("instrument_count"),
        "price_count": prices.get("price_count"),
        "open_trades": open_p.get("trade_count"),
        "closed_trades": closed_p.get("trade_count"),
        "realized_pnl_total": pnl_p.get("realized_pnl_total"),
        "unrealized_pnl_total": pnl_p.get("unrealized_pnl_total"),
        "total_pnl": pnl_p.get("total_pnl"),
        "thoughts": thoughts.get("thought_count"),
        "openclaw_findings": openclaw.get("finding_count"),
        "openclaw_tickets": openclaw.get("ticket_count"),
    }
    summary.update(_safety())
    _eqsb_record("floor41_oanda_refresh", summary)
    return summary


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "open":
        # open <instrument> <direction> <units> <entry_reason>
        result = open_paper_trade(
            sys.argv[2], sys.argv[3], sys.argv[4],
            sys.argv[5] if len(sys.argv) > 5 else "manual_open",
        )
        print(json.dumps(result, indent=2, default=str))
        refresh_all()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "close":
        # close <trade_id> <close_reason>
        result = close_paper_trade(
            sys.argv[2],
            sys.argv[3] if len(sys.argv) > 3 else "manual_close",
        )
        print(json.dumps(result, indent=2, default=str))
        refresh_all()
        return
    payload = refresh_all()
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
