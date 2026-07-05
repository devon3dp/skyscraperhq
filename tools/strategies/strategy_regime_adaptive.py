"""strategy_regime_adaptive.py — regime-aware entry: hold cash / mean-revert in
FLAT regimes, momentum in TRENDING regimes.

WHY (F41/OANDA worst-performer fix, 2026-07-01, quant-engineer parallel agent):
  OANDA lifetime record was 975 trades / 0 wins / 649 losses / -£225.18. Every
  one of those 975 closes was side=BUY (long-only directional). Backtest over
  the real tick history (data/registries/qsb_oanda_tick_stream.jsonl, ~3.36M
  ticks w/ bid+ask) proved the loss is 100% SPREAD BLEED: baseline directional
  expectancy per trade ≈ MINUS the quoted spread on EVERY instrument
  (EUR_USD -0.69bps vs 0.69bps spread; USB10Y_USD -3.0bps vs 2.33bps spread;
  XAU_USD -1.56bps vs 1.55bps spread). Directional entries in a flat/ranging
  market have no edge, so each round trip just pays the spread → structural bleed.

THE FIX (this module — gates EVERY entry on the regime already in belief_state):
  · FLAT / ranging regime  (|drift|/step_std small, i.e. no real trend):
        default = HOLD CASH (proven best: regime-gate took 0 trades on the flat
        bonds USB10Y/UK10Y in backtest → -£13.7/-£162 bleed avoided entirely).
        optional = MEAN-REVERT (fade a statistically oversold dip toward the
        mean with a tight target). Opt-in via FLAT_MODE; long-only so we only
        fade OVERSOLD (buy the dip). NOTE: backtest shows mean-revert lifts
        win-rate 2-15x and cuts total bleed, but does NOT by itself beat the
        spread at tick granularity — hence HOLD CASH is the default.
  · TRENDING-UP regime (drift/step_std above threshold, positive):
        allow the directional/momentum BUY — this is where directional has edge.
  · TRENDING-DOWN regime: refuse (v1 is long-only, can't short the trend).

SCALE-FREE: classification uses the ratio drift/step_std and z-scores of
recent_prices — NOT absolute step_std. This fixes the cross-instrument bug in
the live convergence dim_trend (FLAT_SS_FLOOR=1e-5 absolute), which never
catches a bond priced ~110 (step_std 0.014 ≫ 1e-5) even though it is dead flat
in RELATIVE terms.

DEFENSE IN DEPTH: the trader runs this decide_open AFTER the convergence gate
and ANDs the results, so this module can only make entries STRICTER. That is
exactly what lets it hold cash in flat even when the 3-of-4 convergence quorum
wrongly passes (cross_asset "no_peers_skip" free pass out-votes dim_trend).

Interface matches the other strategy modules (decide_open / decide_close), plus
optional recent_prices kwarg for the mean-revert z-score.

Reason strings for stops/takes deliberately contain "stop_loss" / "take_profit"
so the trader's min-profit close-gate treats them as safety exits and lets them
fire (cut losers fast).
"""
from __future__ import annotations
import math

# ── Tunables ────────────────────────────────────────────────────────────
MIN_REGIME_CONFIDENCE = 0.65   # need a stable regime read before acting
FLAT_RATIO = 0.15              # |drift|/step_std below this ⇒ FLAT/ranging
TREND_RATIO = 0.30            # drift/step_std above this (and >0) ⇒ TREND-UP
FLAT_MODE = "cash"            # "cash" (proven) | "mean_revert" (opt-in)
MR_Z_ENTER = 2.0              # oversold z-score (vs recent_prices) to fade
MR_LOOKBACK = 60             # ticks for the mean-revert z window
MIN_HOLD = 30                # ticks before non-stop exits allowed
# Asymmetric R:R — cut losers fast, let winners run (sigma-scaled).
STOP_SIGMA = 1.5             # stop at -1.5σ·√ticks
TAKE_SIGMA = 3.0             # take at +3.0σ (3:1 vs a 1σ adverse)
STRATEGY_NAME = "regime_adaptive"


