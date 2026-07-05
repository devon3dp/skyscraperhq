"""qsb_trader_chat_board.py — shared knowledge board for the cross-floor
trader fleet.

Ross 2026-06-19: "all traders on all platforms can talk to each other ...
maybe they learn from each other as well". Each trader posts their current
status; losing traders can pull recent winners and adopt a peer's strategy.

Diversity safeguard: a strategy is only "learnable" if more than 1 trader
in the fleet currently uses it. This prevents monoculture collapse — there
will always be at least 1 trader on each strategy as a hedge.

Board location: data/registries/qsb_trader_chat_board.jsonl (append-only).

Schema per row:
  {
    "ts": "...", "worker_id": "f42_market_scout",
    "floor": "F42", "instrument": "BTCUSDT",
    "strategy": "momentum",
    "win_streak": 3, "loss_streak": 0,
    "total_pnl": 0.42,
    "wins": 12, "losses": 8,
    "win_rate": 0.6
  }
"""

from __future__ import annotations
import datetime
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
BOARD = ROOT / "data/registries/qsb_trader_chat_board.jsonl"
LEARN_LOG = ROOT / "data/registries/qsb_trader_learning_events.jsonl"

# How many recent rows to consider when computing fleet strategy mix
RECENT_LOOKBACK = 100
# How many "winning" peers to consider when learning
WINNER_TOP_N = 5
# Minimum trades a peer must have before we copy them
PEER_MIN_TRADES = 5
# Lose this much streak before considering peer-learn
LEARN_AFTER_LOSS_STREAK = 3
# Diversity floor: a strategy must have > this many users to be a learn-target
DIVERSITY_FLOOR = 1


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def post_status(*, worker_id: str, floor: str, instrument: str,
                strategy: str, win_streak: int, loss_streak: int,
                total_pnl: float, wins: int, losses: int) -> None:
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    total = wins + losses
    row = {
        "ts": now_iso(),
        "worker_id": worker_id,
        "floor": floor,
        "instrument": instrument,
        "strategy": strategy,
        "win_streak": win_streak,
        "loss_streak": loss_streak,
        "total_pnl": round(total_pnl, 6),
        "wins": wins, "losses": losses,
        "win_rate": round(wins / total, 3) if total else 0.0,
    }
    with open(BOARD, "a") as f:
        f.write(json.dumps(row) + "\n")


def _read_recent(n: int = RECENT_LOOKBACK) -> list[dict]:
    if not BOARD.exists():
        return []
    out = []
    for ln in BOARD.read_text().splitlines()[-n:]:
        ln = ln.strip()
        if not ln: continue
        try: out.append(json.loads(ln))
        except Exception: pass
    return out


def fleet_strategy_mix() -> dict[str, int]:
    """How many active traders are currently using each strategy.
    Uses each worker's MOST RECENT board post."""
    latest_by_worker: dict[str, dict] = {}
    for row in _read_recent():
        latest_by_worker[row["worker_id"]] = row
    return Counter(r["strategy"] for r in latest_by_worker.values())


def peer_learn(*, worker_id: str, current_strategy: str,
               loss_streak: int) -> dict | None:
    """If this worker is on a losing streak, look at the board and maybe
    suggest a better strategy from a winning peer. Diversity-aware.

    Returns {old, new, reason, peer} when a swap is suggested, else None.
    """
    if loss_streak < LEARN_AFTER_LOSS_STREAK:
        return None

    rows = _read_recent()
    if not rows:
        return None

    # Most recent row per worker (excluding self)
    latest_by_worker: dict[str, dict] = {}
    for row in rows:
        if row.get("worker_id") == worker_id:
            continue
        latest_by_worker[row["worker_id"]] = row

    peers = list(latest_by_worker.values())
    # Eligible peers: have at least PEER_MIN_TRADES + positive PnL + on a strat
    # that has > DIVERSITY_FLOOR users (so we don't drain the gene pool)
    mix = fleet_strategy_mix()
    eligible = [p for p in peers
                if (p["wins"] + p["losses"]) >= PEER_MIN_TRADES
                and p["total_pnl"] > 0
                and mix.get(p["strategy"], 0) > DIVERSITY_FLOOR]
    if not eligible:
        return None

    # Sort by composite winner score: prefer higher win_rate + higher streak
    def score(p: dict) -> float:
        return p["win_rate"] + 0.05 * p["win_streak"]
    eligible.sort(key=score, reverse=True)
    top = eligible[:WINNER_TOP_N]
    # Pick weighted-random from top to keep some randomness (Ross
    # 2026-06-19: keep diversity, don't all flip to one winner)
    pick = random.choice(top)
    if pick["strategy"] == current_strategy:
        # Already on best peer's strategy — no swap
        return None

    suggestion = {
        "old": current_strategy,
        "new": pick["strategy"],
        "peer": pick["worker_id"],
        "peer_win_rate": pick["win_rate"],
        "peer_pnl": pick["total_pnl"],
        "reason": (f"loss_streak {loss_streak} ≥ {LEARN_AFTER_LOSS_STREAK}, "
                   f"peer {pick['worker_id']} winning at "
                   f"{pick['win_rate']:.2f} on {pick['strategy']}"),
    }

    # Audit
    LEARN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LEARN_LOG, "a") as f:
        f.write(json.dumps({
            "ts": now_iso(),
            "worker_id": worker_id,
            **suggestion,
        }) + "\n")
    return suggestion


def board_summary() -> dict:
    """Snapshot of the board — fleet size + strategy mix + top winners."""
    rows = _read_recent()
    latest_by_worker: dict[str, dict] = {}
    for row in rows:
        latest_by_worker[row["worker_id"]] = row
    workers = list(latest_by_worker.values())
    mix = Counter(w["strategy"] for w in workers)
    workers_sorted = sorted(workers, key=lambda w: w["total_pnl"], reverse=True)
    return {
        "ts": now_iso(),
        "fleet_size": len(workers),
        "strategy_mix": dict(mix),
        "top_5_winners": [
            {"worker": w["worker_id"], "strategy": w["strategy"],
             "pnl": w["total_pnl"], "win_rate": w["win_rate"],
             "streak": w["win_streak"]}
            for w in workers_sorted[:5]
        ],
        "bottom_3_losers": [
            {"worker": w["worker_id"], "strategy": w["strategy"],
             "pnl": w["total_pnl"], "win_rate": w["win_rate"],
             "loss_streak": w["loss_streak"]}
            for w in workers_sorted[-3:]
        ],
    }
