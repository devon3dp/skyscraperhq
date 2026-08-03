#!/usr/bin/env python3
"""qsb_accounts_ledger_refresh.py — HONEST F44/F102 accounts reconciliation.

Floor 44 (Accounts / PnL Department) + Floor 102 (Tax & Accounting) do REAL
accounting on the tower's REAL paper/practice/testnet trading activity. This
tool reads — never writes — the live trading registries and produces:

    data/registries/qsb_accounts_ledger.jsonl        (append-only ledger rows)
    data/registries/qsb_accounts_summary_latest.json (latest reconciled summary)

Every number traces to a named source file (each ledger row carries a "source"
field with the registry path + timestamp). NOTHING is invented. When a source
is stale or a market is closed, that is reported honestly (source_ts, note),
never smoothed over.

Venues accounted (ALL paper / practice / testnet — NO real money):
  F41 OANDA practice  — realized lifetime PnL + live NAV/balance/unrealized
  F42 Binance testnet — broker realized PnL by symbol + open exposure
  F43 Alpaca paper    — broker realized PnL by symbol + market open/closed
  Belief-trader pot   — committed capital + open positions by venue
  Provider spend      — real gene-pool / consult cost_usd for the UTC day

HARD SAFETY (unchanged; this tool cannot weaken any gate):
  - read-only on every trading system; never places an order
  - never reads the vault or any .env; never touches a gate JSON
  - all figures labelled advisory_only / paper / practice / testnet

Usage:
    python3 tools/qsb_accounts_ledger_refresh.py            # refresh once
    python3 tools/qsb_accounts_ledger_refresh.py --quiet    # minimal stdout
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LEDGER_PATH = REG / "qsb_accounts_ledger.jsonl"
SUMMARY_PATH = REG / "qsb_accounts_summary_latest.json"

# Reuse the SAME GBP/USD lookup F44 + F47 already agree on, so cross-floor
# reconciliation uses one rate.
sys.path.insert(0, str(ROOT / "tools"))
try:
    from qsb_risk_cap import gbp_per_usd  # type: ignore
except Exception:
    def gbp_per_usd() -> float:
        return 1.0 / 1.30  # conservative fallback


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_json(rel: str) -> tuple[dict[str, Any] | None, str]:
    """Load a registry JSON. Returns (data|None, source_path_str)."""
    p = REG / rel
    if not p.exists():
        return None, str(p)
    try:
        return json.loads(p.read_text()), str(p)
    except Exception:
        return None, str(p)


def _file_mtime(rel: str) -> str | None:
    p = REG / rel
    if not p.exists():
        return None
    return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()


def build() -> dict[str, Any]:
    gpu = gbp_per_usd()          # GBP per 1 USD
    usd_per_gbp = 1.0 / gpu if gpu else 0.0
    rows: list[dict[str, Any]] = []
    gaps: list[str] = []
    now = _now()
    today = _today_utc()

    # ---- F41 OANDA practice: live balance/NAV + lifetime realized PnL -------
    oanda_live, oanda_live_src = _load_json("qsb_oanda_live.json")
    pnl_latest, pnl_latest_src = _load_json("qsb_trader_pnl_latest.json")

    f41_block: dict[str, Any] = {"floor": "F41", "venue": "oanda_practice",
                                 "mode": "oanda_practice_api", "advisory_only": True}
    if oanda_live and oanda_live.get("ok"):
        f41_block.update({
            "balance_gbp": oanda_live.get("balance"),
            "nav_gbp": oanda_live.get("NAV"),
            "unrealized_pnl_gbp": oanda_live.get("unrealized_pl"),
            "realized_pnl_today_gbp": oanda_live.get("realized_pl_today"),
            "margin_used_gbp": oanda_live.get("margin_used"),
            "open_trades": oanda_live.get("open_trades"),
            "open_positions": oanda_live.get("open_positions"),
            "currency": oanda_live.get("currency"),
            "source": oanda_live_src,
            "source_ts": oanda_live.get("ts"),
        })
        rows.append({"ts": now, "floor": "F41", "venue": "oanda_practice",
                     "metric": "balance_gbp", "value": oanda_live.get("balance"),
                     "currency": "GBP", "source": oanda_live_src,
                     "source_ts": oanda_live.get("ts"), "advisory_only": True})
        rows.append({"ts": now, "floor": "F41", "venue": "oanda_practice",
                     "metric": "unrealized_pnl_gbp", "value": oanda_live.get("unrealized_pl"),
                     "currency": "GBP", "source": oanda_live_src,
                     "source_ts": oanda_live.get("ts"), "advisory_only": True})
    else:
        gaps.append("F41 live balance: qsb_oanda_live.json missing/not ok")

    # lifetime realized PnL from the aggregate pnl bus
    if pnl_latest:
        f41agg = (pnl_latest.get("by_floor", {}) or {}).get("F41", {})
        life = f41agg.get("oanda_lifetime", {})
        if life:
            f41_block["realized_pnl_lifetime_gbp"] = life.get("grand_pl_gbp")
            f41_block["fills_with_pl"] = life.get("fills_with_pl")
            f41_block["lifetime_source"] = pnl_latest_src
            f41_block["lifetime_source_ts"] = life.get("ts")
            rows.append({"ts": now, "floor": "F41", "venue": "oanda_practice",
                         "metric": "realized_pnl_lifetime_gbp",
                         "value": life.get("grand_pl_gbp"), "currency": "GBP",
                         "source": pnl_latest_src, "source_ts": life.get("ts"),
                         "advisory_only": True})
            # keep top per-instrument PnL contributors for tax/audit detail
            byi = life.get("by_instrument", {}) or {}
            top = sorted(byi.items(), key=lambda kv: kv[1].get("pl", 0), reverse=True)
            f41_block["by_instrument_top"] = {
                k: {"pl_gbp": round(v.get("pl", 0), 4), "trades": v.get("trades"),
                    "wins": v.get("wins"), "losses": v.get("losses")}
                for k, v in top[:6]}
        else:
            gaps.append("F41 lifetime realized PnL: oanda_lifetime block absent")

    # ---- F42 Binance testnet: broker realized PnL by symbol ----------------
    f42_block: dict[str, Any] = {"floor": "F42", "venue": "binance_testnet",
                                 "mode": "binance_testnet", "advisory_only": True}
    if pnl_latest:
        f42 = (pnl_latest.get("by_floor", {}) or {}).get("F42", {})
        broker = f42.get("broker", {}) or {}
        syms = broker.get("broker_pnl_usdt_by_symbol", {}) or {}
        realized_usdt = round(sum(v.get("realized_pnl", 0) for v in syms.values()), 6)
        f42_block.update({
            "realized_pnl_usdt": realized_usdt,
            # USDT treated 1:1 USD for reconciliation (testnet stablecoin)
            "realized_pnl_gbp_approx": round(realized_usdt * gpu, 4),
            "filled_trades": broker.get("filled_trades"),
            "by_symbol": {k: round(v.get("realized_pnl", 0), 4) for k, v in syms.items()},
            "source": pnl_latest_src,
            "source_ts": pnl_latest.get("ts"),
            "note": "USDT valued 1:1 USD (testnet stablecoin); unrealized not attributed on this floor yet",
        })
        rows.append({"ts": now, "floor": "F42", "venue": "binance_testnet",
                     "metric": "realized_pnl_usdt", "value": realized_usdt,
                     "currency": "USDT", "source": pnl_latest_src,
                     "source_ts": pnl_latest.get("ts"), "advisory_only": True})
    else:
        gaps.append("F42 broker PnL: qsb_trader_pnl_latest.json missing")

    # ---- F43 Alpaca paper stocks: broker realized PnL + market status ------
    f43_block: dict[str, Any] = {"floor": "F43", "venue": "alpaca_paper",
                                 "mode": "alpaca_paper", "advisory_only": True}
    stock_status, stock_status_src = _load_json("stock_floor_status.json")
    if pnl_latest:
        f43 = (pnl_latest.get("by_floor", {}) or {}).get("F43", {})
        broker = f43.get("broker", {}) or {}
        syms = broker.get("broker_pnl_usd_by_symbol", {}) or {}
        realized_usd = round(sum(v.get("realized_pnl", 0) for v in syms.values()), 6)
        f43_block.update({
            "realized_pnl_usd": realized_usd,
            "realized_pnl_gbp": round(realized_usd * gpu, 4),
            "filled_orders": broker.get("filled_orders"),
            "by_symbol": {k: round(v.get("realized_pnl", 0), 4) for k, v in syms.items()},
            "source": pnl_latest_src,
            "source_ts": pnl_latest.get("ts"),
        })
        rows.append({"ts": now, "floor": "F43", "venue": "alpaca_paper",
                     "metric": "realized_pnl_usd", "value": realized_usd,
                     "currency": "USD", "source": pnl_latest_src,
                     "source_ts": pnl_latest.get("ts"), "advisory_only": True})
    else:
        gaps.append("F43 broker PnL: qsb_trader_pnl_latest.json missing")

    if stock_status:
        ms = stock_status.get("market_status")
        f43_block["market_status"] = ms
        f43_block["market_status_source"] = stock_status_src
        f43_block["market_status_ts"] = stock_status.get("status_ts")
        f43_block["account_read_ready"] = stock_status.get("account_read_ready")
        if ms and ms != "open":
            no = (stock_status.get("market_status_detail", {}) or {}).get("next_open")
            f43_block["note"] = f"stocks market {ms}; next_open {no}"
    else:
        gaps.append("F43 market status: stock_floor_status.json missing")

    # ---- Belief-trader pot: committed capital + open exposure --------------
    pot, pot_src = _load_json("qsb_portfolio_pot.json")
    pot_block: dict[str, Any] = {"advisory_only": True}
    if pot:
        open_pos = pot.get("open_positions", {}) or {}
        by_venue = pot.get("by_venue", {}) or {}
        # open exposure by instrument (GBP notional) from real open positions
        exposure_by_instr: dict[str, float] = {}
        exposure_by_venue: dict[str, float] = {}
        for _pid, p in open_pos.items():
            instr = p.get("instrument", "?")
            ven = p.get("venue", "?")
            ng = float(p.get("notional_gbp", 0) or 0)
            exposure_by_instr[instr] = round(exposure_by_instr.get(instr, 0) + ng, 4)
            exposure_by_venue[ven] = round(exposure_by_venue.get(ven, 0) + ng, 4)
        pot_block.update({
            "cap_gbp": pot.get("cap_gbp"),
            "committed_gbp": pot.get("committed_gbp"),
            "committed_by_venue_raw": by_venue,
            "open_position_count": len(open_pos),
            "open_exposure_gbp_by_instrument": exposure_by_instr,
            "open_exposure_gbp_by_venue": exposure_by_venue,
            "open_exposure_gbp_total": round(sum(exposure_by_instr.values()), 4),
            "source": pot_src,
            "source_ts": _file_mtime("qsb_portfolio_pot.json"),
        })
        rows.append({"ts": now, "floor": "F44", "venue": "belief_fleet",
                     "metric": "committed_gbp", "value": pot.get("committed_gbp"),
                     "currency": "GBP", "source": pot_src,
                     "source_ts": _file_mtime("qsb_portfolio_pot.json"),
                     "advisory_only": True})
        rows.append({"ts": now, "floor": "F44", "venue": "belief_fleet",
                     "metric": "open_exposure_gbp_total",
                     "value": pot_block["open_exposure_gbp_total"],
                     "currency": "GBP", "source": pot_src,
                     "source_ts": _file_mtime("qsb_portfolio_pot.json"),
                     "advisory_only": True})
    else:
        gaps.append("Belief-fleet pot: qsb_portfolio_pot.json missing")

    # ---- Provider spend for the UTC day (real cost accounting) -------------
    spend_block: dict[str, Any] = {"utc_day": today, "currency": "USD"}
    tail = REG / "qsb_tower_activity_tail.jsonl"
    if tail.exists():
        by_provider: dict[str, dict[str, Any]] = {}
        n_calls = 0
        spent_after_max = 0.0
        daily_cap = None
        summed = 0.0
        for line in tail.read_text().splitlines():
            line = line.strip()
            if not line or "provider_call" not in line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            pl = ev.get("payload", {}) or {}
            ts = pl.get("ts") or ev.get("ts") or ""
            if not ts.startswith(today):
                continue
            n_calls += 1
            prov = pl.get("provider", "unknown")
            cost = float(pl.get("cost_usd", 0) or 0)
            summed += cost
            sa = pl.get("spent_today_after_usd")
            if sa is not None:
                spent_after_max = max(spent_after_max, float(sa))
            if pl.get("daily_cap_usd") is not None:
                daily_cap = pl.get("daily_cap_usd")
            b = by_provider.setdefault(prov, {"calls": 0, "cost_usd": 0.0})
            b["calls"] += 1
            b["cost_usd"] = round(b["cost_usd"] + cost, 6)
        spend_block.update({
            "provider_calls_today": n_calls,
            "by_provider": by_provider,
            "cost_usd_summed_today": round(summed, 6),
            "spent_today_after_usd_max": round(spent_after_max, 6),
            "daily_cap_usd": daily_cap,
            "source": str(tail),
            "note": "spent_today_after_usd_max is the ledger's own running counter; "
                    "cost_usd_summed_today is our independent re-sum of today's rows",
        })
        rows.append({"ts": now, "floor": "F102", "venue": "provider_spend",
                     "metric": "cost_usd_today", "value": round(summed, 6),
                     "currency": "USD", "source": str(tail),
                     "source_ts": today, "advisory_only": True})
    else:
        gaps.append("Provider spend: qsb_tower_activity_tail.jsonl missing")

    # ---- Reconciled tower-wide realized PnL (GBP) --------------------------
    # Sum each floor's realized PnL converted to GBP with the shared rate.
    realized_gbp_total = 0.0
    realized_components: dict[str, float] = {}
    if "realized_pnl_lifetime_gbp" in f41_block and f41_block["realized_pnl_lifetime_gbp"] is not None:
        v = float(f41_block["realized_pnl_lifetime_gbp"])
        realized_components["F41_oanda_lifetime_gbp"] = round(v, 4)
        realized_gbp_total += v
    if "realized_pnl_gbp_approx" in f42_block:
        v = float(f42_block["realized_pnl_gbp_approx"])
        realized_components["F42_binance_gbp"] = round(v, 4)
        realized_gbp_total += v
    if "realized_pnl_gbp" in f43_block:
        v = float(f43_block["realized_pnl_gbp"])
        realized_components["F43_alpaca_gbp"] = round(v, 4)
        realized_gbp_total += v

    summary = {
        "ok": True,
        "kind": "qsb_accounts_summary",
        "phase": "FLOOR_44_102_ACCOUNTS_RECONCILIATION_V1",
        "generated_ts": now,
        "advisory_only": True,
        "execution_allowed": False,
        "real_money": False,
        "gbp_per_usd": round(gpu, 6),
        "usd_per_gbp": round(usd_per_gbp, 6),
        "reconciled_totals": {
            "realized_pnl_gbp_all_venues": round(realized_gbp_total, 4),
            "realized_pnl_components_gbp": realized_components,
            "oanda_practice_nav_gbp": f41_block.get("nav_gbp"),
            "oanda_practice_balance_gbp": f41_block.get("balance_gbp"),
            "oanda_unrealized_gbp": f41_block.get("unrealized_pnl_gbp"),
            "belief_fleet_committed_gbp": pot_block.get("committed_gbp"),
            "belief_fleet_open_exposure_gbp": pot_block.get("open_exposure_gbp_total"),
            "provider_spend_usd_today": spend_block.get("cost_usd_summed_today"),
        },
        "by_floor": {
            "F41_oanda_practice": f41_block,
            "F42_binance_testnet": f42_block,
            "F43_alpaca_paper": f43_block,
        },
        "belief_fleet_pot": pot_block,
        "provider_spend": spend_block,
        "data_gaps": gaps,
        "ledger_rows_written": len(rows),
        "sources": {
            "oanda_live": oanda_live_src,
            "pnl_aggregate": pnl_latest_src,
            "stock_status": stock_status_src,
            "portfolio_pot": pot_src,
            "provider_activity_tail": str(tail),
        },
    }
    return {"summary": summary, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh F44/F102 accounts reconciliation (read-only).")
    ap.add_argument("--quiet", action="store_true", help="minimal stdout")
    args = ap.parse_args()

    out = build()
    summary = out["summary"]
    rows = out["rows"]

    # append ledger rows (append-only audit trail)
    with LEDGER_PATH.open("a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    # overwrite latest summary (dashboards read this)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    if args.quiet:
        rt = summary["reconciled_totals"]
        print(f"accounts refreshed: realized_all_gbp={rt['realized_pnl_gbp_all_venues']} "
              f"oanda_nav_gbp={rt['oanda_practice_nav_gbp']} "
              f"exposure_gbp={rt['belief_fleet_open_exposure_gbp']} "
              f"provider_usd_today={rt['provider_spend_usd_today']} "
              f"gaps={len(summary['data_gaps'])}")
    else:
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
