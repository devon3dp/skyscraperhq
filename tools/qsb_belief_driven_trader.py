#!/usr/bin/env python3
"""qsb_belief_driven_trader.py — first intelligent worker that CONSUMES beliefs.

Per Ross 2026-06-21 mandate: a worker that uses its belief_state to decide,
not hardcoded thresholds. Subscribes to market.tick.binance + belief.updated.
Decision rule: if confidence_to_act() returns True and no open position, open.
If open position is older than 60s OR a regime shift fired, close. PnL is
SIMULATED for v1 (no real broker call) so the learning loop can spin up
without real-money risk.

Authorship (team co-write):
  Wren-fast drafted the trader class skeleton + on_market_tick path
  Hermes-8b agreed on simulated-PnL pattern for v1
  Claude    integrated — fixed import path, QSBSubscriber registration pattern
            (it's via .on() not class inheritance), wired full event-shape,
            implemented has_open_position state, real PnL from entry_px delta.

Closing the intelligence loop: trader emits trade.closed → belief_updater
catches it → mutates belief_state via update_on_trade_closed → emits
belief.updated → trader sees its own belief evolve. Pure event-driven.
"""
from __future__ import annotations
import argparse, asyncio, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qsb_event_subscriber import QSBSubscriber  # noqa: E402
from belief_updater_math import (  # noqa: E402
    confidence_to_act, confidence_size_scalar, should_exit, convergence_gate,
)

# 2026-06-25 Convergence gate min_dims (Ross "yes team !!!!!" 4-layer ship).
# 2026-07-01 Ross council WIN-PLAN item 1 (TRADE-LESS): raised 2→3 so only
# 3-of-4 orthogonal dims (regime/trend/volatility/cross_asset) can OPEN.
CONVERGENCE_MIN_DIMS = 3
from strategies import STRATEGIES  # noqa: E402
from qsb_broker_place import place_order as _place_real_order  # noqa: E402

# Map our sim venues to broker_place venue keys.
BROKER_VENUE = {
    "binance": "binance_testnet",
    "oanda":   "oanda_practice",
    "alpaca":  "alpaca_paper",
}

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
# Defaults overridable by CLI flags so the same trader can run as
# belief_driven_btc / belief_driven_eur / belief_driven_spy / etc.
DEFAULT_WORKER_ID = "belief_driven_btc"
DEFAULT_INSTRUMENT = "BTCUSDT"
DEFAULT_VENUE = "binance"
DEFAULT_HOLD_SECS = 60
DEFAULT_SIM_UNITS = 0.0005


def belief_file(worker_id: str, instrument: str) -> Path:
    return ROOT / "data/registries/cognitive" / \
           f"belief_state_{worker_id}__{instrument}.json"


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


FLOOR_BY_VENUE = {"binance": "F42", "oanda": "F41", "alpaca": "F43"}

# Per-worker hourly open cap (Wren + Hermes team design 2026-06-23).
# Derived from broker gate caps / #workers per venue:
#   binance 120/hr ÷ 4 workers = 30, oanda 60/hr ÷ 14 = 12 (rounded down conservatively),
#   alpaca 60/hr ÷ 11 = 20 (rounded up since fewer concurrent positions).
# Stops the rate-limit cycling that produces phantom closes (ETH 9655 / 26 real).
PER_WORKER_HOURLY_CAP = {"binance": 300, "oanda": 200, "alpaca": 150}  # 2026-06-24 raised 10x for fast trading per Ross
RATE_WINDOW_S = 3600


