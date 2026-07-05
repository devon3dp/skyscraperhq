#!/usr/bin/env python3
"""qsb_ensemble_coordinator.py — Phase 4 multi-strategy ensemble.

Watches one instrument. On each tick consults ALL 3 strategy modules
(momentum, mean_revert, breakout) against its own belief state. Votes by
weighted majority (each strategy weighted by win_rate). Opens ONE position
per instrument when ≥2 of 3 strategies vote open. Closes on ANY exit vote
(veto pattern).

Team co-write 2026-06-22:
  Wren-fast: coordinator centralizes position-holding, win_rate-weighted,
             subscribes to strategy_vote (we use belief.updated + own ticks)
             Risk: win_rate lag during regime shifts
  Hermes-8b: voting math drafted — unanimous open / any-close veto / weighted
             truthiness. Claude relaxed unanimous to majority-of-3 (else
             rarely opens), kept any-close veto (Hermes's good call),
             replaced truthiness with weighted-conviction threshold.
  Claude:    integrator — built single-instrument daemon, shared-belief
             approach (all 3 strategies decide against same belief; diversity
             comes from decision-rule variation not belief variation).

Per Ross 'no clocks anywhere': bus-event-driven. Exits use should_exit-style
checks, not hold_secs.

CLI:
  --instrument BTCUSDT --venue binance --strategies momentum,mean_revert,breakout
"""
from __future__ import annotations
import argparse, asyncio, json, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))
from qsb_event_subscriber import QSBSubscriber  # noqa: E402
from strategies import STRATEGIES  # noqa: E402
from belief_updater_math import confidence_size_scalar, convergence_gate  # noqa: E402
from qsb_broker_place import place_order as _place_real_order  # noqa: E402

# 2026-06-25 (Ross "yes team !!!!!"): convergence-gate min_dims tunable.
# 3 = strict (trend OR cross_asset must agree on direction).
# 2 = lax (regime + vol can pass alone).
CONVERGENCE_MIN_DIMS = 2  # 2026-06-25 Ross "123": loosened from 3 to 2 for first live run

# Currency lookup for cross_asset peer beliefs.
_CCY_OF = {
    # OANDA fx
    "EUR_USD": ["EUR","USD"], "GBP_USD": ["GBP","USD"], "USD_JPY": ["USD","JPY"],
    "AUD_USD": ["AUD","USD"], "USD_CHF": ["USD","CHF"], "EUR_GBP": ["EUR","GBP"],
    # crypto
    "BTCUSDT": ["BTC","USDT"], "ETHUSDT": ["ETH","USDT"], "BNBUSDT": ["BNB","USDT"],
    "SOLUSDT": ["SOL","USDT"], "ADAUSDT": ["ADA","USDT"], "XRPUSDT": ["XRP","USDT"],
    # equities all USD
    "SPY": ["USD"], "AAPL": ["USD"], "QQQ": ["USD"], "TSLA": ["USD"],
    "NVDA": ["USD"], "MSFT": ["USD"], "DIA": ["USD"], "XLF": ["USD"],
    "GLD": ["USD"], "COIN": ["USD"], "IWM": ["USD"],
}


def _peer_beliefs(instrument: str) -> list[dict]:
    """Load belief states of instruments sharing a currency, excluding self.
    Cheap pass — scans cognitive dir. Returns at most 6 most-recent."""
    cgs = _CCY_OF.get(instrument, [])
    if not cgs:
        return []
    cog = ROOT / "data/registries/cognitive"
    if not cog.exists():
        return []
    out = []
    for f in cog.glob("belief_state_*.json"):
        # filename: belief_state_<worker_id>__<INSTRUMENT>.json
        name = f.stem
        if "__" not in name:
            continue
        peer_inst = name.rsplit("__", 1)[1]
        if peer_inst == instrument:
            continue
        # Share at least one currency?
        peer_ccys = _CCY_OF.get(peer_inst, [])
        if not any(c in peer_ccys for c in cgs):
            continue
        try:
            out.append(json.loads(f.read_text()))
        except Exception:
            continue
        if len(out) >= 6:
            break
    return out

FLOOR_BY_VENUE = {"binance": "F42", "oanda": "F41", "alpaca": "F43"}
BROKER_VENUE = {"binance": "binance_testnet", "oanda": "oanda_practice",
                 "alpaca": "alpaca_paper"}


def belief_file(worker_id: str, instrument: str) -> Path:
    return (ROOT / "data/registries/cognitive"
            / f"belief_state_{worker_id}__{instrument}.json")


def load_belief(worker_id: str, instrument: str) -> dict | None:
    p = belief_file(worker_id, instrument)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def now_loop_time() -> float:
    return asyncio.get_event_loop().time()


