"""Floor 44 — Accounts / PnL Department.

Aggregates paper-trade outcomes across all three trading floors (F41 OANDA
practice, F42 Binance testnet, F43 Alpaca paper) into a single rolled-up
account picture.

Reads — never writes — the underlying floors' state. Stamps:
    data/registries/qsb_floor44_accounts_state.json

Safety envelope:
    advisory_only=True
    execution_allowed=False
    no real-money totals

Output structure:
    rolled_up_totals: {
        realized_pnl_usd, unrealized_pnl_usd, total_pnl_usd,
        realized_pnl_gbp, unrealized_pnl_gbp, total_pnl_gbp,
        open_position_count, closed_trade_count, win_count, loss_count,
        gbp_per_usd,
    }
    by_venue: { "oanda_practice": {...}, "binance_testnet": {...}, "alpaca_paper": {...} }
    by_strategy: { "scalp_silver_intraday": {trades, pnl_usd, ...}, ... }
    by_worker: { "f47.wren.scribe.04": {...}, ... }
    open_positions: [...]
"""

from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
STATE_PATH = REG / "qsb_floor44_accounts_state.json"

# Reuse the GBP/USD lookup from the floor-47 risk-cap tool so F44 + F47 agree.
import sys
sys.path.insert(0, str(ROOT / "tools"))
try:
    from qsb_risk_cap import gbp_per_usd  # type: ignore
except Exception:
    def gbp_per_usd() -> float:
        return 1.0 / 1.30   # conservative fallback


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(rel: str, fallback=None) -> Any:
    p = REG / rel
    if not p.exists():
        return {} if fallback is None else fallback
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {} if fallback is None else fallback


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _safety() -> dict:
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "real_money_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
        "worker_execution_enabled": False,
        "autonomous_dispatch_enabled": False,
    }


# ── per-venue collectors ────────────────────────────────────────────────


def collect_oanda() -> dict:
    """Pull F41 OANDA practice trades + PnL."""
    pnl_doc = _load("qsb_floor41_oanda_pnl.json")
    lifecycle = _load("qsb_floor41_oanda_trade_lifecycle.json")
    open_trades = lifecycle.get("open_trades", []) if isinstance(lifecycle, dict) else []
    closed_trades = lifecycle.get("closed_trades", []) if isinstance(lifecycle, dict) else []
    requests = lifecycle.get("requests", []) if isinstance(lifecycle, dict) else []

    return {
        "venue": "oanda_practice",
        "floor": "F41",
        "available": True,
        "realized_pnl_usd": float(pnl_doc.get("realized_pnl_total", 0) or 0),
        "unrealized_pnl_usd": float(pnl_doc.get("unrealized_pnl_total", 0) or 0),
        "total_pnl_usd": float(pnl_doc.get("total_pnl", 0) or 0),
        "open_position_count": int(pnl_doc.get("open_total", len(open_trades))),
        "closed_trade_count": int(pnl_doc.get("closed_total", len(closed_trades))),
        "win_count": int(pnl_doc.get("closed_winners", 0)),
        "loss_count": int(pnl_doc.get("closed_losers", 0)),
        "open_trades": open_trades,
        "closed_trades": closed_trades,
        "requests_seen": len(requests),
    }


def collect_binance_testnet() -> dict:
    """Pull F42 Binance testnet trade ledger."""
    interior = _load("qsb_floor42_binance_interior.json")
    testnet_state = _load("qsb_floor42_binance_testnet_state.json")
    # Binance trade ledger is appended to data/logs/binance_floor.jsonl by the
    # placement engine. Count rows; PnL on testnet is symbolic.
    ledger_path = ROOT / "data/logs/binance_floor.jsonl"
    placed = 0
    if ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line: continue
            try:
                row = json.loads(line)
                if row.get("event") == "place":
                    placed += 1
            except Exception:
                pass
    return {
        "venue": "binance_testnet",
        "floor": "F42",
        "available": bool(interior),
        "realized_pnl_usd": 0.0,
        "unrealized_pnl_usd": 0.0,
        "total_pnl_usd": 0.0,
        "open_position_count": 0,
        "closed_trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "placement_rows": placed,
        "note": "Binance testnet PnL aggregation not wired yet — placement counted, P&L pending.",
    }


def collect_alpaca_paper() -> dict:
    """Pull F43 Alpaca paper ledger."""
    status = _load("stock_floor_status.json")
    return {
        "venue": "alpaca_paper",
        "floor": "F43",
        "available": bool(status),
        "realized_pnl_usd": 0.0,
        "unrealized_pnl_usd": 0.0,
        "total_pnl_usd": 0.0,
        "open_position_count": 0,
        "closed_trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "note": "Alpaca paper PnL aggregation not wired yet — placement wrapper TBD.",
    }


# ── cross-cuts ──────────────────────────────────────────────────────────