class BeliefDrivenTrader:
    def __init__(self, worker_id: str, venue: str, instrument: str,
                  sim_units: float,
                  strategy: str = "baseline") -> None:
        self.worker_id = worker_id
        self.venue = venue
        self.instrument = instrument
        self.sim_units = sim_units
        self.floor = FLOOR_BY_VENUE.get(venue, "F??")
        self.open_position: dict | None = None
        self.sub = QSBSubscriber(worker_id=worker_id)
        self.last_belief_log_n = 0
        self.last_tick_price: float | None = None  # for regime-shift exit
        # 2026-06-27 V10 — Multi-timeframe filter (Jesse-inspired, 3/3 team).
        # Maintain fast (~5min) and slow (~1h) EMAs of price. Refuse entries
        # when fast & slow disagree on direction. Real tick data only.
        self.mtf_fast_ema: float | None = None
        self.mtf_slow_ema: float | None = None
        self.mtf_fast_prev: float | None = None
        self.mtf_slow_prev: float | None = None
        # alpha tuned for ~8 t/s on binance, ~1 t/s on oanda — rough
        # window length: 2/(alpha*tick_rate) seconds
        # For 8 t/s: 0.003 → 2/(0.003*8) ≈ 83s (close enough to "5min momentum")
        # For 0.0001 alpha: 2/(0.0001*8) ≈ 2500s ≈ 42 min ("1h trend")
        self.mtf_fast_alpha = 0.003
        self.mtf_slow_alpha = 0.0001
        # Phase 3: optional strategy module overrides decide_open/decide_close.
        # "baseline" uses the original confidence_to_act + should_exit path.
        self.strategy_name = strategy
        self.strategy_mod = STRATEGIES.get(strategy)
        # Per-worker self-throttle (team-built 2026-06-23). Trim-and-count on
        # each open attempt. Prevents the rate-limit cycling that bled ETH to
        # 9655 phantom closes (only 26 real) and kept wr at ~25%.
        self._open_timestamps: list[float] = []
        self._hourly_cap = PER_WORKER_HOURLY_CAP.get(venue, 60)
        self._throttle_log_n = 0
        # Rolling price buffer for TA-based strategies (Ross 2026-06-23
        # "real intelligent trading algorithms"). Last 100 mid-prices.
        from collections import deque
        self.recent_prices: deque[float] = deque(maxlen=100)

    def _under_open_cap(self) -> tuple[bool, int]:
        """Return (under_cap, current_count). Trims window in place."""
        now = now_loop_time()
        cutoff = now - RATE_WINDOW_S
        self._open_timestamps = [t for t in self._open_timestamps if t >= cutoff]
        return (len(self._open_timestamps) < self._hourly_cap,
                len(self._open_timestamps))

    async def on_belief_updated(self, event: dict) -> None:
        p = event.get("payload", {})
        if p.get("worker_id") != self.worker_id:
            return

    async def on_regime_shift(self, event: dict) -> None:
        p = event.get("payload", {})
        if p.get("instrument") != self.instrument:
            return
        # Let position breathe — only close on regime_shift if min ticks observed.
        # NO CLOCK: ticks_seen_since_entry replaces held-seconds (Ross 2026-06-23:
        # 'no loops no timers no clocks only intelligent trading').
        if self.open_position:
            ticks = self.open_position.get("ticks_seen_since_entry", 0)
            if ticks >= 15:
                await self._close_position(
                    reason=f"regime_shift_to_{p.get('to_regime')}_ticks_{ticks}",
                    exit_px=None,  # close at market — caller will use last tick price
                )

    async def on_tick(self, event: dict) -> None:
        p = event.get("payload", {})
        if p.get("instrument") != self.instrument:
            return
        price = p.get("price") or p.get("mid") or p.get("bid")
        if not price:
            return
        price = float(price)
        self.last_tick_price = price
        self.recent_prices.append(price)
        # V10 — Multi-timeframe EMA update (Jesse-inspired, 3/3 team).
        # Track fast (~5min) and slow (~1h) EMAs of price for MTF disagreement check.
        if self.mtf_fast_ema is None:
            self.mtf_fast_ema = price
            self.mtf_slow_ema = price
        else:
            self.mtf_fast_prev = self.mtf_fast_ema
            self.mtf_slow_prev = self.mtf_slow_ema
            self.mtf_fast_ema += self.mtf_fast_alpha * (price - self.mtf_fast_ema)
            self.mtf_slow_ema += self.mtf_slow_alpha * (price - self.mtf_slow_ema)

        belief = load_belief(self.worker_id, self.instrument)
        if not belief:
            return

        if self.open_position:
            # Belief-driven exit (replaces clock hold_secs per Ross 2026-06-22).
            # Phase 3 (2026-06-22): if a strategy module is loaded, it owns the
            # exit decision. Otherwise fall back to baseline should_exit.
            entry_px = self.open_position["entry_px"]
            qty = self.open_position.get("qty", self.sim_units)
            unrealized = (price - entry_px) * qty
            ticks = self.open_position.get("ticks_seen_since_entry", 0) + 1
            self.open_position["ticks_seen_since_entry"] = ticks
            # Trailing stop tracking (Wren+Hermes+OpenAI 2026-06-24): peak unrealized
            peak = max(self.open_position.get("peak_unrealized", 0.0), unrealized)
            self.open_position["peak_unrealized"] = peak
            if self.strategy_mod:
                # Pass price buffer to TA-aware strategies (backward-compat:
                # strategies that don't accept it just ignore via **kwargs).
                try:
                    exit_now, reason = self.strategy_mod.decide_close(
                        belief, ticks, unrealized, qty,
                        recent_prices=list(self.recent_prices))
                except TypeError:
                    exit_now, reason = self.strategy_mod.decide_close(
                        belief, ticks, unrealized, qty)
            else:
                exit_now, reason = should_exit(belief, ticks, unrealized, qty,
                                                 venue=self.venue, instrument=self.instrument,
                                                 peak_unrealized=peak)
            if exit_now:
                await self._close_position(reason=reason, exit_px=price)
            return

        # 2026-06-25 PRE-ENTRY CONVERGENCE GATE — Ross "yes team !!!!!".
        # 3-of-3 team (Wren+OpenAI+DeepSeek; Hermes Ollama timeout) unanimous
        # on adopting cryptoteknikal_id/trading-skills approach: require N
        # orthogonal dimensions to agree BEFORE any other entry logic runs.
        c_ok, c_reason, c_dims = convergence_gate(
            belief, peer_beliefs=[], side="BUY",
            min_dims=CONVERGENCE_MIN_DIMS,
        )
        self._last_convergence = {"ok": c_ok, "reason": c_reason,
                                    "dims_passed": c_dims}
        if not c_ok:
            ok, reason = False, f"convergence_fail:{c_reason}"
        # Phase 3: strategy module decide_open OR baseline confidence_to_act.
        # When strategy is loaded, it must approve AND baseline must approve
        # (defense-in-depth — strategy can refine but not bypass cold-start gates).
        elif self.strategy_mod:
            try:
                ok_strat, reason_strat = self.strategy_mod.decide_open(
                    belief, recent_prices=list(self.recent_prices))
            except TypeError:
                ok_strat, reason_strat = self.strategy_mod.decide_open(belief)
            if not ok_strat:
                ok, reason = False, f"{self.strategy_name}:{reason_strat}"
            else:
                ok, reason = confidence_to_act(belief)
                if ok:
                    reason = f"converge[{'+'.join(c_dims)}]+{self.strategy_name}+{reason_strat}"
        else:
            ok, reason = confidence_to_act(belief)
            if ok:
                reason = f"converge[{'+'.join(c_dims)}]+{reason}"
        # V11 — Hard cap: max 200 open positions across fleet (Ross 2026-06-27).
        # Prevents the £1 gate from causing runaway pile-up. Checked via shared pot file.
        if ok:
            try:
                _pot_path = Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_portfolio_pot.json")
                if _pot_path.exists():
                    _pot = json.loads(_pot_path.read_text())
                    _n_open = len(_pot.get("open_positions", {}))
                    if _n_open >= 200:
                        ok = False
                        reason = f"max_open_cap_200({_n_open})"
            except Exception:
                pass
        # V10 — Multi-timeframe disagreement gate (3/3 team consensus, Jesse-inspired).
        # If fast (~5min) and slow (~1h) EMAs disagree on direction, refuse entry.
        # Catches 5min-bullish / 1h-bearish traps. Bypassed during EMA warmup.
        if ok and self.mtf_fast_prev is not None and self.mtf_slow_prev is not None:
            fast_dir = 1 if self.mtf_fast_ema > self.mtf_fast_prev else (-1 if self.mtf_fast_ema < self.mtf_fast_prev else 0)
            slow_dir = 1 if self.mtf_slow_ema > self.mtf_slow_prev else (-1 if self.mtf_slow_ema < self.mtf_slow_prev else 0)
            # Require both moving in same direction (or one neutral). Reject opposite.
            if fast_dir * slow_dir < 0:
                ok = False
                reason = f"mtf_disagree(5m={fast_dir:+d} vs 1h={slow_dir:+d})"
        if ok:
            # Per-worker self-throttle (team-built fix 2026-06-23). Skip the
            # open entirely if this worker has already hit its hourly cap —
            # avoids the rate-limit cycling that bled WR.
            under, n_window = self._under_open_cap()
            if not under:
                if self._throttle_log_n != n_window:
                    self._throttle_log_n = n_window
                    print(f"[{self.worker_id}] self_throttle "
                          f"({n_window}/{self._hourly_cap}/hr — skip)",
                          flush=True)
                return
            size_mult = confidence_size_scalar(belief)
            # 2026-06-25 throttle fix (DeepSeek-team-signed): timestamp now
            # appended INSIDE _open_position AFTER successful broker placement,
            # so OPEN_REFUSED doesn't count toward 200/hr cap.
            await self._open_position(price, size_mult=size_mult)
        else:
            n = belief["strategy_fitness"]["n_trades"]
            if n != self.last_belief_log_n:
                self.last_belief_log_n = n
                print(f"[{self.worker_id}] not acting: {reason}", flush=True)

    async def _open_position(self, entry_px: float, size_mult: float = 1.0) -> None:
        qty = self.sim_units * size_mult
        # 2026-07-01 STALL-FIX Ross: pre-check Binance min-notional before hitting
        # broker. Win-plan probation ×0.5 + fitness ×0.4 was shrinking cheap-alt
        # positions (ADA/SOL/DOT etc.) below Binance's ~$5-10 notional filter,
        # causing 228 broker_400_code-1013 refuses/session that spammed the API.
        # If we know the notional will fail, hold the position instead.
        if self.venue == "binance":
            notional_usd_est = qty * entry_px
            BINANCE_MIN_NOTIONAL_USD = 10.5  # $5-10 filter + safety cushion
            if notional_usd_est < BINANCE_MIN_NOTIONAL_USD:
                # Silently skip — don't spam broker or log. Wait for size_mult
                # to grow (fitness+probation gates) or price to move enough.
                if not hasattr(self, "_min_notional_log_last") or (now_loop_time() - self._min_notional_log_last) > 300:
                    print(f"[{self.worker_id}] HOLD notional=${notional_usd_est:.2f}<${BINANCE_MIN_NOTIONAL_USD} "
                          f"(qty={qty}, wait for size_mult growth)", flush=True)
                    self._min_notional_log_last = now_loop_time()
                return
        # REAL BROKER placement (gate-checked; refuses if disabled, rate-limited, etc).
        broker_venue = BROKER_VENUE.get(self.venue)
        broker_result = {"ok": False, "reason": "no_broker_venue_mapping",
                          "broker_order_id": None}
        # Broker-side stop / take distances (2026-06-24 Ross). Price-units distance.
        # For OANDA: stop_distance moves trigger to broker side — eliminates event-loop
        # slippage past trigger. Calculated to cap loss at ~£2.50 GBP per trade.
        # stop_distance_in_price = (max_loss_gbp / qty / fx_quote_to_gbp)
        stop_dist = 0.0
        take_dist = 0.0
        if broker_venue == "oanda_practice":
            # Conservative defaults; instrument-specific overrides:
            # JPY pair: quote=JPY, fx≈0.0053. 2.50 / 500 / 0.0053 ≈ 0.94 JPY
            # USD pair: quote=USD, fx≈0.80. 2.50 / 500 / 0.80 ≈ 0.00625
            # GBP pair (quote=GBP). 2.50 / 500 / 1.0 ≈ 0.005
            quote_ccy_map = {"USD_JPY":"JPY", "EUR_USD":"USD", "GBP_USD":"USD",
                              "AUD_USD":"USD", "USD_CHF":"CHF", "EUR_GBP":"GBP",
                              "XAU_USD":"USD", "XAG_USD":"USD",
                              "SPX500_USD":"USD", "NAS100_USD":"USD"}
            fx_to_gbp = {"GBP":1.0, "USD":0.80, "EUR":0.85, "JPY":0.0053, "CHF":0.90}
            quote = quote_ccy_map.get(self.instrument, "USD")
            rate = fx_to_gbp.get(quote, 0.80)
            # 2026-07-01 WIN-PLAN item 3 ASYMMETRIC — stop £2.50→£1.50, take £4.00→£4.50
            # R:R was 4.00/2.50 = 1.6:1 → now 4.50/1.50 = 3.0:1. Trailing 0.55×hw
            # (from 2026-07-01 earlier ship) lets winners still run past take.
            stop_dist = 1.50 / max(qty, 1) / rate  # £1.50 cap (tight)
            take_dist = 4.50 / max(qty, 1) / rate  # £4.50 target (wide)
        if broker_venue:
            try:
                broker_result = _place_real_order(
                    broker_venue, self.instrument, "BUY", qty, self.worker_id,
                    ref_price=entry_px,
                    stop_distance=stop_dist, take_distance=take_dist)
            except Exception as e:
                broker_result = {"ok": False, "reason": f"exc:{str(e)[:60]}",
                                  "broker_order_id": None}
        # Ross 2026-06-24 "no sims team" — if broker refuses, no fake open.
        # Trade simply doesn't happen. Worker waits for next signal.
        if not broker_result["ok"]:
            print(f"[{self.worker_id}] OPEN_REFUSED @ {entry_px} qty={qty} "
                  f"({broker_result.get('reason','?')})", flush=True)
            return
        # 2026-06-25 throttle fix: only count SUCCESSFUL opens toward 200/hr cap.
        self._open_timestamps.append(now_loop_time())
        broker_oid = broker_result["broker_order_id"]
        self.open_position = {"entry_px": entry_px, "opened_t": now_loop_time(),
                              "qty": qty, "broker_order_id": broker_oid,
                              "broker_ok": True}
        await self.sub.publish("trade.opened", {
            "floor": self.floor, "worker_id": self.worker_id, "venue": self.venue,
            "instrument": self.instrument, "side": "BUY",
            "qty": qty, "entry_px": entry_px,
            "broker_order_id": broker_oid,
            "broker_ok": True,
            "broker_reason": broker_result.get("reason"),
            "size_mult": size_mult,
        })
        print(f"[{self.worker_id}] OPEN @ {entry_px} qty={qty} (REAL)", flush=True)

    async def _close_position(self, reason: str, exit_px: float | None) -> None:
        if not self.open_position:
            return
        entry_px = self.open_position["entry_px"]
        qty = self.open_position.get("qty", self.sim_units)
        broker_was_real = self.open_position.get("broker_ok", False)
        ex = exit_px if exit_px is not None else (self.last_tick_price or entry_px)
        pnl = (ex - entry_px) * qty
        # 2026-06-27 Ross + team 3/3 (DSK+OAI+Wren): minimum-profit gate.
        # Don't close unless pnl >= £1 GBP OR safety stop fires OR position held >= 4h.
        # Estimate pnl in GBP by quote-currency fx conversion (rough).
        _QUOTE_FX_TO_GBP = {
            "GBP": 1.0, "USD": 0.80, "EUR": 0.85, "JPY": 0.0053,
            "CHF": 0.90, "AUD": 0.52, "NZD": 0.48, "USDT": 0.80,
        }
        _QUOTE_BY_INST = {
            "GBP_USD":"USD","EUR_USD":"USD","AUD_USD":"USD","USD_JPY":"JPY",
            "USD_CHF":"CHF","EUR_GBP":"GBP","EUR_JPY":"JPY","GBP_JPY":"JPY",
            "AUD_JPY":"JPY","CHF_JPY":"JPY","XAU_USD":"USD","XAG_USD":"USD",
            "SPX500_USD":"USD","NAS100_USD":"USD","US30_USD":"USD","DE30_EUR":"EUR",
            "JP225_USD":"USD","NATGAS_USD":"USD","WTICO_USD":"USD","BCO_USD":"USD",
            "WHEAT_USD":"USD","XCU_USD":"USD","USB10Y_USD":"USD","UK10YB_GBP":"GBP",
        }
        # For Binance USDT pairs + Alpaca stocks: quote is USDT/USD
        if self.venue in ("binance", "alpaca"):
            quote_ccy = "USD"
        else:
            quote_ccy = _QUOTE_BY_INST.get(self.instrument, "USD")
        fx_to_gbp = _QUOTE_FX_TO_GBP.get(quote_ccy, 0.80)
        pnl_gbp_est = pnl * fx_to_gbp
        # Safety reasons that bypass the £1 gate (we still want stops to fire)
        _SAFETY_KW = ("abs_stop", "ccy_max_loss", "oanda_stop", "broker_stop",
                      "take_profit", "stop_distance", "tp_hit", "broker_force",
                      "max_loss", "stop_loss")
        is_safety = any(k in (reason or "").lower() for k in _SAFETY_KW)
        age_secs = now_loop_time() - self.open_position.get("opened_t", now_loop_time())
        MAX_HOLD_SECS = 4 * 3600  # 4h cap before force-close
        # 2026-06-30 ThinkPad-CEO sign-off thinkpad-00054 — relative gate.
        # Was max(£1, 0.7×high_water): on £10 notional that needs 9% move → frozen forever.
        # Now: max(£0.10, 0.4% × notional, 0.7 × high_water). Scales with position size.
        notional_gbp_abs = abs(float(self.open_position.get("notional_gbp", 0.0)))
        hw = float(self.open_position.get("hw_pnl_gbp", 0.0))
        if pnl_gbp_est > hw:
            self.open_position["hw_pnl_gbp"] = pnl_gbp_est
            hw = pnl_gbp_est
        min_profit_floor = max(0.10, 0.004 * notional_gbp_abs)
        # 2026-07-01 RUN WINNERS — Ross-council recommendation. Audit showed avg
        # winner £0.20 vs avg loser £0.55 → R:R 0.36:1 (too tight). Loosen the
        # early-scalp trail so small winners can develop into medium winners
        # instead of locking at first pullback:
        #   hw < £1.00: 0.55×hw (was 0.70 — allow 45% give-back, was 30%)
        #   £1 ≤ hw < £3: 0.80×hw (was 0.85 — slightly more room)
        #   hw ≥ £3.00: 0.92×hw (unchanged — milk big wins)
        if hw < 1.0:
            trail_floor = hw * 0.55
        elif hw < 3.0:
            trail_floor = hw * 0.80
        else:
            trail_floor = hw * 0.92
        effective_floor = max(min_profit_floor, trail_floor)
        if not is_safety and pnl_gbp_est < effective_floor and age_secs < MAX_HOLD_SECS:
            # HOLD — wait for ≥relative gate or stop or 4h timeout
            if not hasattr(self, "_min_gate_log_last") or (now_loop_time() - self._min_gate_log_last) > 30:
                print(f"[{self.worker_id}] CLOSE_HELD pnl_est=£{pnl_gbp_est:.3f}"
                      f"<floor£{effective_floor:.2f} hw£{hw:.2f} "
                      f"age={int(age_secs)}s reason_was={reason}", flush=True)
                self._min_gate_log_last = now_loop_time()
            return
        if not is_safety and pnl_gbp_est < effective_floor:
            # 4h timeout — force close but mark it
            reason = f"min_profit_gate_timeout({reason})"
        won = pnl > 0
        # If the OPEN was real on broker, send a real SELL to close.
        close_broker_oid = None
        close_broker_ok = False
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
        # is_real = open AND close both placed real broker orders (Ross 2026-06-24:
        # "traders can't learn from sims" — belief_updater filters on this)
        is_real = bool(broker_was_real and close_broker_ok)
        await self.sub.publish("trade.closed", {
            "floor": self.floor, "worker_id": self.worker_id, "venue": self.venue,
            "instrument": self.instrument, "exit_px": ex,
            "pnl": pnl, "won": won, "reason": reason,
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
        self.sub.on("belief.updated", self.on_belief_updated)
        self.sub.on("market.regime_shift", self.on_regime_shift)
        self.sub.on(tick_event, self.on_tick)
        await self.sub.run(subscriptions=["belief.updated",
                                           "market.regime_shift",
                                           tick_event])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--worker-id", default=DEFAULT_WORKER_ID)
    p.add_argument("--venue", default=DEFAULT_VENUE,
                   choices=["binance", "oanda", "alpaca"])
    p.add_argument("--instrument", default=DEFAULT_INSTRUMENT)
    # --hold-secs accepted but IGNORED for backward compatibility with the spawn
    # scripts. Exits are belief-driven (no clocks per Ross 2026-06-23).
    p.add_argument("--hold-secs", type=int, default=0,
                    help="DEPRECATED: ignored — exits are belief-driven.")
    p.add_argument("--sim-units", type=float, default=DEFAULT_SIM_UNITS)
    p.add_argument("--strategy", default="baseline",
                    choices=["baseline", "momentum", "mean_revert", "breakout", "ta_classic", "regime_aware", "regime_adaptive"],
                    help="Decision logic module. ta_classic = EMA crossover + RSI "
                         "(real TA signal beyond belief math). Others = belief-based.")
    args = p.parse_args()
    trader = BeliefDrivenTrader(
        worker_id=args.worker_id, venue=args.venue, instrument=args.instrument,
        sim_units=args.sim_units, strategy=args.strategy,
    )
    try:
        asyncio.run(trader.run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