class EnsembleCoordinator:
    def __init__(self, instrument: str, venue: str,
                  strategy_names: list[str], sim_units: float) -> None:
        self.instrument = instrument
        self.venue = venue
        self.worker_id = f"ensemble_{instrument.lower().replace('_','')}"
        self.floor = FLOOR_BY_VENUE.get(venue, "F??")
        self.strategies = [(n, STRATEGIES[n]) for n in strategy_names
                            if n in STRATEGIES]
        self.sim_units = sim_units
        self.open_position: dict | None = None
        self.last_tick_price: float | None = None
        self.sub = QSBSubscriber(worker_id=self.worker_id)
        self.last_log_n = 0

    def _collect_open_votes(self, belief: dict) -> list[tuple[str, bool, str]]:
        return [(name, *mod.decide_open(belief))
                for name, mod in self.strategies]

    def _collect_close_votes(self, belief: dict, ticks: int,
                              unrealized: float, qty: float = 1.0) -> list[tuple[str, bool, str]]:
        return [(name, *mod.decide_close(belief, ticks, unrealized, qty))
                for name, mod in self.strategies]

    def _open_decision(self, belief: dict) -> tuple[bool, str, list[str]]:
        """Returns (ok, reason, opener_strategies). The opener list is stored
        on the open_position dict so only those strategies can veto-close it
        (Wren-designed fix 2026-06-22: strategies don't veto trades they
        wouldn't have opened, prevents mean_revert killing momentum trades).

        2026-06-25 PRE-ENTRY CONVERGENCE GATE (Ross "yes team !!!!!" / 3-of-3
        team unanimous: Wren+OpenAI+DeepSeek; Hermes timed out). Require N
        orthogonal dimensions (regime / trend / volatility / cross_asset)
        before letting strategies vote. Filters low-conviction single-signal
        trades."""
        # Stage 1: convergence gate
        peers = _peer_beliefs(self.instrument)
        c_ok, c_reason, c_dims = convergence_gate(belief, peers, side="BUY",
                                                    min_dims=CONVERGENCE_MIN_DIMS)
        self._last_convergence = {"ok": c_ok, "reason": c_reason,
                                   "dims_passed": c_dims,
                                   "peer_count": len(peers)}
        if not c_ok:
            return False, f"convergence_fail:{c_reason}", []
        # Stage 2: existing strategy vote
        votes = self._collect_open_votes(belief)
        yeses = [(n, r) for n, yes, r in votes if yes]
        wr = belief["strategy_fitness"]["win_rate"]
        threshold = len(self.strategies) if wr < 0.3 else 2
        opener_strategies = [n for n, _ in yeses]
        if len(yeses) >= threshold:
            return True, (f"converge[{'+'.join(c_dims)}]+ensemble_"
                          f"{len(yeses)}/{len(self.strategies)}"
                          f"({','.join(opener_strategies)})"), opener_strategies
        return False, f"only {len(yeses)}/{len(self.strategies)} yes (need {threshold})", []

    def _close_decision(self, belief: dict, ticks: int,
                         unrealized: float,
                         opener_strategies: list[str] | None = None,
                         qty: float = 1.0) -> tuple[bool, str]:
        """Only strategies that voted yes-to-open can veto-close. If none
        listed (legacy), fall back to all-vote-veto."""
        if opener_strategies:
            active = [(n, m) for n, m in self.strategies if n in opener_strategies]
        else:
            active = self.strategies
        for name, mod in active:
            yes, reason = mod.decide_close(belief, ticks, unrealized, qty)
            if yes:
                return True, f"veto_by_{name}:{reason}"
        return False, "all_hold"

    async def on_tick(self, event: dict) -> None:
        p = event.get("payload", {})
        if p.get("instrument") != self.instrument:
            return
        price = p.get("price") or p.get("mid") or p.get("bid")
        if not price:
            return
        price = float(price)
        self.last_tick_price = price

        belief = load_belief(self.worker_id, self.instrument)
        if not belief:
            # Borrow the baseline belief if we don't have our own yet
            base = self.instrument.lower().split("_")[0]
            belief = load_belief(f"belief_driven_{base}", self.instrument)
            if not belief:
                return

        if self.open_position:
            entry_px = self.open_position["entry_px"]
            qty = self.open_position.get("qty", self.sim_units)
            unrealized = (price - entry_px) * qty
            ticks = self.open_position.get("ticks_seen_since_entry", 0) + 1
            self.open_position["ticks_seen_since_entry"] = ticks
            close, reason = self._close_decision(
                belief, ticks, unrealized,
                opener_strategies=self.open_position.get("opener_strategies"),
                qty=qty,
            )
            if close:
                await self._close_position(reason=reason, exit_px=price)
            return

        ok, reason, opener_strategies = self._open_decision(belief)
        if ok:
            size_mult = confidence_size_scalar(belief)
            await self._open_position(price, size_mult=size_mult, reason=reason,
                                       opener_strategies=opener_strategies)
        else:
            n = belief["strategy_fitness"]["n_trades"]
            if n != self.last_log_n:
                self.last_log_n = n
                print(f"[{self.worker_id}] not_open: {reason}", flush=True)

    async def _open_position(self, entry_px: float, size_mult: float,
                              reason: str,
                              opener_strategies: list[str] | None = None) -> None:
        qty = self.sim_units * size_mult
        # Real broker placement (gated)
        broker_venue = BROKER_VENUE.get(self.venue)
        broker_result = {"ok": False, "reason": "no_broker_venue_mapping",
                          "broker_order_id": None}
        if broker_venue:
            try:
                broker_result = _place_real_order(
                    broker_venue, self.instrument, "BUY", qty, self.worker_id,
                    ref_price=entry_px)
            except Exception as e:
                broker_result = {"ok": False, "reason": f"exc:{str(e)[:60]}",
                                  "broker_order_id": None}
        # Ross 2026-06-24 "no sims team" — if broker refuses, no fake open.
        if not broker_result["ok"]:
            print(f"[{self.worker_id}] OPEN_REFUSED @ {entry_px} qty={qty} "
                  f"({broker_result.get('reason','?')})", flush=True)
            return
        broker_oid = broker_result["broker_order_id"]
        self.open_position = {"entry_px": entry_px, "opened_t": now_loop_time(),
                              "qty": qty,
                              "opener_strategies": opener_strategies or [],
                              "broker_order_id": broker_oid,
                              "broker_ok": True}
        await self.sub.publish("trade.opened", {
            "floor": self.floor, "worker_id": self.worker_id,
            "venue": self.venue, "instrument": self.instrument,
            "side": "BUY", "qty": qty, "entry_px": entry_px,
            "broker_order_id": broker_oid,
            "broker_ok": True,
            "broker_reason": broker_result.get("reason"),
            "size_mult": size_mult, "reason": reason,
        })
        print(f"[{self.worker_id}] OPEN @ {entry_px} qty={qty} ×{size_mult:.2f}"
              f" — {reason} [REAL]", flush=True)

    async def _close_position(self, reason: str, exit_px: float | None) -> None:
        if not self.open_position:
            return
        entry_px = self.open_position["entry_px"]
        qty = self.open_position.get("qty", self.sim_units)
        broker_was_real = self.open_position.get("broker_ok", False)
        ex = exit_px if exit_px is not None else (self.last_tick_price or entry_px)
        pnl = (ex - entry_px) * qty
        won = pnl > 0
        # Send real SELL if OPEN was real
        close_broker_oid = None; close_broker_ok = False
        if broker_was_real:
            broker_venue = BROKER_VENUE.get(self.venue)
            if broker_venue:
                try:
                    open_oid = str(self.open_position.get("broker_order_id") or "")
                    cr = _place_real_order(broker_venue, self.instrument,
                                            "SELL", qty, self.worker_id,
                                            ref_price=ex, open_order_id=open_oid)
                    close_broker_oid = cr.get("broker_order_id")
                    close_broker_ok = cr["ok"]
                except Exception:
                    pass
        is_real = bool(broker_was_real and close_broker_ok)
        await self.sub.publish("trade.closed", {
            "floor": self.floor, "worker_id": self.worker_id,
            "venue": self.venue, "instrument": self.instrument,
            "exit_px": ex, "pnl": pnl, "won": won, "reason": reason,
            "close_broker_order_id": close_broker_oid,
            "close_broker_ok": close_broker_ok,
            "is_real": is_real,
            "broker_was_real": broker_was_real,
        })
        marker = "REAL" if close_broker_ok else ("SIM_was_real" if broker_was_real else "SIM")
        print(f"[{self.worker_id}] CLOSE @ {ex} pnl={pnl:.4f} won={won} ({reason}) [{marker}]",
              flush=True)
        self.open_position = None

    async def run(self) -> None:
        tick_event = f"market.tick.{self.venue}"
        self.sub.on(tick_event, self.on_tick)
        await self.sub.run(subscriptions=[tick_event])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--instrument", required=True)
    p.add_argument("--venue", required=True,
                   choices=["binance", "oanda", "alpaca"])
    p.add_argument("--strategies", default="momentum,mean_revert,breakout",
                   help="comma-separated strategy names")
    p.add_argument("--sim-units", type=float, default=1.0)
    args = p.parse_args()
    coord = EnsembleCoordinator(
        instrument=args.instrument, venue=args.venue,
        strategy_names=[s.strip() for s in args.strategies.split(",")],
        sim_units=args.sim_units,
    )
    try:
        asyncio.run(coord.run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
