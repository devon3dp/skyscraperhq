"""qsb_trader_memory.py — per-trader memory + strategy module.

Each daemon worker gets their own memory file at
  data/registries/trader_memory/<worker_id>.json

Memory schema:
  {
    "worker_id": "f42_market_scout",
    "instrument": "BTCUSDT",
    "strategy": {
      "name": "momentum",  // momentum | mean_revert | scalp | random
      "params": {"lookback_min": 5, "threshold_bps": 5}
    },
    "stats": {
      "wins": 0, "losses": 0, "total_pnl": 0.0,
      "win_streak": 0, "loss_streak": 0,
      "trades_total": 0,
      "last_trade_ts": null
    },
    "open_trades": [
      {"order_id": "...", "side": "BUY", "qty": 0.001, "entry_px": 64000,
       "opened_ts": "2026-06-19T...Z"}
    ],
    "closed_trades": [   // most recent first, capped at 50
      {"order_id": "...", "side": "BUY", "qty": 0.001,
       "entry_px": 64000, "exit_px": 64200, "pnl": 0.20,
       "won": true, "opened_ts": "...", "closed_ts": "..."}
    ],
    "strategy_history": [
      {"ts": "...", "from": "momentum", "to": "mean_revert",
       "reason": "loss_streak >= 5"}
    ]
  }

Each worker:
  - Remembers their open + closed trades
  - Tracks wins/losses + streaks
  - Owns their strategy choice
  - Can SWITCH strategy after a 5-loss streak
"""

from __future__ import annotations
import datetime
import json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
MEM_DIR = ROOT / "data/registries/trader_memory"

CLOSED_CAP = 50            # keep last 50 closed trades
LOSS_STREAK_SWITCH = 5     # switch strategy after this many losses in a row

DEFAULT_STRATEGIES = [
    {"name": "momentum",
     "params": {"lookback_min": 5, "threshold_bps": 5}},
    {"name": "mean_revert",
     "params": {"lookback_min": 5, "threshold_bps": 5}},
    {"name": "scalp",
     "params": {"lookback_min": 1, "threshold_bps": 2}},
    {"name": "random",
     "params": {}},
]


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def mem_path(worker_id: str) -> Path:
    return MEM_DIR / f"{worker_id}.json"


def load(worker_id: str, instrument: str) -> dict:
    """Load or initialise this worker's memory."""
    p = mem_path(worker_id)
    if not p.exists():
        m = {
            "worker_id": worker_id,
            "instrument": instrument,
            "strategy": DEFAULT_STRATEGIES[0].copy(),
            "stats": {
                "wins": 0, "losses": 0, "total_pnl": 0.0,
                "win_streak": 0, "loss_streak": 0,
                "trades_total": 0, "last_trade_ts": None,
            },
            "open_trades": [],
            "closed_trades": [],
            "strategy_history": [],
        }
        save(worker_id, m)
        return m
    try:
        return json.loads(p.read_text())
    except Exception:
        return {
            "worker_id": worker_id, "instrument": instrument,
            "strategy": DEFAULT_STRATEGIES[0].copy(),
            "stats": {"wins": 0, "losses": 0, "total_pnl": 0.0,
                       "win_streak": 0, "loss_streak": 0,
                       "trades_total": 0, "last_trade_ts": None},
            "open_trades": [], "closed_trades": [],
            "strategy_history": [],
        }


def save(worker_id: str, mem: dict) -> None:
    MEM_DIR.mkdir(parents=True, exist_ok=True)
    p = mem_path(worker_id)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(mem, indent=2))
    tmp.replace(p)


def record_open(worker_id: str, instrument: str, order_id: str, side: str,
                qty: float, entry_px: float) -> dict:
    m = load(worker_id, instrument)
    m["open_trades"].append({
        "order_id": str(order_id),
        "side": side,
        "qty": qty,
        "entry_px": entry_px,
        "opened_ts": now_iso(),
    })
    m["stats"]["last_trade_ts"] = now_iso()
    m["stats"]["trades_total"] += 1
    save(worker_id, m)
    return m


def record_close(worker_id: str, instrument: str, order_id: str,
                 exit_px: float) -> dict:
    """Close a previously-open trade by order_id. Computes pnl, updates
    stats, may switch strategy on long loss streak."""
    m = load(worker_id, instrument)
    # Find the open trade
    remaining = []
    closed_one = None
    for ot in m["open_trades"]:
        if str(ot["order_id"]) == str(order_id) and closed_one is None:
            entry = float(ot["entry_px"])
            qty = float(ot["qty"])
            side_sign = 1 if ot["side"].upper() == "BUY" else -1
            pnl = (exit_px - entry) * qty * side_sign
            closed_one = {
                **ot,
                "exit_px": exit_px,
                "pnl": round(pnl, 6),
                "won": pnl > 0,
                "closed_ts": now_iso(),
            }
        else:
            remaining.append(ot)
    if closed_one is None:
        # No matching open trade; nothing to do
        return m
    m["open_trades"] = remaining
    # Prepend to closed (most recent first) + cap
    m["closed_trades"].insert(0, closed_one)
    m["closed_trades"] = m["closed_trades"][:CLOSED_CAP]
    # Stats
    s = m["stats"]
    s["total_pnl"] = round(s.get("total_pnl", 0) + closed_one["pnl"], 6)
    if closed_one["won"]:
        s["wins"] += 1
        s["win_streak"] += 1
        s["loss_streak"] = 0
    else:
        s["losses"] += 1
        s["loss_streak"] += 1
        s["win_streak"] = 0
    # Long loss streak → rotate strategy (Ross 2026-06-19: traders must
    # know the difference between winning and losing)
    if s["loss_streak"] >= LOSS_STREAK_SWITCH:
        old = m["strategy"]["name"]
        # Pick the next strategy in the list
        names = [d["name"] for d in DEFAULT_STRATEGIES]
        next_idx = (names.index(old) + 1) % len(names) if old in names else 0
        m["strategy"] = DEFAULT_STRATEGIES[next_idx].copy()
        m["strategy_history"].append({
            "ts": now_iso(),
            "from": old, "to": m["strategy"]["name"],
            "reason": f"loss_streak {s['loss_streak']}",
        })
        s["loss_streak"] = 0   # reset on switch — fresh start
    save(worker_id, m)
    return m


def get_strategy(worker_id: str, instrument: str) -> dict:
    """Return this worker's current strategy spec."""
    m = load(worker_id, instrument)
    return m["strategy"]


def get_summary(worker_id: str, instrument: str) -> dict:
    """Compact view of trader state."""
    m = load(worker_id, instrument)
    s = m["stats"]
    return {
        "worker_id": worker_id,
        "instrument": instrument,
        "strategy": m["strategy"]["name"],
        "wins": s["wins"], "losses": s["losses"],
        "win_rate": (s["wins"] / s["trades_total"]
                     if s["trades_total"] else 0.0),
        "total_pnl": s["total_pnl"],
        "win_streak": s["win_streak"],
        "loss_streak": s["loss_streak"],
        "open": len(m["open_trades"]),
    }
