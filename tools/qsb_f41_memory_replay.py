"""qsb_f41_memory_replay.py — backfill F41 trader memory from the
existing closed-trades registry.

Trigger: Ross 2026-06-21 — F42 workers have trader_memory/, F41 workers
have ZERO. 622 closed F41 trades exist on disk with full detail but
no per-worker memory file aggregates them. This tool replays them
into the same trader_memory/ directory using one file per
(worker_id, instrument) combo, since F41 workers trade multiple FX
pairs (EUR_USD, GBP_USD, USD_JPY) and the existing qsb_trader_memory
schema is single-instrument-per-file.

Idempotent: re-running overwrites the F41 files (the source registry
is authoritative). Does NOT touch F42 memory files.

Run:
    python3 tools/qsb_f41_memory_replay.py             # apply
    python3 tools/qsb_f41_memory_replay.py --dry-run   # preview only
"""
from __future__ import annotations
import argparse, datetime, json
from collections import defaultdict
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
SRC = REPO / "data/registries/qsb_floor41_oanda_closed_trades.json"
MEM_DIR = REPO / "data/registries/trader_memory"
F47 = REPO / "data/registries/qsb_f47_team_records.jsonl"

# Mirror the cap from qsb_trader_memory.py (most-recent-N closed trades).
CLOSED_CAP = 200


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp(rows_written: int, workers: int, instruments: int) -> None:
    F47.parent.mkdir(parents=True, exist_ok=True)
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": now_iso(), "kind": "f41_memory_replayed", "role": "claude",
            "subject": "trader_memory/f41_<worker>__<instrument>.json",
            "detail": (
                f"F41 trader_memory backfilled from "
                f"qsb_floor41_oanda_closed_trades.json. "
                f"{rows_written} memory files written across "
                f"{workers} workers × {instruments} instruments. "
                "Per-(worker, instrument) file mirrors F42 single-"
                "instrument schema. Forex peer-learning loop not yet "
                "wired — that's the next step. Team-designed: per-worker "
                "split (Wren+F42 pattern), open+close write timing "
                "(qwen3.5+F42 pattern), separate forex loop (unanimous)."
            ),
        }) + "\n")


def build_memory(rows: list[dict], worker_id: str, instrument: str) -> dict:
    """Build a per-(worker, instrument) memory dict mirroring F42's
    trader_memory schema. Computes stats from the historical trades."""
    closed = []
    wins = 0
    losses = 0
    total_pnl = 0.0
    last_ts = None
    # Newest first (matches qsb_trader_memory.record_close behavior).
    rows_sorted = sorted(rows, key=lambda r: r.get("closed_ts", ""))
    streak_win = 0
    streak_loss = 0
    for r in rows_sorted:
        pnl = float(r.get("pnl_amount") or 0)
        won = pnl > 0
        total_pnl += pnl
        if won:
            wins += 1
            streak_win += 1
            streak_loss = 0
        else:
            losses += 1
            streak_loss += 1
            streak_win = 0
        last_ts = r.get("closed_ts") or last_ts
        closed.insert(0, {
            "order_id": r.get("trade_id") or r.get("request_id"),
            "side": (r.get("direction") or "").upper() or "BUY",
            "qty": float(r.get("units") or 0),
            "entry_px": float(r.get("entry_price") or 0),
            "opened_ts": r.get("opened_ts"),
            "exit_px": float(r.get("exit_price") or 0),
            "pnl": round(pnl, 6),
            "won": won,
            "closed_ts": r.get("closed_ts"),
            "strategy_name": r.get("strategy_name"),
            "close_reason": r.get("close_reason"),
        })
    return {
        "worker_id": worker_id,
        "instrument": instrument,
        # Strategy starts at "mean_revert" baseline (matches F42 default)
        # — daemon-side wiring will rotate via record_close peer-learning.
        "strategy": {"name": "mean_revert",
                     "params": {"lookback_min": 5, "threshold_bps": 5}},
        "stats": {
            "wins": wins,
            "losses": losses,
            "total_pnl": round(total_pnl, 6),
            "win_streak": streak_win,
            "loss_streak": streak_loss,
            "trades_total": len(rows_sorted),
            "last_trade_ts": last_ts,
        },
        "open_trades": [],   # snapshot — source has no live opens for these
        "closed_trades": closed[:CLOSED_CAP],
        "strategy_history": [],
        # Provenance — mark these as backfilled so live writers can tell
        # the difference between replayed history and fresh writes.
        "backfilled_from": "qsb_floor41_oanda_closed_trades.json",
        "backfilled_ts": now_iso(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not SRC.exists():
        print(f"[f41-mem-replay] ERROR: source missing: {SRC}")
        return 1

    payload = json.loads(SRC.read_text())
    closed = payload.get("closed_trades") or []
    print(f"[f41-mem-replay] source: {SRC.relative_to(REPO)} "
          f"({len(closed)} closed trades)")

    # Group by (worker_id, instrument).
    buckets: dict[tuple, list] = defaultdict(list)
    for r in closed:
        wid = r.get("worker_id") or "unknown"
        inst = r.get("instrument") or "unknown"
        buckets[(wid, inst)].append(r)
    print(f"[f41-mem-replay] {len(buckets)} (worker × instrument) buckets")

    if not args.dry_run:
        MEM_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    workers = set()
    instruments = set()
    for (wid, inst), rows in sorted(buckets.items()):
        mem = build_memory(rows, wid, inst)
        target = MEM_DIR / f"f41__{wid}__{inst}.json"
        s = mem["stats"]
        wr = s["wins"] / max(s["trades_total"], 1)
        print(f"  {target.name:55s}  n={s['trades_total']:4d}  "
              f"wr={wr*100:5.1f}%  pnl={s['total_pnl']:>9.2f}")
        if not args.dry_run:
            target.write_text(json.dumps(mem, indent=2))
        written += 1
        workers.add(wid)
        instruments.add(inst)

    if not args.dry_run:
        stamp(written, len(workers), len(instruments))
        print(f"\n[f41-mem-replay] ✓ wrote {written} files "
              f"({len(workers)} workers × {len(instruments)} instruments)")
        print(f"[f41-mem-replay] F47 stamped kind=f41_memory_replayed")
    else:
        print(f"\n[f41-mem-replay] DRY RUN — no files written")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
