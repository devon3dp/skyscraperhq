#!/usr/bin/env python3
"""qsb_belief_updater.py — long-running event-driven belief-updater daemon.

Per Ross 2026-06-21 mandate: intelligence in the skyscraper = calibrated
beliefs updated from streaming evidence. NO timers, NO loops in business
logic — subscribes to the bus and mutates per-worker belief_state files on
events.

Authorship (team co-write):
  Hermes-8b: belief_updater_math.py pure functions
  Wren-fast: glue class skeleton + subscribe-on-bus pattern
  DeepSeek:  belief schema (regime + strategy_fitness + stream_evidence),
             decay-don't-wipe correction, role split for this build
  Claude:    integration — fixed Wren's eval()-load bug, function-name drift,
             event-shape mismatch (workers don't appear in tick payloads;
             ticks broadcast to all workers tracking that instrument).

Subscribes to: market.tick.*, trade.closed, market.regime_shift
Emits:        belief.updated event after each mutation

Per-worker belief file: data/registries/cognitive/belief_state_{worker_id}__{instrument}.json

For v1, the daemon reads a worker→instrument map from a JSON registry. Add
workers there to start tracking their beliefs. No worker is born with a
belief until it appears in the registry.
"""
from __future__ import annotations
import argparse, asyncio, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qsb_event_subscriber import QSBSubscriber  # noqa: E402
from belief_updater_math import (  # noqa: E402
    new_belief, update_on_tick, update_on_trade_closed, update_on_regime_shift,
)
from peer_belief_fusion import (  # noqa: E402
    fuse_peer_belief, peer_reputation_from_chat_board,
)

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
BELIEF_DIR = ROOT / "data/registries/cognitive"
WORKER_REGISTRY = ROOT / "data/registries/qsb_belief_workers.json"
CHAT_BOARD = ROOT / "data/registries/qsb_trader_chat_board.jsonl"


def load_chat_board_tail(n: int = 200) -> list[dict]:
    if not CHAT_BOARD.exists():
        return []
    try:
        lines = CHAT_BOARD.read_text().splitlines()[-n:]
        return [json.loads(ln) for ln in lines if ln.strip()]
    except Exception:
        return []


def load_worker_registry() -> dict:
    """Map worker_id → [instruments]. Default seed if missing."""
    if WORKER_REGISTRY.exists():
        return json.loads(WORKER_REGISTRY.read_text())
    # Seed with the F42 workers that have memory + trade history
    seed = {
        "f42_market_scout": {"venue": "binance", "instruments": ["BTCUSDT"]},
        "f42_spread_watcher": {"venue": "binance", "instruments": ["ETHUSDT"]},
        "crypto_market_scout": {"venue": "binance", "instruments": ["BNBUSDT"]},
    }
    WORKER_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    WORKER_REGISTRY.write_text(json.dumps(seed, indent=2))
    return seed


def belief_path(worker_id: str, instrument: str) -> Path:
    return BELIEF_DIR / f"belief_state_{worker_id}__{instrument}.json"


def load_belief(worker_id: str, instrument: str) -> dict:
    p = belief_path(worker_id, instrument)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return new_belief()


def save_belief(worker_id: str, instrument: str, belief: dict) -> None:
    p = belief_path(worker_id, instrument)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(belief, indent=2))


