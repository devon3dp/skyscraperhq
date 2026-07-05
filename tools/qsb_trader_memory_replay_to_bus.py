#!/usr/bin/env python3
"""qsb_trader_memory_replay_to_bus.py — warm up beliefs from existing history.

Per team consensus 2026-06-21 (Wren+Hermes+DeepSeek 3/3): before tomorrow's
markets open we must replay closed_trades from data/registries/trader_memory/
into the bus as synthetic trade.closed events. belief_updater will pick them
up and warm beliefs; peer teaching then propagates from F42 workers (rich
history) to belief_driven_btc, etc.

Authorship:
  Hermes-8b drafted the iterate/parse/publish/throttle skeleton
  Claude integrated — fixed: literal-text-as-Python registry check, sync/async
                       drift, F41 filename parsing (f41__worker__instrument.json),
                       venue inference table, main() async runner.

NOT a daemon. One-shot. Exits when done.
"""
from __future__ import annotations
import argparse, asyncio, glob, json, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))
from qsb_event_subscriber import QSBSubscriber  # noqa: E402

MEMORY_DIR = ROOT / "data/registries/trader_memory"
REGISTRY = ROOT / "data/registries/qsb_belief_workers.json"


def parse_worker_and_instrument(path: Path, doc: dict) -> tuple[str | None, str | None]:
    """Return (worker_id, instrument) from JSON doc + filename fallback."""
    worker_id = doc.get("worker_id")
    instrument = doc.get("instrument")
    if worker_id and instrument:
        return worker_id, instrument
    # F41 filename pattern: f41__worker_id__INSTRUMENT.json
    name = path.stem  # filename without .json
    parts = name.split("__")
    if len(parts) >= 3:
        worker_id = worker_id or parts[1]
        instrument = instrument or parts[2]
        return worker_id, instrument
    return worker_id, instrument


def venue_for(worker_id: str) -> tuple[str, str]:
    """Return (floor, venue) by worker_id prefix."""
    if worker_id.startswith("f42_") or worker_id.startswith("crypto_"):
        return "F42", "binance"
    if worker_id.startswith("f41_") or worker_id.startswith("f41__"):
        return "F41", "oanda"
    if worker_id.startswith("f43_"):
        return "F43", "alpaca"
    return "??", "unknown"


async def replay(throttle_s: float = 0.02) -> dict:
    sub = QSBSubscriber(worker_id="memory_replay")
    bus_task = asyncio.create_task(sub.run(subscriptions=["_noop_"]))
    # Wait for bus connect
    for _ in range(30):
        await asyncio.sleep(0.1)
        if sub.writer:
            break
    if not sub.writer:
        return {"error": "failed_to_connect_bus"}

    registry = json.loads(REGISTRY.read_text())
    tracked = set(registry.keys())

    stats = {"files_scanned": 0, "events_published": 0,
             "workers_warmed": set(), "files_skipped": 0}

    for f in sorted(MEMORY_DIR.glob("*.json")):
        stats["files_scanned"] += 1
        try:
            doc = json.loads(f.read_text())
        except Exception:
            stats["files_skipped"] += 1
            continue
        worker_id, instrument = parse_worker_and_instrument(f, doc)
        if not (worker_id and instrument):
            stats["files_skipped"] += 1
            continue
        if worker_id not in tracked:
            stats["files_skipped"] += 1
            continue
        floor, venue = venue_for(worker_id)
        closed = doc.get("closed_trades", [])
        for t in closed:
            payload = {
                "floor": floor, "worker_id": worker_id, "venue": venue,
                "instrument": instrument,
                "exit_px": t.get("exit_px"),
                "pnl": float(t.get("pnl", 0) or 0),
                "won": bool(t.get("won", False)),
                "reason": "replay_from_trader_memory_history",
            }
            await sub.publish("trade.closed", payload)
            stats["events_published"] += 1
            stats["workers_warmed"].add(worker_id)
            if throttle_s > 0:
                await asyncio.sleep(throttle_s)

    bus_task.cancel()
    try:
        await bus_task
    except Exception:
        pass

    stats["workers_warmed"] = sorted(stats["workers_warmed"])
    return stats


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--throttle-s", type=float, default=0.02,
                   help="seconds between events (0 = full speed)")
    args = p.parse_args()
    stats = asyncio.run(replay(args.throttle_s))
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