def _regime(belief: dict) -> tuple[float, float, float, float]:
    r = belief.get("regime", {})
    drift = float(r.get("mean_retreat", 0.0) or 0.0)
    ss = float(r.get("step_std", 0.0) or 0.0)
    rc = float(r.get("regime_confidence", 0.0) or 0.0)
    ratio = (drift / ss) if ss > 0 else 0.0
    return drift, ss, rc, ratio


def classify(belief: dict) -> str:
    """FLAT | TREND_UP | TREND_DOWN | COLD."""
    drift, ss, rc, ratio = _regime(belief)
    if ss <= 0:
        return "COLD"
    if abs(ratio) < FLAT_RATIO:
        return "FLAT"
    if ratio >= TREND_RATIO:
        return "TREND_UP"
    if ratio <= -TREND_RATIO:
        return "TREND_DOWN"
    # between FLAT_RATIO and TREND_RATIO ⇒ ambiguous, treat as flat (no edge)
    return "FLAT"


def _oversold(recent_prices, z_enter: float) -> tuple[bool, float]:
    if not recent_prices or len(recent_prices) < 20:
        return False, 0.0
    win = list(recent_prices)[-MR_LOOKBACK:]
    m = sum(win) / len(win)
    var = sum((x - m) ** 2 for x in win) / max(1, len(win) - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return False, 0.0
    z = (win[-1] - m) / sd
    return (z < -z_enter), z


def decide_open(belief: dict, recent_prices=None) -> tuple[bool, str]:
    drift, ss, rc, ratio = _regime(belief)
    if ss <= 0:
        return False, "cold_no_volatility"
    if rc < MIN_REGIME_CONFIDENCE:
        return False, f"regime_confidence {rc:.2f}<{MIN_REGIME_CONFIDENCE}"
    regime = classify(belief)
    if regime == "TREND_UP":
        return True, f"trend_up_directional (drift/σ={ratio:.2f})"
    if regime == "TREND_DOWN":
        return False, f"trend_down_long_only_hold (drift/σ={ratio:.2f})"
    # FLAT / ranging ── the loss zone for directional strategies
    if FLAT_MODE == "mean_revert":
        os_hit, z = _oversold(recent_prices, MR_Z_ENTER)
        if os_hit:
            return True, f"flat_mean_revert_fade_oversold (z={z:.2f})"
        return False, f"flat_hold_cash_not_oversold (z={z:.2f})"
    return False, f"flat_hold_cash (drift/σ={ratio:.2f})"


def decide_close(belief: dict, ticks_since_entry: int,
                 unrealized_pnl: float, qty: float = 1.0,
                 recent_prices=None) -> tuple[bool, str]:
    drift, ss, rc, ratio = _regime(belief)
    if qty <= 0:
        qty = 1.0
    move = unrealized_pnl / qty  # signed price-units
    t = max(1, ticks_since_entry)
    # 1) Hard stop — cut losers fast. Fires even inside min-hold. "stop_loss"
    #    keyword ⇒ trader's min-profit gate lets it through.
    if ss > 0 and move < -STOP_SIGMA * ss * math.sqrt(t):
        return True, f"regime_adaptive_stop_loss_{STOP_SIGMA:.1f}sigma"
    # 2) Catastrophic stop (extra safety).
    if ss > 0 and move < -5.0 * ss * math.sqrt(t):
        return True, "regime_adaptive_catastrophic_stop_loss"
    if ticks_since_entry < MIN_HOLD:
        return False, f"hold (min_hold_{MIN_HOLD})"
    # 3) Regime flipped against a long — get out.
    if drift < 0 and abs(ratio) >= TREND_RATIO:
        return True, "regime_adaptive_trend_flipped_take_profit"
    # 4) Let winners run: take at +TAKE_SIGMA.
    if ss > 0 and move > TAKE_SIGMA * ss:
        return True, f"regime_adaptive_take_profit_{TAKE_SIGMA:.1f}sigma"
    # 5) Profit lock after warmup once we clear ~1σ.
    if ticks_since_entry > 90 and ss > 0 and move > ss:
        return True, "regime_adaptive_take_profit_lock"
    # 6) Edge gone.
    if rc < 0.4:
        return True, "regime_adaptive_edge_gone_take_profit"
    # 7) Stale — no signal, small move.
    if ticks_since_entry > 300 and ss > 0 and abs(move) < 0.5 * ss:
        return True, "regime_adaptive_stale_stop_loss"
    return False, "hold"
