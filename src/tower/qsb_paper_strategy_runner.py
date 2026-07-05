"""
QSB Paper Strategy Tick Runner
Phase: QSB_NEXT_SAFE_IMPROVEMENTS_V1 (extends paper trading lifecycle)

Cadence-driven runner that:
  * marks every OPEN paper trade at the latest known price
  * auto-closes any trade whose mark crosses stop/target/timeout
  * occasionally opens new advisory paper trades using deterministic
    simple-rule strategies (NEVER random; seeded by cadence tick_count)
  * respects max_open_trades=20 cap
  * runs ONLY in simulated_paper mode (no Binance/OANDA/Stocks API calls)
  * stamps every payload with real_money_live_trading_enabled=False

Trigger: invoked by scripts/qsb_paper_strategy_tick.sh on cadence tick.
The same script also runs the EQSB cadence tick so movement/task counts
grow naturally over time.

Writes:
  data/registries/qsb_paper_strategy_tick_state.json
  data/logs/qsb_paper_strategy_ticks.jsonl
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import hashlib

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

P_TICK_STATE = REG / "qsb_paper_strategy_tick_state.json"
L_TICKS      = LOGS / "qsb_paper_strategy_ticks.jsonl"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _safety_envelope():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "real_money_live_trading_enabled": False,
        "live_trading_enabled": False,
        "binance_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
    }


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _append_jsonl(path, rec):
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", _now())
    rec.setdefault("execution_allowed", False)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def _seeded_int(s, mod):
    return int(hashlib.sha1(str(s or "x").encode("utf-8")).hexdigest()[:8], 16) % max(1, int(mod))


SEED_MARKS = {
    "BTCUSDT": 63414.0, "ETHUSDT": 3500.0,
    "BNBUSDT":   600.0, "SOLUSDT":  150.0,
}


def _last_mark_for(symbol, tick):
    """Deterministic mark series — never random. Walks ±0.3% per tick
    based on a stable hash of (symbol, tick). Honest about being a
    simulated price walk."""
    base = SEED_MARKS.get(symbol.upper(), 100.0)
    seed = _seeded_int(symbol + "|" + str(tick), 1000)
    drift = (seed - 500) / 500.0 * 0.003   # ±0.3%
    return round(base * (1 + drift), 6)


def tick_once():
    """One cadence tick. Marks every open trade; auto-closes anything
    that crossed its stop/target; optionally opens 1 new trade if open
    count below cap and the cadence tick allows it."""
    from tower.qsb_paper_trading import (
        open_trade, mark_trade, close_trade,
        list_open_trades, refresh_open_trades_registry,
        refresh_learning_registry,
    )

    cadence = _load("eqsb_cadence_state.json", {})
    tick = int(cadence.get("tick_count") or 0)

    opens = list_open_trades()
    marked = []
    closed = []
    for t in opens:
        mark = _last_mark_for(t["symbol"], tick)
        res = mark_trade(t["trade_id"], mark)
        if res.get("ok"):
            marked.append({
                "trade_id": t["trade_id"],
                "symbol":   t["symbol"],
                "side":     t["side"],
                "mark":     mark,
                "current_pnl": res.get("current_pnl"),
            })
            # Auto-close path is already handled inside mark_trade when
            # stop/target hits. Track it via the open list after.

    # Re-list open trades to detect auto-closures
    opens_after = {x["trade_id"] for x in list_open_trades()}
    closed_now = [m for m in marked if m["trade_id"] not in opens_after]

    # Possibly OPEN a new advisory paper trade when:
    #  - open count < 20 (cap)
    #  - cadence tick is divisible by 2 (slow cadence)
    #  - we have a deterministic strategy choice
    opened_new = None
    open_count = len(list_open_trades())
    if open_count < 20 and tick > 0 and (tick % 2 == 0):
        strategies = [
            ("BTCUSDT", "LONG",  0.05, "wrk_binance_market_scout",
             "strategy_momentum_btc_cadence", 0.4, 1.0),
            ("ETHUSDT", "LONG",  1.0,  "wrk_spread_watcher",
             "strategy_mean_reversion_eth_cadence", 0.4, 0.9),
            ("BNBUSDT", "SHORT", 5.0,  "wrk_risk_clerk",
             "strategy_overbought_bnb_cadence", 0.5, 0.9),
            ("SOLUSDT", "LONG", 10.0,  "wrk_arbitrage_observer",
             "strategy_funding_carry_sol_cadence", 0.5, 1.0),
        ]
        choice = strategies[_seeded_int("strategy|" + str(tick), len(strategies))]
        sym, side, qty, wrk, strat, sp, tp = choice
        entry = _last_mark_for(sym, tick)
        r = open_trade(sym, side, entry, qty,
                        worker_id=wrk, strategy_id=strat,
                        entry_reason="cadence tick #%d advisory open" % tick,
                        stop_pct=sp, target_pct=tp,
                        guardian_verdict="ALLOW_ADVISORY")
        if r.get("ok"):
            opened_new = {"trade_id": r["trade_id"], "symbol": sym,
                          "side": side, "qty": qty, "strategy_id": strat}

    refresh_open_trades_registry()
    refresh_learning_registry()

    state = {
        "ok": True,
        "phase": "QSB_NEXT_SAFE_IMPROVEMENTS_V1",
        "kind": "qsb_paper_strategy_tick_state",
        "generated_ts": _now(),
        "cadence_tick_count": tick,
        "open_trades_before": len(opens),
        "open_trades_after":  open_count + (1 if opened_new else 0),
        "marked_count":       len(marked),
        "auto_closed_now":    closed_now,
        "opened_new":         opened_new,
        "policy":
            "Deterministic price walk (no random). Auto-close on "
            "stop/target rules. Strategy IDs tagged _cadence so they "
            "are distinguishable from the seed batch.",
    }
    state.update(_safety_envelope())
    _write_json(P_TICK_STATE, state)
    _append_jsonl(L_TICKS, {
        "event": "strategy_tick",
        "tick":  tick,
        "marked_count": len(marked),
        "auto_closed_now_count": len(closed_now),
        "opened_new_trade_id": (opened_new or {}).get("trade_id"),
    })
    # Record into EQSB so the kernel can replay
    _append_jsonl(LOGS / "eqsb_kernel_events.jsonl", {
        "event": "paper_strategy_tick",
        "phase": "QSB_NEXT_SAFE_IMPROVEMENTS_V1",
        "tick":  tick,
        "marked": len(marked),
        "auto_closed": len(closed_now),
        "opened_new": bool(opened_new),
    })
    return state


def main():
    print(json.dumps(tick_once(), indent=2))


if __name__ == "__main__":
    main()
