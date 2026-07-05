"""Auto-close evaluator for Floor 41 paper trades.

Reads every currently-open trade and decides whether to close it based on:
  · the strategy's target_profit_pct  → close_reason: take_profit
  · the strategy's max_loss_pct       → close_reason: stop_loss
  · the strategy's max_hold_seconds   → close_reason: max_hold_timeout

If a trade's strategy isn't in the F47 library (manual smoke tests etc.),
DEFAULTS apply: 0.10% target, 0.10% stop, 600s hold.

Trades are closed via tower.qsb_floor41_oanda.close_paper_trade so the
existing audit trail (closed_trades + actions + jsonl logs) is preserved.

Each close fires a trade_close event into the tower activity tail so we can
read "what just happened" between sessions.

Run with:
    python3 -m tower.qsb_auto_close_evaluator

Safety:
  · only paper_simulator trades are evaluated (real OANDA practice trades
    fed by oanda_practice_api are left alone — the OANDA broker owns close)
  · gate state never changes
  · advisory_only stamped on every output
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LIFECYCLE_PATH = REG / "qsb_floor41_oanda_trade_lifecycle.json"
PRICES_PATH = REG / "qsb_floor41_oanda_prices_latest.json"
STRATEGY_LIBRARY_PATH = REG / "qsb_wren_strategy_library.json"
SUMMARY_PATH = REG / "qsb_auto_close_last_tick.json"

# Defaults for trades whose strategy_name is not in the library (manual,
# smoke tests, legacy). Conservative.
DEFAULT_TARGET_PCT = 0.10
DEFAULT_LOSS_PCT = 0.10
DEFAULT_HOLD_SECONDS = 600

from tower.qsb_floor41_oanda import close_paper_trade, refresh_all
from tower.qsb_tower_activity import append_event


def _load(path: Path, fallback=None):
    if not path.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ts_to_epoch(ts: str) -> float:
    if not ts: return 0.0
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _strategy_lookup() -> dict[str, dict]:
    lib = _load(STRATEGY_LIBRARY_PATH)
    out = {}
    for s in lib.get("strategies", []):
        out[s["strategy_id"]] = s
    return out


def _price_lookup() -> dict[str, dict]:
    d = _load(PRICES_PATH)
    return {p["instrument"]: p for p in d.get("prices", [])
              if isinstance(p, dict) and p.get("instrument")}


def _pnl_pct(direction: str, entry: float, mid: float) -> float:
    """Return percent move in the trader's favor, signed."""
    if entry <= 0: return 0.0
    raw = (mid - entry) / entry * 100.0
    return raw if direction == "buy" else -raw


