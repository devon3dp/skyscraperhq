"""qsb_session_pnl_stop.py — daily P&L drawdown stop.

Per Ross Knechtel 2026-06-24 "yes make it all happen". Ship 1 of 3 missing pieces.

DeepSeek's math: a -£75 daily drawdown cap (1.5% of £5000 pot) would have cut today's
JPY -£36 bleed 52% earlier and prevented cascade revenge trades.

Architecture: lives as a thin file at data/registries/qsb_session_pnl_stop.json.
Updated by aggregator-hook OR cheap stat — checked by broker_place on every open.

API:
    from qsb_session_pnl_stop import session_pnl_check, session_pnl_state, set_daily_cap
    ok, reason = session_pnl_check()  # call in place_order before broker dispatch
    state = session_pnl_state()
    set_daily_cap(-75.0)  # cap defaults to -75; can override

State schema (data/registries/qsb_session_pnl_stop.json):
{
    "session_date": "2026-06-24",   # rolls midnight UTC
    "realized_pnl": -12.34,         # cumulative TODAY (REAL closes only)
    "daily_cap": -75.0,             # hard floor; new opens refused below this
    "tripped": false,               # once tripped, stays tripped this session
    "tripped_at": null,
    "total_closes": 23,
    "real_closes": 18,
    "updated_at": "..."
}
"""
from __future__ import annotations
import datetime
import fcntl
import json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_FILE = ROOT / "data/registries/qsb_session_pnl_stop.json"

DEFAULT_DAILY_CAP_GBP = -75.0


def _today_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _init_state() -> dict:
    return {
        "session_date": _today_utc(),
        "realized_pnl": 0.0,
        "daily_cap": DEFAULT_DAILY_CAP_GBP,
        "tripped": False,
        "tripped_at": None,
        "total_closes": 0,
        "real_closes": 0,
        "updated_at": _now_iso(),
    }


def _read_locked(fh) -> dict:
    fh.seek(0)
    body = fh.read()
    if not body:
        return _init_state()
    try:
        d = json.loads(body)
        if d.get("session_date") != _today_utc():
            # New UTC day — roll over (reset realized, untrip)
            d = _init_state()
        return d
    except json.JSONDecodeError:
        return _init_state()


def _write_locked(fh, state: dict) -> None:
    state["updated_at"] = _now_iso()
    fh.seek(0)
    fh.truncate()
    fh.write(json.dumps(state, indent=2))
    fh.flush()


def session_pnl_check() -> tuple[bool, str]:
    """Return (ok, reason). False if session is tripped on drawdown."""
    if not STATE_FILE.exists():
        return True, "session_clean_no_state_yet"
    try:
        with open(STATE_FILE) as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)
            try:
                state = json.loads(fh.read() or "{}") or {}
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception:
        return True, "state_unreadable"
    # Day-roll check
    if state.get("session_date") != _today_utc():
        return True, "new_session_day"
    if state.get("tripped"):
        return False, (f"session_pnl_stop_tripped "
                       f"realized={state.get('realized_pnl',0):.2f} "
                       f"cap={state.get('daily_cap',-75):.2f}")
    realized = state.get("realized_pnl", 0.0)
    cap = state.get("daily_cap", DEFAULT_DAILY_CAP_GBP)
    if realized <= cap:
        return False, (f"session_pnl_stop_breached "
                       f"realized={realized:.2f}<={cap:.2f}")
    return True, f"session_pnl_ok ({realized:+.2f}/{cap:.2f})"


def record_close(pnl: float, is_real: bool) -> dict:
    """Hook called on every trade.closed. Returns the new state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            state = _read_locked(fh)
            state["total_closes"] = state.get("total_closes", 0) + 1
            if is_real:
                state["real_closes"] = state.get("real_closes", 0) + 1
                state["realized_pnl"] = state.get("realized_pnl", 0.0) + float(pnl)
                if not state.get("tripped"):
                    cap = state.get("daily_cap", DEFAULT_DAILY_CAP_GBP)
                    if state["realized_pnl"] <= cap:
                        state["tripped"] = True
                        state["tripped_at"] = _now_iso()
            _write_locked(fh, state)
            return state
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def session_pnl_state() -> dict:
    if not STATE_FILE.exists():
        return _init_state()
    try:
        with open(STATE_FILE) as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)
            try:
                return json.loads(fh.read() or "{}") or _init_state()
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception:
        return _init_state()


def set_daily_cap(cap_gbp: float) -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            state = _read_locked(fh)
            state["daily_cap"] = float(cap_gbp)
            _write_locked(fh, state)
            return state
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def reset_session() -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as fh:
        s = _init_state()
        json.dump(s, fh, indent=2)
        return s


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    sub.add_parser("reset")
    sp = sub.add_parser("set-cap"); sp.add_argument("cap", type=float)
    sp = sub.add_parser("record"); sp.add_argument("pnl", type=float); sp.add_argument("--real", action="store_true")
    args = p.parse_args()
    if args.cmd == "show":
        s = session_pnl_state()
        ok, reason = session_pnl_check()
        print(f"date:        {s.get('session_date')}")
        print(f"realized:    {s.get('realized_pnl',0):+.2f}")
        print(f"cap:         {s.get('daily_cap',-75):.2f}")
        print(f"tripped:     {s.get('tripped',False)}  at={s.get('tripped_at')}")
        print(f"closes:      total={s.get('total_closes',0)} real={s.get('real_closes',0)}")
        print(f"check:       ok={ok} reason={reason}")
    elif args.cmd == "reset":
        reset_session()
        print("session reset")
    elif args.cmd == "set-cap":
        s = set_daily_cap(args.cap)
        print(f"cap set to {s['daily_cap']:.2f}")
    elif args.cmd == "record":
        s = record_close(args.pnl, args.real)
        print(f"recorded {args.pnl:+.2f} real={args.real}  new realized={s['realized_pnl']:+.2f} tripped={s['tripped']}")
