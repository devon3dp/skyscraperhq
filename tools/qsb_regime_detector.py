#!/usr/bin/env python3
"""qsb_regime_detector.py — event-driven regime detector daemon.

Subscribes to market.tick.* on the bus. Maintains a per-(venue, instrument)
price deque of last 100 prices. After each tick re-classifies regime. When
the regime LABEL changes AND new confidence >= 0.6, emits a market.regime_shift
event back on the bus. NO timers, NO sleep loops.

Authorship (team co-write):
  Hermes-8b: regime_detector_math.py classification skeleton
  Wren-fast: daemon glue skeleton + price-deque pattern
  Claude:    integration — fixed subscriber API drift, async dispatch, multi-
             instrument support (Wren's draft handled only one).
"""
from __future__ import annotations
import argparse, asyncio, sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qsb_event_subscriber import QSBSubscriber  # noqa: E402
from regime_detector_math import classify_regime, regime_changed  # noqa: E402


SHIFT_COOLDOWN_S = 60.0   # min seconds between regime_shifts per instrument
HYSTERESIS_DELTA = 0.10   # new regime must beat prev confidence by this much


class RegimeDaemon:
    def __init__(self) -> None:
        # per (venue, instrument) → deque of last 100 prices
        self.windows: dict[tuple[str, str], deque[float]] = {}
        # per (venue, instrument) → last (regime, confidence, ts_loop_time)
        self.last_regime: dict[tuple[str, str], tuple[str, float, float]] = {}
        self.sub = QSBSubscriber(worker_id="regime_detector")

    async def on_tick(self, event: dict) -> None:
        payload = event.get("payload", {})
        name = event.get("name", "")
        venue = name.split(".")[-1]  # market.tick.binance → "binance"
        instrument = payload.get("instrument")
        price = payload.get("price") or payload.get("mid") or payload.get("bid")
        if not (instrument and price):
            return
        key = (venue, instrument)
        buf = self.windows.setdefault(key, deque(maxlen=100))
        buf.append(float(price))
        if len(buf) < 30:
            return  # need enough data
        regime, conf = classify_regime(list(buf))
        prev_regime, prev_conf, prev_ts = self.last_regime.get(key, ("none", 0.0, 0.0))
        if not regime_changed(prev_regime, regime, conf):
            return
        # Anti-flap: enforce cooldown AND hysteresis (new must clearly beat prev)
        now_t = asyncio.get_event_loop().time()
        if prev_ts and (now_t - prev_ts) < SHIFT_COOLDOWN_S:
            return
        if prev_regime != "none" and conf < prev_conf + HYSTERESIS_DELTA:
            return
        await self.sub.publish("market.regime_shift", {
            "venue": venue, "instrument": instrument,
            "from_regime": prev_regime, "to_regime": regime,
            "confidence": conf,
        })
        self.last_regime[key] = (regime, conf, now_t)

    async def run(self) -> None:
        self.sub.on("market.tick.*", self.on_tick)
        await self.sub.run(subscriptions=["market.tick.*"])


def main() -> int:
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    try:
        asyncio.run(RegimeDaemon().run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