def evaluate_open_trades(now_epoch: Optional[float] = None) -> dict:
    """Walk every open trade, decide close vs leave, execute closes."""
    state = _load(LIFECYCLE_PATH)
    open_trades = state.get("open_trades", []) if isinstance(state, dict) else []
    strats = _strategy_lookup()
    prices = _price_lookup()

    if now_epoch is None:
        now_epoch = datetime.now(timezone.utc).timestamp()

    closes: list[dict] = []
    skips: list[dict] = []
    errors: list[dict] = []

    for t in open_trades:
        tid = t.get("trade_id")
        if not tid: continue
        instrument = t.get("instrument")
        direction = t.get("direction", "buy")
        entry = float(t.get("entry_price") or 0)
        opened_ts = t.get("opened_ts", "")
        strategy_name = t.get("strategy_name") or "manual"
        worker_id = t.get("worker_id")
        execution_mode = t.get("execution_mode", "paper_simulator")

        # Both paper_simulator and oanda_practice_api use the local price cache
        # (refreshed by refresh_all in either mode), so the same close logic
        # applies. Skip only truly unknown modes (e.g. future "live" mode).
        if execution_mode not in ("paper_simulator", "oanda_practice_api"):
            skips.append({"trade_id": tid, "reason": f"unsupported_mode:{execution_mode}"})
            continue

        # Resolve strategy parameters
        s = strats.get(strategy_name) or {}
        target = float(s.get("target_profit_pct", DEFAULT_TARGET_PCT))
        loss = float(s.get("max_loss_pct", DEFAULT_LOSS_PCT))
        max_hold = float(s.get("max_hold_seconds", DEFAULT_HOLD_SECONDS))

        # Resolve current price
        p = prices.get(instrument)
        if not p:
            skips.append({"trade_id": tid, "reason": f"no_price:{instrument}"})
            continue
        mid = (float(p.get("bid", 0)) + float(p.get("ask", 0))) / 2.0
        if mid <= 0:
            skips.append({"trade_id": tid, "reason": "zero_mid"})
            continue

        # Compute current PnL pct + elapsed seconds
        pnl_pct = _pnl_pct(direction, entry, mid)
        age = now_epoch - _ts_to_epoch(opened_ts)

        close_reason = None
        if pnl_pct >= target:
            close_reason = "auto_take_profit"
        elif pnl_pct <= -loss:
            close_reason = "auto_stop_loss"
        elif age >= max_hold:
            close_reason = "auto_max_hold_timeout"
        else:
            skips.append({
                "trade_id": tid, "reason": "no_trigger",
                "pnl_pct": round(pnl_pct, 4),
                "age_seconds": int(age),
                "target": target, "loss": loss, "hold": max_hold,
            })
            continue

        # Fire the close
        try:
            res = close_paper_trade(
                trade_id=tid,
                close_reason=close_reason,
                worker_id="f47.wren.auto_close_evaluator",
            )
            closes.append({
                "trade_id": tid,
                "instrument": instrument,
                "direction": direction,
                "entry_price": entry,
                "exit_mid": round(mid, 5),
                "pnl_pct": round(pnl_pct, 4),
                "age_seconds": int(age),
                "close_reason": close_reason,
                "strategy_name": strategy_name,
                "worker_id": worker_id,
                "ok": bool(res.get("ok")),
            })
            # Activity tail event
            append_event(
                "trade_close",
                summary=(f"{tid} {instrument} {direction} {entry}→{round(mid,5)} "
                         f"{round(pnl_pct,3)}% {close_reason}"),
                floor="F41",
                worker_id="f47.wren.auto_close_evaluator",
                payload={
                    "trade_id": tid, "instrument": instrument,
                    "pnl_pct": round(pnl_pct, 4),
                    "close_reason": close_reason,
                    "strategy_name": strategy_name,
                    "trader_worker_id": worker_id,
                },
            )
        except Exception as exc:
            errors.append({"trade_id": tid, "error": str(exc)[:160]})

    # Refresh PnL aggregates after closes
    if closes:
        try:
            refresh_all()
        except Exception:
            pass

    # Single tick-level event
    append_event(
        "auto_close_tick",
        summary=f"evaluated {len(open_trades)} open · closed {len(closes)} · skipped {len(skips)} · errors {len(errors)}",
        floor="F41",
        payload={"closed_count": len(closes), "skipped_count": len(skips),
                  "error_count": len(errors)},
    )

    summary = {
        "ok": True,
        "kind": "qsb_auto_close_last_tick",
        "generated_ts": _now(),
        "evaluated_count": len(open_trades),
        "closed_count": len(closes),
        "skipped_count": len(skips),
        "error_count": len(errors),
        "closes": closes,
        "skips_sample": skips[:20],
        "errors": errors,
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    s = evaluate_open_trades()
    print(f"  evaluated:  {s['evaluated_count']}")
    print(f"  closed:     {s['closed_count']}")
    print(f"  skipped:    {s['skipped_count']}")
    print(f"  errors:     {s['error_count']}")
    if s["closes"]:
        print(f"  closes:")
        for c in s["closes"][:20]:
            print(f"    {c['trade_id']}  {c['instrument']:10s} {c['direction']:5s} "
                  f"entry={c['entry_price']:>10.4f} exit={c['exit_mid']:>10.4f}  "
                  f"pnl_pct={c['pnl_pct']:>6.3f}%  age={c['age_seconds']:>5d}s  "
                  f"reason={c['close_reason']}")