class BeliefDaemon:
    def __init__(self) -> None:
        self.workers = load_worker_registry()
        # tick_buffer keyed by (worker_id, instrument)
        self.tick_buffers: dict[tuple[str, str], list[float]] = {}
        self.sub = QSBSubscriber(worker_id="belief_updater")

    def _interested_workers(self, instrument: str, venue: str | None = None) -> list[str]:
        out = []
        for wid, cfg in self.workers.items():
            if venue and cfg.get("venue") != venue:
                continue
            if instrument in cfg.get("instruments", []):
                out.append(wid)
        return out

    async def on_tick(self, event: dict) -> str | None:
        payload = event.get("payload", {})
        name = event.get("name", "")
        venue = name.split(".")[-1]  # market.tick.binance → "binance"
        instrument = payload.get("instrument")
        price = payload.get("price") or payload.get("mid") or payload.get("bid")
        ts = payload.get("ts") or event.get("ts")
        if not (instrument and price):
            return None
        for wid in self._interested_workers(instrument, venue):
            buf = self.tick_buffers.setdefault((wid, instrument), [])
            belief = load_belief(wid, instrument)
            update_on_tick(belief, float(price), str(ts), buf)
            save_belief(wid, instrument, belief)
            await self.sub.publish("belief.updated", {
                "worker_id": wid, "instrument": instrument,
                "regime_confidence": belief["regime"]["regime_confidence"],
                "n_trades": belief["strategy_fitness"]["n_trades"],
                "ticks_seen": belief["stream_evidence"]["ticks_seen"],
            })
        return None

    async def on_trade_closed(self, event: dict) -> str | None:
        payload = event.get("payload", {})
        wid = payload.get("worker_id")
        instrument = payload.get("instrument")
        pnl = payload.get("pnl")
        won = payload.get("won")
        if not (wid and instrument and pnl is not None and won is not None):
            return None
        if wid not in self.workers:
            return None
        # Ross 2026-06-24: "traders can't learn from sims". Only REAL broker-placed
        # closes update belief. SIM (rate-limit fallback, balance refusal, etc) is
        # noise that contaminates win_rate and expectancy.
        is_real = payload.get("is_real")
        if is_real is None:
            # Back-compat: legacy events don't have is_real; treat as real
            is_real = True
        # Always record to session_pnl_stop (REAL only counts toward drawdown)
        try:
            from qsb_session_pnl_stop import record_close
            record_close(float(pnl), bool(is_real))
        except Exception:
            pass
        if not is_real:
            return None
        belief = load_belief(wid, instrument)
        update_on_trade_closed(belief, float(pnl), bool(won))
        save_belief(wid, instrument, belief)
        await self.sub.publish("belief.updated", {
            "worker_id": wid, "instrument": instrument,
            "win_rate": belief["strategy_fitness"]["win_rate"],
            "n_trades": belief["strategy_fitness"]["n_trades"],
            "expectancy": belief["strategy_fitness"]["expectancy"],
            "trigger": "trade.closed",
        })
        return None

    async def on_regime_shift(self, event: dict) -> str | None:
        payload = event.get("payload", {})
        instrument = payload.get("instrument")
        new_regime = payload.get("to_regime", "")
        venue = payload.get("venue", "")
        if not instrument:
            return None
        for wid in self._interested_workers(instrument, venue):
            belief = load_belief(wid, instrument)
            update_on_regime_shift(belief, new_regime)
            save_belief(wid, instrument, belief)
            await self.sub.publish("belief.updated", {
                "worker_id": wid, "instrument": instrument,
                "new_regime": new_regime, "trigger": "regime.shift",
            })
        return None

    async def on_peer_belief(self, event: dict) -> None:
        """Cross-worker teaching: when peer A's belief updates from a real
        trigger (tick or trade.closed, not from peer fusion), every OTHER
        worker tracking the same instrument fuses A's belief into theirs."""
        payload = event.get("payload", {})
        peer_wid = payload.get("worker_id")
        instrument = payload.get("instrument")
        trigger = payload.get("trigger", "tick")
        # Anti-cascade: never react to peer_teaching events (we emitted them)
        if trigger == "peer_teaching":
            return
        if not (peer_wid and instrument):
            return
        if peer_wid not in self.workers:
            return  # we don't have peer's full belief on disk
        peer_belief = load_belief(peer_wid, instrument)
        peer_ticks = peer_belief["stream_evidence"]["ticks_seen"]
        peer_n = peer_belief["strategy_fitness"]["n_trades"]
        # Peer is "experienced enough to teach" if EITHER (a) seen 30+ ticks
        # live, OR (b) has 5+ closed trades in its belief. The OR handles the
        # replay-warmed case (n_trades from history, ticks_seen=0).
        if peer_ticks < 30 and peer_n < 5:
            return
        chat = load_chat_board_tail()
        peer_rep = peer_reputation_from_chat_board(chat, peer_wid)
        if peer_rep <= 0:
            return
        for wid, cfg in self.workers.items():
            if wid == peer_wid:
                continue
            if instrument not in cfg.get("instruments", []):
                continue
            own = load_belief(wid, instrument)
            fused = fuse_peer_belief(own, peer_belief, peer_rep)
            save_belief(wid, instrument, fused)
            await self.sub.publish("belief.updated", {
                "worker_id": wid, "instrument": instrument,
                "trigger": "peer_teaching",
                "taught_by": peer_wid, "peer_reputation": round(peer_rep, 3),
                "win_rate": fused["strategy_fitness"]["win_rate"],
            })

    async def run(self) -> None:
        self.sub.on("market.tick.*", self.on_tick)
        self.sub.on("trade.closed", self.on_trade_closed)
        self.sub.on("market.regime_shift", self.on_regime_shift)
        self.sub.on("belief.updated", self.on_peer_belief)
        await self.sub.run(subscriptions=["market.tick.*", "trade.closed",
                                           "market.regime_shift",
                                           "belief.updated"])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.parse_args()
    daemon = BeliefDaemon()
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
