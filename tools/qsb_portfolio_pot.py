"""qsb_portfolio_pot.py — fleet-wide £5000 net pot.

Per Ross Knechtel 2026-06-24: "we only start with 5000 pounds for everything".
Every OPEN order across every venue reserves notional from a shared pot.
Closes release. If a new OPEN would push committed > cap_gbp, place_order refuses.

State persists in JSON under file lock so it survives trader respawns.

API:
    from qsb_portfolio_pot import try_reserve, release, snapshot
    ok, reason, notional_gbp = try_reserve(venue, instrument, qty, price,
                                            order_id, worker_id)
    release(order_id)
    snap = snapshot()  # {cap_gbp, committed_gbp, by_venue, open_positions, ...}
"""
from __future__ import annotations
import fcntl
import json
import time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
POT_FILE = ROOT / "data/registries/qsb_portfolio_pot.json"

DEFAULT_CAP_GBP = 5000.0

# Currency conversion to GBP. Updated when streams provide better data; OK static for now.
FX_TO_GBP = {
    "GBP": 1.0,
    "USD": 0.80,
    "USDT": 0.80,
    "USDC": 0.80,
    "EUR": 0.85,
    "JPY": 0.0053,
    "CHF": 0.90,
    "AUD": 0.52,
    "CAD": 0.59,
}

# Quote-currency for each instrument we trade. Notional = qty × price × FX_TO_GBP[quote].
QUOTE_CCY = {
    # OANDA pairs — quote is RHS of underscore
    "EUR_USD": "USD", "GBP_USD": "USD", "USD_JPY": "JPY",
    "AUD_USD": "USD", "USD_CHF": "CHF", "EUR_GBP": "GBP",
    "XAU_USD": "USD", "XAG_USD": "USD", "WTICO_USD": "USD", "BCO_USD": "USD",
    "SPX500_USD": "USD", "NAS100_USD": "USD", "US30_USD": "USD",
    "NATGAS_USD": "USD", "DE30_EUR": "EUR", "JP225_USD": "USD",
    "USB10Y_USD": "USD", "UK10YB_GBP": "GBP", "XCU_USD": "USD", "WHEAT_USD": "USD",
    # Binance — quote is rightmost (USDT)
    "BTCUSDT": "USDT", "ETHUSDT": "USDT", "BNBUSDT": "USDT", "SOLUSDT": "USDT",
    "ADAUSDT": "USDT", "XRPUSDT": "USDT", "DOTUSDT": "USDT", "AVAXUSDT": "USDT",
    "LINKUSDT": "USDT",
    # Alpaca — all USD-quoted
    "SPY": "USD", "AAPL": "USD", "QQQ": "USD", "TSLA": "USD", "NVDA": "USD",
    "MSFT": "USD", "DIA": "USD", "XLF": "USD", "GLD": "USD", "COIN": "USD",
    "IWM": "USD",
}


def _init_state() -> dict:
    return {
        "cap_gbp": DEFAULT_CAP_GBP,
        "committed_gbp": 0.0,
        "by_venue": {"oanda_practice": 0.0, "alpaca_paper": 0.0, "binance_testnet": 0.0},
        "open_positions": {},
        "fx_to_gbp": FX_TO_GBP,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "refused_count": 0,
        "reserved_count": 0,
        "released_count": 0,
    }


def _read_locked(fh) -> dict:
    fh.seek(0)
    body = fh.read()
    if not body:
        return _init_state()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return _init_state()


def _write_locked(fh, state: dict) -> None:
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fh.seek(0)
    fh.truncate()
    fh.write(json.dumps(state, indent=2))
    fh.flush()


def _notional_gbp(instrument: str, qty: float, price: float) -> float:
    quote = QUOTE_CCY.get(instrument, "USD")
    rate = FX_TO_GBP.get(quote, 0.80)
    return abs(qty * price * rate)


