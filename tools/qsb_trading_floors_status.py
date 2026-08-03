#!/usr/bin/env python3
"""qsb_trading_floors_status.py — one HONEST unified status for the 3 trading floors.

Reads the per-floor registries that each trading floor already writes and folds
them into a single, TIMESTAMPED registry the dashboards / Underground map can
read without having to know each floor's private layout:

    data/registries/qsb_trading_floors_status.json

Floors covered:
    F41 · OANDA Trading Floor   (forex, PRACTICE account — the live exception)
    F42 · Binance Trading Floor (crypto, TESTNET / preview-only)
    F43 · Stock Exchange Floor  (Alpaca PAPER — preview-only, placement blocked)

HONESTY (R01): this tool INVENTS NOTHING. Every number is copied verbatim from
a source registry, and each floor carries:
    - source_file + source_ts (what it read, when that source was written)
    - fresh: bool + stale_secs (this tool computes staleness itself, so a
      7-week-old source surfaces as fresh=false instead of silently lying)
Positions / PnL only appear when the source registry actually carries them.

READ-ONLY. Places no orders. Flips no gates. Touches no SAFETY_DENY path
(it reads only the public per-floor status registries, never the vault/.env).

Usage:
    python3 tools/qsb_trading_floors_status.py            # write + print summary
    python3 tools/qsb_trading_floors_status.py --quiet    # write, minimal stdout
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
OUT = REG / "qsb_trading_floors_status.json"

# A source is considered "fresh" if written within this many seconds of now.
# OANDA refreshes every 30s, F43 every 120s, F42 refresher every 120s — 600s
# gives generous headroom while still flagging genuinely stale (Jun/Jul-old) files.
FRESH_WINDOW_SECS = 600
# Tick streams append continuously; flag as live only if touched in the last 5 min.
TICK_FRESH_SECS = 300


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat().replace("+00:00", "Z")


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def parse_ts(val) -> datetime.datetime | None:
    if not val or not isinstance(val, str):
        return None
    s = val.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        return None


def staleness(ts_val) -> tuple[bool, float | None]:
    dt = parse_ts(ts_val)
    if dt is None:
        return False, None
    secs = (now_utc() - dt).total_seconds()
    return (secs <= FRESH_WINDOW_SECS), round(secs, 1)


def tick_stream_state(fname: str) -> dict:
    p = REG / fname
    if not p.exists():
        return {"present": False, "live": False, "mtime": None, "age_secs": None}
    mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime, datetime.timezone.utc)
    age = (now_utc() - mtime).total_seconds()
    return {
        "present": True,
        "live": age <= TICK_FRESH_SECS,
        "mtime": mtime.isoformat().replace("+00:00", "Z"),
        "age_secs": round(age, 1),
        "file": fname,
    }


def floor_f41() -> dict:
    """OANDA — the honest live surface is qsb_oanda_live.json (refreshed 30s)."""
    live = load_json(REG / "qsb_oanda_live.json") or {}
    src_ts = live.get("ts")
    fresh, stale = staleness(src_ts)
    connected = bool(live.get("ok")) and fresh
    tick = tick_stream_state("qsb_oanda_tick_stream.jsonl")
    return {
        "floor": "floor_41",
        "name": "OANDA Trading Floor",
        "asset_class": "forex",
        "provider": "oanda",
        "environment": "practice",
        "live_exception": True,  # the one CLAUDE.md-authorised live venue (practice)
        "connected": connected,
        "market_open": True if tick.get("live") else None,  # FX 24/5; live ticks => open
        "open_trades": live.get("open_trades"),
        "open_positions": live.get("open_positions"),
        "realized_pl_today": live.get("realized_pl_today"),
        "unrealized_pl": live.get("unrealized_pl"),
        "balance": live.get("balance"),
        "nav": live.get("NAV"),
        "currency": live.get("currency"),
        "instrument_count": None,  # OANDA offers many; not enumerated in live snap
        "tick_stream": tick,
        "source_file": "qsb_oanda_live.json",
        "source_ts": src_ts,
        "source_fresh": fresh,
        "source_stale_secs": stale,
        "order_placement_enabled": False,  # practice orders only via F41 guardrails, never here
        "note": (
            "OANDA PRACTICE account — realized/unrealized PnL and open trades are "
            "real broker reads. Legacy F41 registries (qsb_floor41_oanda_pnl.json, "
            "qsb_floor41_oanda_open_trades.json, oanda_trading_floor_status.json, "
            "qsb_floor41_oanda_account_snapshot.json) are STALE placeholders — use "
            "qsb_oanda_live.json, refreshed every 30s by qsb-oanda-live.timer."
        ),
    }


def floor_f42() -> dict:
    """Binance — honest public status from binance_floor_status.json + tick stream."""
    st = load_json(REG / "binance_floor_status.json") or {}
    src_ts = st.get("status_ts")
    fresh, stale = staleness(src_ts)
    tick = tick_stream_state("qsb_binance_tick_stream.jsonl")
    symbols = st.get("default_symbols") or []
    acct_ok = bool(st.get("account_read_ready"))
    return {
        "floor": "floor_42",
        "name": "Binance Trading Floor",
        "asset_class": "crypto",
        "provider": "binance",
        "environment": "testnet",
        "live_exception": False,
        # "connected" for F42 means public market data is flowing (ticks live).
        # Testnet account read requires vault creds and is reported separately.
        "connected": bool(tick.get("live")),
        "market_open": True if tick.get("live") else None,  # crypto 24/7
        "public_market_data_ready": st.get("public_market_data_ready"),
        "account_read_ready": acct_ok,
        "open_trades": None,   # testnet preview-only; no live account positions surfaced
        "open_positions": None,
        "realized_pl_today": None,
        "unrealized_pl": None,
        "instrument_count": len(symbols),
        "instruments": symbols,
        "tick_stream": tick,
        "source_file": "binance_floor_status.json",
        "source_ts": src_ts,
        "source_fresh": fresh,
        "source_stale_secs": stale,
        "order_placement_enabled": False,  # testnet preview-only; placement blocked
        "note": (
            "Binance TESTNET, preview-only — order placement blocked regardless of "
            "gate. Public trade stream is LIVE (qsb_binance_tick_stream.jsonl) so "
            "market data is real-time; testnet account read requires F28 vault creds "
            "and is not surfaced here. No open-position/PnL numbers are claimed."
        ),
    }


def floor_f43() -> dict:
    """Stocks — honest status from stock_floor_status.json (refreshed 120s)."""
    st = load_json(REG / "stock_floor_status.json") or {}
    src_ts = st.get("status_ts")
    fresh, stale = staleness(src_ts)
    acct = st.get("account_read_detail") or {}
    mkt = st.get("market_status")
    symbols = st.get("default_symbols") or []
    acct_ready = bool(st.get("account_read_ready"))
    mkt_data_ready = bool(st.get("public_market_data_ready"))
    return {
        "floor": "floor_43",
        "name": "Stock Exchange Trading Floor",
        "asset_class": "equities",
        "provider": "alpaca",
        "environment": "paper",
        "live_exception": False,
        # Connected = the floor is reachable this cycle: a fresh refresh with
        # EITHER a good account read OR good public market data. A single flaky
        # /v2/account poll must not flip the floor to "disconnected" while quotes
        # are still flowing. account_read_ready is surfaced separately below.
        "connected": (acct_ready or mkt_data_ready) and fresh,
        "account_read_ready": acct_ready,
        "public_market_data_ready": mkt_data_ready,
        "market_open": (mkt == "open") if mkt else None,
        "market_status": mkt,
        "market_next_open": (st.get("market_status_detail") or {}).get("next_open"),
        "market_next_close": (st.get("market_status_detail") or {}).get("next_close"),
        "account_status": acct.get("status"),
        "trading_blocked": acct.get("trading_blocked"),
        "open_trades": None,   # no live positions registry surfaced by F43 status
        "open_positions": None,
        "realized_pl_today": None,
        "unrealized_pl": None,
        "instrument_count": len(symbols),
        "instruments": symbols,
        "source_file": "stock_floor_status.json",
        "source_ts": src_ts,
        "source_fresh": fresh,
        "source_stale_secs": stale,
        "order_placement_enabled": False,  # Alpaca paper preview-only; placement blocked
        "note": (
            "Alpaca PAPER, preview-only — real /v2/account + /v2/clock reads, order "
            "placement blocked. Market is "
            + (str(mkt).upper() if mkt else "UNKNOWN")
            + "; refreshed every 120s by qsb-floor43-stocks.timer."
        ),
    }


def build() -> dict:
    floors = [floor_f41(), floor_f42(), floor_f43()]
    connected = sum(1 for f in floors if f.get("connected"))
    return {
        "kind": "qsb_trading_floors_status",
        "ts": now_iso(),
        "generated_by": "tools/qsb_trading_floors_status.py",
        "read_only": True,
        "any_order_placement_enabled": False,
        "floors_total": len(floors),
        "floors_connected": connected,
        "summary": {
            f["floor"]: {
                "name": f["name"],
                "connected": f["connected"],
                "market_open": f.get("market_open"),
                "source_fresh": f.get("source_fresh"),
            }
            for f in floors
        },
        "floors": floors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    data = build()
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")

    if not args.quiet:
        print(f"wrote {OUT} @ {data['ts']}")
        for f in data["floors"]:
            bits = [
                f"connected={f['connected']}",
                f"mkt_open={f.get('market_open')}",
                f"fresh={f.get('source_fresh')}({f.get('source_stale_secs')}s)",
            ]
            if f.get("open_trades") is not None:
                bits.append(f"open_trades={f['open_trades']}")
            if f.get("realized_pl_today") is not None:
                bits.append(f"realized_today={f['realized_pl_today']}{f.get('currency','')}")
            print(f"  {f['floor']} {f['name']}: " + " ".join(bits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