def _by_strategy(oanda: dict) -> dict:
    """Group OANDA trades by strategy_name and tally."""
    groups: dict = {}
    lifecycle = _load("qsb_floor41_oanda_trade_lifecycle.json")
    for r in lifecycle.get("requests", []):
        s = r.get("strategy_name") or "unspecified"
        groups.setdefault(s, {"trade_count": 0, "instruments": set(),
                                "workers": set()})
        groups[s]["trade_count"] += 1
        if r.get("instrument"): groups[s]["instruments"].add(r["instrument"])
        if r.get("worker_id"): groups[s]["workers"].add(r["worker_id"])
    # PnL per strategy comes from closed trades that reference the request.
    for t in lifecycle.get("closed_trades", []):
        s = t.get("strategy_name") or "unspecified"
        if s in groups:
            groups[s].setdefault("realized_pnl_usd", 0.0)
            groups[s]["realized_pnl_usd"] += float(t.get("realized_pnl", 0) or 0)
    # Flatten sets to sorted lists
    for s, g in groups.items():
        g["instruments"] = sorted(g["instruments"])
        g["workers"] = sorted(g["workers"])
    return groups


def _by_worker(oanda: dict) -> dict:
    """Group trades by worker_id."""
    groups: dict = {}
    lifecycle = _load("qsb_floor41_oanda_trade_lifecycle.json")
    for r in lifecycle.get("requests", []):
        w = r.get("worker_id") or "unknown"
        groups.setdefault(w, {"trade_count": 0, "strategies": set(),
                                "instruments": set()})
        groups[w]["trade_count"] += 1
        if r.get("strategy_name"): groups[w]["strategies"].add(r["strategy_name"])
        if r.get("instrument"): groups[w]["instruments"].add(r["instrument"])
    for t in lifecycle.get("closed_trades", []):
        w = t.get("worker_id") or "unknown"
        if w in groups:
            groups[w].setdefault("realized_pnl_usd", 0.0)
            groups[w]["realized_pnl_usd"] += float(t.get("realized_pnl", 0) or 0)
    for w, g in groups.items():
        g["strategies"] = sorted(g["strategies"])
        g["instruments"] = sorted(g["instruments"])
    return groups


def build_state() -> dict:
    oanda = collect_oanda()
    binance = collect_binance_testnet()
    alpaca = collect_alpaca_paper()

    venues = {"oanda_practice": oanda,
              "binance_testnet": binance,
              "alpaca_paper": alpaca}

    realized_usd = sum(v["realized_pnl_usd"] for v in venues.values())
    unrealized_usd = sum(v["unrealized_pnl_usd"] for v in venues.values())
    total_usd = realized_usd + unrealized_usd
    rate = gbp_per_usd()

    rolled_up = {
        "realized_pnl_usd": round(realized_usd, 4),
        "unrealized_pnl_usd": round(unrealized_usd, 4),
        "total_pnl_usd": round(total_usd, 4),
        "realized_pnl_gbp": round(realized_usd * rate, 4),
        "unrealized_pnl_gbp": round(unrealized_usd * rate, 4),
        "total_pnl_gbp": round(total_usd * rate, 4),
        "open_position_count": sum(v["open_position_count"] for v in venues.values()),
        "closed_trade_count": sum(v["closed_trade_count"] for v in venues.values()),
        "win_count": sum(v["win_count"] for v in venues.values()),
        "loss_count": sum(v["loss_count"] for v in venues.values()),
        "gbp_per_usd": round(rate, 6),
    }

    # Win/loss ratio defended against div-by-zero
    closed = rolled_up["closed_trade_count"]
    rolled_up["win_rate"] = (round(rolled_up["win_count"] / closed, 3)
                              if closed > 0 else None)

    state = {
        "ok": True,
        "kind": "qsb_floor44_accounts_state",
        "phase": "FLOOR_44_ACCOUNTS_PNL_ROLLUP_V1",
        "generated_ts": _now(),
        "floor": "F44",
        "department": "Accounts / PnL Department",
        "rolled_up_totals": rolled_up,
        "by_venue": venues,
        "by_strategy": _by_strategy(oanda),
        "by_worker": _by_worker(oanda),
        **_safety(),
    }
    return state


def refresh() -> dict:
    state = build_state()
    _write(STATE_PATH, state)
    return state


if __name__ == "__main__":
    state = refresh()
    rt = state["rolled_up_totals"]
    print(f"  ROLLED UP TOTALS")
    print(f"    realized:    ${rt['realized_pnl_usd']:>10.2f}   £{rt['realized_pnl_gbp']:>10.2f}")
    print(f"    unrealized:  ${rt['unrealized_pnl_usd']:>10.2f}   £{rt['unrealized_pnl_gbp']:>10.2f}")
    print(f"    total:       ${rt['total_pnl_usd']:>10.2f}   £{rt['total_pnl_gbp']:>10.2f}")
    print(f"    open pos:    {rt['open_position_count']}    closed: {rt['closed_trade_count']}    win_rate: {rt['win_rate']}")
    print(f"  BY VENUE")
    for venue, v in state["by_venue"].items():
        print(f"    {venue:18s}  open={v['open_position_count']:>3d}  closed={v['closed_trade_count']:>3d}  P&L=${v['total_pnl_usd']:>8.2f}")
    print(f"  BY STRATEGY")
    for s, g in sorted(state["by_strategy"].items(),
                         key=lambda kv: -kv[1].get("trade_count", 0))[:10]:
        pnl = g.get("realized_pnl_usd", 0)
        print(f"    {s:28s}  trades={g['trade_count']:>2d}  realized=${pnl:>7.2f}  workers={len(g.get('workers',[]))}")
    print(f"  Stamped: {STATE_PATH.relative_to(ROOT)}")
