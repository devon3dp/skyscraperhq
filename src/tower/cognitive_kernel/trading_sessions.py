"""Trading sessions — world-clock awareness for the finance floors.

Sessions are defined in **local hours of the relevant city** then
converted to UTC daily, since each city's DST rules differ. We compute
on-the-fly from UTC `now` to avoid stale state.

Sessions (FX market consensus):
  · Sydney     22:00 - 07:00 local (≈ UTC 12:00-21:00 in DST)
  · Tokyo      09:00 - 18:00 local (UTC 00:00-09:00)
  · London     08:00 - 16:00 local (UTC 07:00-15:00 in BST)
  · New York   08:00 - 17:00 local (UTC 13:00-22:00 in EDT)

Overlap windows are where volatility (and worker opportunity) peaks:
  · Tokyo / London   ≈ UTC 07:00-09:00
  · London / NY      ≈ UTC 13:00-15:00  ← strongest for FX majors
  · Sydney / Tokyo   ≈ UTC 00:00-06:00

Other markets:
  · NYSE / Nasdaq    14:30 - 21:00 UTC (DST), 09:30-16:00 ET
  · LSE              08:00 - 16:30 London
  · Binance crypto   24/7

Per-instrument liquidity profile decides whether a session is "best" or
"acceptable" or "thin" for a given symbol.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import time

from . import write_registry, append_log, now


# Session UTC windows. These approximate DST-blended hours; we will
# recompute precisely with zoneinfo in a future upgrade. Format:
# (start_utc_hour, end_utc_hour) on a 24-hour clock; if start>end the
# session crosses midnight.
SESSIONS: List[Dict[str, Any]] = [
    {"name": "sydney",  "city": "Sydney",   "tz": "Australia/Sydney",
     "fx_session": True, "stock_market_session": False,
     "utc_open_hour": 22, "utc_close_hour": 7,
     "best_for": ["AUD_USD", "AUD_NZD", "NZD_USD"]},
    {"name": "tokyo",   "city": "Tokyo",    "tz": "Asia/Tokyo",
     "fx_session": True, "stock_market_session": False,
     "utc_open_hour": 0, "utc_close_hour": 9,
     "best_for": ["USD_JPY", "EUR_JPY", "AUD_JPY", "GBP_JPY"]},
    {"name": "london",  "city": "London",   "tz": "Europe/London",
     "fx_session": True, "stock_market_session": False,
     "utc_open_hour": 7, "utc_close_hour": 16,
     "best_for": ["EUR_USD", "GBP_USD", "EUR_GBP", "USD_CHF"]},
    {"name": "new_york","city": "New York", "tz": "America/New_York",
     "fx_session": True, "stock_market_session": False,
     "utc_open_hour": 13, "utc_close_hour": 22,
     "best_for": ["EUR_USD", "GBP_USD", "USD_CAD", "USD_JPY"]},
    {"name": "nyse",    "city": "New York", "tz": "America/New_York",
     "fx_session": False, "stock_market_session": True,
     "utc_open_hour": 14, "utc_close_hour": 21,
     "best_for": ["US_STOCKS"]},
    {"name": "lse",     "city": "London",   "tz": "Europe/London",
     "fx_session": False, "stock_market_session": True,
     "utc_open_hour": 8, "utc_close_hour": 16,
     "best_for": ["UK_STOCKS"]},
    {"name": "binance_crypto", "city": "Global", "tz": "UTC",
     "fx_session": False, "stock_market_session": False,
     "utc_open_hour": 0, "utc_close_hour": 24,         # 24/7
     "best_for": ["BTC_USDT", "ETH_USDT", "BNB_USDT", "SOL_USDT"]},
]


OVERLAPS: List[Dict[str, Any]] = [
    {"name": "sydney_tokyo",
     "utc_open_hour": 0, "utc_close_hour": 6,
     "intensity": 0.55,
     "note": "Asia-Pacific FX flows; thin majors, active crosses."},
    {"name": "tokyo_london",
     "utc_open_hour": 7, "utc_close_hour": 9,
     "intensity": 0.70,
     "note": "Early-London volatility, Asian-session unwinds."},
    {"name": "london_new_york",
     "utc_open_hour": 13, "utc_close_hour": 16,
     "intensity": 0.95,
     "note": "Peak liquidity for FX majors. Best window for scalp/swing."},
]


def _hour_in_window(hour: int, open_h: int, close_h: int) -> bool:
    if open_h == 0 and close_h == 24:
        return True
    if open_h < close_h:
        return open_h <= hour < close_h
    # Crosses midnight (e.g., Sydney 22 → 7)
    return hour >= open_h or hour < close_h


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def session_status_for(utc_hour: int) -> Dict[str, Any]:
    open_sessions = []
    for s in SESSIONS:
        if _hour_in_window(utc_hour, s["utc_open_hour"], s["utc_close_hour"]):
            open_sessions.append(s["name"])
    active_overlaps = []
    for o in OVERLAPS:
        if _hour_in_window(utc_hour, o["utc_open_hour"], o["utc_close_hour"]):
            active_overlaps.append(o["name"])
    # Trade-time-of-day classification
    if any(o for o in OVERLAPS
            if o["name"] == "london_new_york"
            and _hour_in_window(utc_hour, o["utc_open_hour"], o["utc_close_hour"])):
        regime = "peak_liquidity"
    elif "london" in open_sessions and "new_york" not in open_sessions:
        regime = "london_only"
    elif "new_york" in open_sessions and "london" not in open_sessions:
        regime = "ny_only"
    elif "tokyo" in open_sessions or "sydney" in open_sessions:
        regime = "asia_pacific"
    else:
        regime = "low_liquidity"
    return {
        "utc_hour": utc_hour,
        "open_sessions": open_sessions,
        "active_overlaps": active_overlaps,
        "regime": regime,
    }


def advise_instrument_now(instrument: str) -> Dict[str, Any]:
    """Is *now* a good time to trade `instrument`? Return a structured
    advisory used by the cognitive Reasoning layer."""
    h = now_utc().hour
    status = session_status_for(h)
    relevant_sessions = [s for s in SESSIONS
                          if instrument in s.get("best_for", [])
                          and s["name"] in status["open_sessions"]]
    advice = "thin"
    if status["regime"] == "peak_liquidity" and any(
            instrument in s.get("best_for", []) for s in SESSIONS
            if s["name"] in ("london", "new_york")):
        advice = "peak"
    elif relevant_sessions:
        advice = "acceptable"
    return {
        "instrument": instrument,
        "advice": advice,
        "open_sessions": status["open_sessions"],
        "active_overlaps": status["active_overlaps"],
        "regime": status["regime"],
        "rationale": (
            f"At UTC hour {h}, regime={status['regime']}, "
            f"open={status['open_sessions']}, "
            f"overlaps={status['active_overlaps']}. "
            f"Instrument's preferred sessions open right now: "
            f"{[s['name'] for s in relevant_sessions] or '(none)'}."
        ),
    }


def snapshot() -> Dict[str, Any]:
    nu = now_utc()
    status = session_status_for(nu.hour)
    # Pre-compute advice for the OANDA-whitelisted + a few crypto symbols
    advised = [advise_instrument_now(sym)
               for sym in ("EUR_USD", "GBP_USD", "USD_JPY",
                           "AUD_USD", "EUR_GBP",
                           "BTC_USDT", "ETH_USDT")]
    return {
        "ok": True,
        "kind": "cognitive_trading_sessions",
        "generated_ts": now(),
        "utc_now": nu.isoformat(),
        "utc_hour": nu.hour,
        "open_sessions": status["open_sessions"],
        "active_overlaps": status["active_overlaps"],
        "regime": status["regime"],
        "sessions": SESSIONS,
        "overlaps": OVERLAPS,
        "instrument_advice": advised,
        "policy": (
            "Time-zone-aware trading session advisor. The Reasoning "
            "layer can read this to refuse trade proposals during "
            "low-liquidity hours unless the operator overrides."
        ),
    }


def persist() -> Dict[str, Any]:
    snap = snapshot()
    write_registry("cognitive_trading_sessions.json", snap)
    append_log("trading_sessions.jsonl", {
        "event": "snapshot",
        "regime": snap["regime"],
        "open_sessions": snap["open_sessions"],
    })
    return snap