def try_reserve(venue: str, instrument: str, qty: float, price: float,
                order_id: str, worker_id: str) -> tuple[bool, str, float]:
    """Reserve notional. Returns (ok, reason, notional_gbp).

    If pot would exceed cap_gbp, returns (False, "pot_full ...", 0).
    Also checks per-currency exposure cap (correlation-aware sizing).
    Idempotent on order_id — same order_id reserved twice is a no-op.
    """
    notional_gbp = _notional_gbp(instrument, qty, price)
    # Currency-correlation cap check (Ross 2026-06-24 ship-2). Before pot file IO.
    try:
        from qsb_correlation_groups import check_currency_exposure
        result = check_currency_exposure(instrument, notional_gbp)
        if len(result) == 3:
            ok_ccy, clamped_notional, ccy_reason = result
            if not ok_ccy:
                return False, ccy_reason, notional_gbp
            notional_gbp = clamped_notional  # use the clamped amount
        else:
            ok_ccy, ccy_reason = result
            if not ok_ccy:
                return False, ccy_reason, notional_gbp
    except Exception:
        pass  # tool absent → no correlation cap (backwards compat)
    POT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(POT_FILE, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            state = _read_locked(fh)
            # Idempotent — already reserved
            if order_id in state["open_positions"]:
                return True, "already_reserved", state["open_positions"][order_id]["notional_gbp"]
            cap = state.get("cap_gbp", DEFAULT_CAP_GBP)
            committed = state.get("committed_gbp", 0.0)
            if committed + notional_gbp > cap:
                state["refused_count"] = state.get("refused_count", 0) + 1
                _write_locked(fh, state)
                return False, (f"pot_full ({committed:.2f}+{notional_gbp:.2f}>{cap:.2f} GBP, "
                              f"{state['refused_count']} refused total)"), notional_gbp
            state["committed_gbp"] = committed + notional_gbp
            state["by_venue"][venue] = state["by_venue"].get(venue, 0.0) + notional_gbp
            state["open_positions"][order_id] = {
                "venue": venue, "instrument": instrument, "qty": qty, "price": price,
                "notional_gbp": notional_gbp, "worker_id": worker_id,
                "opened_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            state["reserved_count"] = state.get("reserved_count", 0) + 1
            _write_locked(fh, state)
            return True, "reserved", notional_gbp
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def release(order_id: str) -> tuple[bool, float]:
    """Release reserved notional. Returns (found, released_gbp)."""
    if not POT_FILE.exists():
        return False, 0.0
    with open(POT_FILE, "r+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            state = _read_locked(fh)
            pos = state["open_positions"].pop(order_id, None)
            if not pos:
                return False, 0.0
            notional = pos["notional_gbp"]
            state["committed_gbp"] = max(0.0, state.get("committed_gbp", 0.0) - notional)
            venue = pos["venue"]
            state["by_venue"][venue] = max(0.0, state["by_venue"].get(venue, 0.0) - notional)
            state["released_count"] = state.get("released_count", 0) + 1
            _write_locked(fh, state)
            return True, notional
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def snapshot() -> dict:
    """Read-only snapshot of pot state."""
    if not POT_FILE.exists():
        return _init_state()
    try:
        with open(POT_FILE) as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)
            try:
                return json.loads(fh.read() or "{}") or _init_state()
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception:
        return _init_state()


def set_cap(cap_gbp: float) -> dict:
    """Change the cap. Used by ops / dashboard / CLI."""
    POT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(POT_FILE, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            state = _read_locked(fh)
            state["cap_gbp"] = float(cap_gbp)
            _write_locked(fh, state)
            return state
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    sub.add_parser("init")
    sp = sub.add_parser("set-cap"); sp.add_argument("cap", type=float)
    sp = sub.add_parser("release"); sp.add_argument("order_id")
    args = p.parse_args()
    if args.cmd == "show":
        s = snapshot()
        print(f"cap_gbp:       {s['cap_gbp']:.2f}")
        print(f"committed:     {s['committed_gbp']:.2f}")
        print(f"remaining:     {s['cap_gbp'] - s['committed_gbp']:.2f}")
        print(f"open positions: {len(s['open_positions'])}")
        print(f"by venue:")
        for v, n in s["by_venue"].items():
            print(f"  {v}: {n:.2f}")
        print(f"counters: reserved={s.get('reserved_count',0)} released={s.get('released_count',0)} refused={s.get('refused_count',0)}")
    elif args.cmd == "init":
        POT_FILE.unlink(missing_ok=True)
        with open(POT_FILE, "w") as fh:
            json.dump(_init_state(), fh, indent=2)
        print(f"initialized {POT_FILE}")
    elif args.cmd == "set-cap":
        s = set_cap(args.cap)
        print(f"cap set to {s['cap_gbp']:.2f}")
    elif args.cmd == "release":
        ok, n = release(args.order_id)
        print(f"release {args.order_id}: ok={ok} freed={n:.2f}")
