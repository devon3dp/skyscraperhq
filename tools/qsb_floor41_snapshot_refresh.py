#!/usr/bin/env python3
"""
qsb_floor41_snapshot_refresh.py

Keeps the F41 OANDA dashboard registries HONEST by mirroring the live poller
output (qsb_oanda_live.json, written every 30s by qsb_oanda_live_snapshot.py)
into the two files the dashboard actually serves:
  - qsb_floor41_oanda_account_snapshot.json  (/api/trading/oanda/floor41/account)
  - qsb_floor41_oanda_pnl.json               (/api/trading/oanda/floor41/pnl)

Without this, those two files were 7-week-stale build snapshots claiming a false
balance (100057.30 / 0 open trades / 0 PnL) while the account was really at
~104055 GBP with open trades. This ONLY copies read-only live values; it never
touches any execution/live-money gate field (those are preserved verbatim).

Idempotent one-shot. Wire as ExecStartPost on qsb-oanda-live.service.
"""
import json, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "registries"
LIVE = REG / "qsb_oanda_live.json"
SUMM = REG / "qsb_oanda_history_summary.json"
SNAP = REG / "qsb_floor41_oanda_account_snapshot.json"
PNL = REG / "qsb_floor41_oanda_pnl.json"


def load(p, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:
        return {} if default is None else default


def main():
    live = load(LIVE)
    if not live or "balance" not in live:
        return  # no live data yet; leave files untouched
    summ = load(SUMM)
    iso = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- account snapshot (preserve all gate fields verbatim) ---
    snap = load(SNAP)
    snap.update({
        "generated_ts": iso,
        "refreshed_by": "qsb_floor41_snapshot_refresh (ExecStartPost of qsb-oanda-live)",
        "source": "qsb_oanda_live.json (live OANDA practice poller)",
        "live_source_ts": live.get("ts"),
        "currency": live.get("currency", snap.get("currency")),
        "balance": live.get("balance"),
        "NAV": live.get("NAV"),
        "margin_used": live.get("margin_used"),
        "margin_available": live.get("margin_available"),
        "unrealized_PL": live.get("unrealized_pl"),
        "realized_pl_today": live.get("realized_pl_today"),
        "open_trade_count": live.get("open_trades"),
        "open_position_count": live.get("open_positions"),
        "lifetime_realized_pl_gbp": summ.get("grand_pl_gbp"),
        "lifetime_fills": summ.get("fills_with_pl"),
    })
    SNAP.write_text(json.dumps(snap, indent=2))

    # --- pnl ---
    pnl = load(PNL)
    pnl.update({
        "generated_ts": iso,
        "refreshed_by": "qsb_floor41_snapshot_refresh",
        "realized_pnl_today": live.get("realized_pl_today"),
        "unrealized_pnl_total": live.get("unrealized_pl"),
        "lifetime_realized_pnl_gbp": summ.get("grand_pl_gbp"),
        "lifetime_fills": summ.get("fills_with_pl"),
        "open_total": live.get("open_trades"),
        "live_source": "qsb_oanda_live.json + qsb_oanda_history_summary.json",
    })
    PNL.write_text(json.dumps(pnl, indent=2))


if __name__ == "__main__":
    main()
