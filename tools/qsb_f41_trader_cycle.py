#!/usr/bin/env python3
"""qsb_f41_trader_cycle.py — close-old + open-new cycle for F41 practice traders.

Designed to be called periodically (cron / systemd timer) to keep the
hands-on-learning loop turning:

  1. Force-refresh the lifecycle snapshot so the PnL panel is current.
  2. Close any open trade older than --hold-secs (default 900 = 15 min).
  3. If open < max_open_trades, run a small cohort to top up via
     qsb_train_and_trade_cohort.

OANDA practice only. Refuses if execution_mode != practice or kill switch on.
Per Ross 2026-06-16 authorization for the demo account; certified-trader gate.
"""

from __future__ import annotations
import argparse, json, sys, subprocess, datetime
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def force_refresh():
    """Force the F41 lifecycle + snapshot to refresh so the dashboard is current."""
    from tower.qsb_floor41_oanda import refresh_all
    try:
        return refresh_all()
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def close_aged_trades(hold_secs: int) -> dict:
    """Close any open trade that has been held > hold_secs."""
    from tower.qsb_floor41_oanda import _load_lifecycle_state, close_paper_trade
    state = _load_lifecycle_state()
    opens = list(state.get("open_trades", []))
    closed, skipped = [], []
    now = datetime.datetime.now(datetime.timezone.utc)
    for t in opens:
        opened_ts = t.get("opened_ts", "")
        try:
            opened = datetime.datetime.fromisoformat(opened_ts.replace("Z", "+00:00"))
        except Exception:
            skipped.append({"trade_id": t.get("trade_id"), "reason": "bad_ts"})
            continue
        age = (now - opened).total_seconds()
        if age < hold_secs:
            skipped.append({"trade_id": t.get("trade_id"), "age_s": int(age), "still_young": True})
            continue
        try:
            res = close_paper_trade(t["trade_id"], close_reason=f"cycle_close_age_{int(age)}s")
            closed.append({"trade_id": t["trade_id"], "age_s": int(age),
                           "ok": res.get("ok"), "pnl": res.get("realized_pl")})
        except Exception as e:
            skipped.append({"trade_id": t["trade_id"], "error": str(e)[:120]})
    return {"closed": closed, "skipped": skipped}


def open_cohort_if_room(units: int, instrument: str) -> dict:
    """Run a small training+trade cohort if room under max_open_trades AND
    the entry signal says we should trade.

    2026-06-21 V1.6 trader-winning fix B (team unanimous 4/4): use the
    existing classify_signal() in oanda_paper_strategy_lab.py to decide
    whether to open. Was: open blindly every cycle = 957 trades, 0 wins.
    Now: only open when signal in ('long_bias','short_bias'), skip on
    'no_trade' or 'observe'. Should produce fewer but smarter trades.
    """
    from tower.qsb_floor41_oanda import _load_lifecycle_state, _load
    from tower.oanda_paper_strategy_lab import classify_signal, metric_from_price
    guards = _load("qsb_floor41_oanda_state.json", {}).get("live_signals", {})
    cap = int(guards.get("max_open_trades", 3))
    cur = len(_load_lifecycle_state().get("open_trades", []))
    if cur >= cap:
        return {"ok": True, "skipped": "at_cap", "cap": cap, "open_now": cur}

    # Entry-signal gate (V1.6 fix B): only open when signal is bias-positive.
    prices_doc = _load("qsb_floor41_oanda_prices_latest.json", {})
    prices = prices_doc.get("prices") or []
    quote = next((p for p in prices if p.get("instrument") == instrument), None)
    signal = "no_signal"
    signal_reason = "no quote for instrument"
    if quote:
        metric = metric_from_price(quote) if quote.get("bids") else {
            "spread_pips": quote.get("spread_pips"),
            "top_bid_liquidity": 0, "top_ask_liquidity": 0,
            "top_liquidity_imbalance": 0,
        }
        signal, signal_reason = classify_signal(metric)
    if signal not in ("long_bias", "short_bias"):
        return {"ok": True, "skipped": "no_entry_signal",
                "signal": signal, "signal_reason": signal_reason,
                "cap": cap, "open_now": cur}

    room = cap - cur
    cohort_n = min(room * 3, 6)  # ~30% cert rate; try 3x room
    cmd = [sys.executable, str(ROOT / "tools/qsb_train_and_trade_cohort.py"),
           "--cohort", str(cohort_n), "--instrument", instrument,
           "--venue", "oanda_practice", "--units", str(units),
           "--from-floor", "F41"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        tail = (r.stdout or "").splitlines()[-6:]
        return {"ok": r.returncode == 0, "cap": cap, "open_now": cur,
                "signal": signal, "signal_reason": signal_reason, "tail": tail}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def stamp(payload: dict):
    out = ROOT / "data/registries/qsb_f41_trader_cycle.jsonl"
    with open(out, "a") as f:
        f.write(json.dumps(payload) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--hold-secs", type=int, default=900,
                   help="close trades older than this (default 900 = 15min)")
    p.add_argument("--units", type=int, default=100, help="cohort trade units")
    p.add_argument("--instrument", default="EUR_USD",
                   choices=["EUR_USD", "GBP_USD", "USD_JPY"])
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.dry_run:
        print("(dry run — would refresh + close > {}s + cohort)".format(args.hold_secs))
        return 0

    refresh = force_refresh()
    closed = close_aged_trades(args.hold_secs)
    opened = open_cohort_if_room(args.units, args.instrument)

    payload = {"ts": _now_iso(), "kind": "f41_trader_cycle",
               "hold_secs": args.hold_secs, "units": args.units,
               "instrument": args.instrument,
               "refresh_ok": refresh.get("ok"),
               "closed": closed.get("closed", []),
               "closed_count": len(closed.get("closed", [])),
               "skipped_count": len(closed.get("skipped", [])),
               "opened": opened}
    stamp(payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
