#!/usr/bin/env python3
"""qsb_trader_pnl_aggregator_bus.py — event-driven PnL aggregator (Task #34).

Hybrid pair to qsb_trader_pnl_aggregator.py (timer-based broker reconciler).
This module is FAST: it subscribes to `trade.closed` on the event bus and
rewrites the per-worker PnL view on every close. The timer-based one stays
as the slower broker-truth reconciler (OANDA history, Binance account, Alpaca).

Design picked by Wren (hybrid) + Hermes (heartbeat). Producer (belief_driven_trader)
already publishes the right shape — zero changes there.

Writes:
  data/registries/qsb_trader_pnl_bus_latest.json   (atomic rewrite on every event)
  data/registries/qsb_trader_pnl_bus_tail.jsonl    (append: per-close audit row)

Publishes:
  pnl.aggregator.heartbeat   every 30s with last_event_ts + event_count
"""
from __future__ import annotations
import asyncio, datetime, json, os, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qsb_event_subscriber import QSBSubscriber

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
OUT_LATEST = ROOT / "data/registries/qsb_trader_pnl_bus_latest.json"
OUT_TAIL = ROOT / "data/registries/qsb_trader_pnl_bus_tail.jsonl"

HEARTBEAT_S = 30.0


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


class PnLAggregator:
    def __init__(self) -> None:
        self.sub = QSBSubscriber(worker_id="pnl_aggregator_bus")
        self.by_worker: dict[str, dict] = defaultdict(lambda: {
            "closes": 0, "wins": 0, "losses": 0, "pnl_sum": 0.0,
            "real_closes": 0, "sim_closes": 0,
            "venue": None, "instrument": None,
        })
        self.by_venue: dict[str, dict] = defaultdict(lambda: {
            "closes": 0, "pnl_sum": 0.0, "wins": 0,
        })
        self.event_count = 0
        self.last_event_ts: str | None = None
        self.started_at = now_iso()

    async def on_trade_closed(self, ev: dict) -> None:
        p = ev.get("payload", {}) or {}
        worker = p.get("worker_id") or "unknown"
        venue = p.get("venue") or "unknown"
        instrument = p.get("instrument") or ""
        pnl = float(p.get("pnl") or 0.0)
        won = bool(p.get("won"))
        is_real = bool(p.get("close_broker_ok"))

        w = self.by_worker[worker]
        w["closes"] += 1
        w["wins"] += 1 if won else 0
        w["losses"] += 0 if won else 1
        w["pnl_sum"] += pnl
        w["real_closes"] += 1 if is_real else 0
        w["sim_closes"] += 0 if is_real else 1
        w["venue"] = venue
        w["instrument"] = instrument

        v = self.by_venue[venue]
        v["closes"] += 1
        v["pnl_sum"] += pnl
        v["wins"] += 1 if won else 0

        self.event_count += 1
        self.last_event_ts = ev.get("ts") or now_iso()

        # Append tail audit row (per-close)
        OUT_TAIL.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_TAIL, "a") as fh:
            fh.write(json.dumps({
                "ts": self.last_event_ts, "worker_id": worker, "venue": venue,
                "instrument": instrument, "pnl": pnl, "won": won,
                "is_real": is_real, "reason": p.get("reason"),
            }) + "\n")

        # Atomic rewrite of latest snapshot
        self._write_latest()

    def _write_latest(self) -> None:
        snap = {
            "ts": now_iso(),
            "started_at": self.started_at,
            "event_count": self.event_count,
            "last_event_ts": self.last_event_ts,
            "by_worker": {k: dict(v) for k, v in self.by_worker.items()},
            "by_venue": {k: dict(v) for k, v in self.by_venue.items()},
            "totals": {
                "closes": sum(v["closes"] for v in self.by_worker.values()),
                "pnl_sum": sum(v["pnl_sum"] for v in self.by_worker.values()),
                "real_closes": sum(v["real_closes"] for v in self.by_worker.values()),
                "wins": sum(v["wins"] for v in self.by_worker.values()),
            },
        }
        tmp = OUT_LATEST.with_suffix(".json.tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(snap, indent=2, default=str))
        tmp.replace(OUT_LATEST)

    async def heartbeat_loop(self) -> None:
        """Hermes's anti-stall guard: publish heartbeat + event_count every 30s.
        If this stops appearing on the bus, watchdog flags a stall."""
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            if self.sub.writer is None:
                continue
            try:
                await self.sub.publish("pnl.aggregator.heartbeat", {
                    "daemon_pid": os.getpid(),
                    "event_count": self.event_count,
                    "last_event_ts": self.last_event_ts,
                    "uptime_started": self.started_at,
                    "tracked_workers": len(self.by_worker),
                })
            except Exception as e:
                print(f"[{now_iso()}] heartbeat publish failed: {e!r}", flush=True)

    async def run(self) -> None:
        self.sub.on("trade.closed", self.on_trade_closed)
        hb = asyncio.create_task(self.heartbeat_loop())
        try:
            await self.sub.run(subscriptions=["trade.closed"])
        finally:
            hb.cancel()


def main() -> int:
    agg = PnLAggregator()
    print(f"[{now_iso()}] pnl_aggregator_bus starting; "
          f"latest={OUT_LATEST.name} tail={OUT_TAIL.name} heartbeat={HEARTBEAT_S}s",
          flush=True)
    asyncio.run(agg.run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
