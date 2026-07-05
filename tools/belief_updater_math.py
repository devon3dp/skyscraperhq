"""belief_updater_math.py — pure math for skyscraper belief updates.

NO I/O, NO bus calls. Pure functions over belief dicts. Per Ross 2026-06-21
mandate: intelligence = calibrated beliefs updated from stream evidence.

Authorship:
  Hermes-8b drafted the four function skeletons + EWMA + expectancy formulas
  Claude integrated, fixed bugs: typo (beliefs vs belief), missing math import,
  regime_shift wipe-instead-of-decay, regime_confidence formula correction.

Schema (per DeepSeek's design):
  {
    "regime": {"mean_retreat": 0.0, "step_std": 0.0, "regime_confidence": 0.0},
    "strategy_fitness": {"win_rate": 0.0, "expectancy": 0.0, "n_trades": 0},
    "stream_evidence": {"last_tick_ts": "", "ticks_seen": 0}
  }
"""
from __future__ import annotations
import math


def new_belief() -> dict:
    return {
        "regime": {"mean_retreat": 0.0, "step_std": 0.0, "regime_confidence": 0.0},
        "strategy_fitness": {"win_rate": 0.0, "expectancy": 0.0, "n_trades": 0},
        "stream_evidence": {"last_tick_ts": "", "ticks_seen": 0},
    }


def update_on_tick(belief: dict, tick_price: float, tick_ts: str,
                    tick_buffer: list[float]) -> dict:
    """Update belief from a single market tick. tick_buffer is mutated in place
    (caller maintains the last-100 window per worker/instrument)."""
    belief["stream_evidence"]["ticks_seen"] += 1
    belief["stream_evidence"]["last_tick_ts"] = tick_ts
    tick_buffer.append(tick_price)
    if len(tick_buffer) > 100:
        tick_buffer.pop(0)
    if len(tick_buffer) >= 2:
        deltas = [tick_buffer[i] - tick_buffer[i - 1] for i in range(1, len(tick_buffer))]
        mean = sum(deltas) / len(deltas)
        belief["regime"]["mean_retreat"] = mean
        if len(deltas) >= 2:
            var = sum((d - mean) ** 2 for d in deltas) / (len(deltas) - 1)
            belief["regime"]["step_std"] = math.sqrt(var)
    # regime_confidence rises with ticks_seen, capped at 1.0
    belief["regime"]["regime_confidence"] = min(
        belief["stream_evidence"]["ticks_seen"] / 100.0, 1.0
    )
    return belief


def update_on_trade_closed(belief: dict, pnl: float, won: bool,
                            alpha: float = 0.15) -> dict:
    """EWMA on win_rate, running mean on expectancy, increment n_trades.

    2026-06-24 (Ross "traders must learn from wins AND losses"): alpha 0.03→0.15.
    Old: a single loss moved WR by 3% — too slow to adapt to regime change.
    New: 15% means recent N trades dominate; trader recognizes streaks within
    ~5-10 closes (was 30-50). Symmetric — wins lift WR equally fast.
    """
    prev_wr = belief["strategy_fitness"]["win_rate"]
    belief["strategy_fitness"]["win_rate"] = alpha * (1.0 if won else 0.0) + (1 - alpha) * prev_wr
    n = belief["strategy_fitness"]["n_trades"]
    prev_exp = belief["strategy_fitness"]["expectancy"]
    belief["strategy_fitness"]["expectancy"] = (prev_exp * n + pnl) / (n + 1)
    belief["strategy_fitness"]["n_trades"] = n + 1
    return belief


def update_on_regime_shift(belief: dict, new_regime: str, decay: float = 0.5) -> dict:
    """Decay old beliefs — don't wipe. New regime means old edge is less reliable
    but we don't throw it away (DeepSeek's correction to Hermes's first draft)."""
    belief["regime"]["regime_confidence"] *= decay
    belief["strategy_fitness"]["expectancy"] *= decay
    # Keep win_rate, n_trades — strategy fitness in prior regime is still info
    return belief


def confidence_to_act(belief: dict, min_n_trades: int = 0,
                       min_win_rate: float = 0.42,
                       min_regime_confidence: float = 0.65) -> tuple[bool, str]:
    """Decision query — would a worker holding this belief trade now?

    2026-07-01 Ross council WIN-PLAN item 1 (TRADE-LESS): thresholds raised
    from wr>=0.35→0.42 + rc>=0.4→0.65 so only high-conviction, regime-aligned
    setups pass. Combined with CONVERGENCE_MIN_DIMS 2→3 in the trader
    (3-of-4 orthogonal dims required), this materially cuts churn.
    """
    n = belief["strategy_fitness"]["n_trades"]
    wr = belief["strategy_fitness"]["win_rate"]
    rc = belief["regime"]["regime_confidence"]
    if n < min_n_trades:
        return False, f"too few trades ({n}<{min_n_trades})"
    # 2026-06-29 cold-start grace (fixes Alpaca silence): brand-new traders
    # (n==0) cannot have a non-zero win_rate yet, so skip the wr check on
    # their very first trade. Once they have any history (n>0), the normal
    # gates apply. Regime confidence still required.
    if n == 0:
        if rc < min_regime_confidence:
            return False, f"cold_start regime_confidence {rc:.2f} below {min_regime_confidence}"
        return True, f"cold_start_first_trade (rc={rc:.2f})"
    if wr < min_win_rate:
        return False, f"win_rate {wr:.2%} below {min_win_rate:.0%}"
    if rc < min_regime_confidence:
        return False, f"regime_confidence {rc:.2f} below {min_regime_confidence}"
    return True, f"act (n={n} wr={wr:.2%} rc={rc:.2f})"


def confidence_size_scalar(belief: dict, target_win_rate: float = 0.55,
                             floor: float = 0.10) -> float:
    """Kelly-ish belief-driven sizing (Wren design + Hermes regime-gate
    2026-06-23). Multiplier 0.1..2.0 — winners can scale UP, losers shrink.
    Pure belief math: NO CLOCKS, NO LOOPS, NO TIMERS.

    2026-07-01 Ross council WIN-PLAN items 2+4+5 (uncertainty/fitness/prove):
      · UNCERTAINTY-GATED (Wren): × 1/(1 + 20·step_std) — high-vol regime shrinks
      · FITNESS CAPITAL (Hermes): +25% when expectancy>£0.10 & n>=20;
                                  −60% when expectancy<0 (dud shrink)
      · PROVE-EDGE-FIRST: × 0.5 while n<20 (probation half-size)

    Inputs (all from belief state):
      wr  = strategy_fitness.win_rate
      rc  = regime.regime_confidence
      n   = strategy_fitness.n_trades
      exp = strategy_fitness.expectancy
      ss  = regime.step_std  (bigger = more uncertain)
    """
    sf = belief["strategy_fitness"]
    rg = belief["regime"]
    wr  = sf["win_rate"]
    rc  = rg["regime_confidence"]
    n   = sf["n_trades"]
    exp = sf.get("expectancy", 0.0)
    ss  = rg.get("step_std", 0.0)
    if target_win_rate <= 0:
        return 1.0
    if wr >= target_win_rate:
        kelly = min(2.0, 1.0 + (wr - target_win_rate) * 4)
    else:
        kelly = max(floor, wr / target_win_rate)
    regime_gate = max(0.3, min(1.0, rc * 1.5))
    kelly *= regime_gate
    sample_dampen = min(1.0, n / 20.0)
    mult = 1.0 + sample_dampen * (kelly - 1.0)
    # WIN-PLAN item 2 — UNCERTAINTY-GATED: shrink when step_std is large.
    # Typical calm step_std ~0.001; choppy ~0.05. 20·0.05=1.0 → half size.
    mult *= 1.0 / (1.0 + 20.0 * max(0.0, ss))
    # WIN-PLAN item 4 — FITNESS CAPITAL: reward positive-expectancy workers,
    # shrink duds. Needs at least 20 trades to matter (avoids over-reaction).
    if n >= 20:
        if exp > 0.10:
            mult *= 1.25
        elif exp < 0.0:
            mult *= 0.40
    # WIN-PLAN item 5 — PROVE-EDGE-FIRST: half size while in probation (n<20).
    if n < 20:
        mult *= 0.5
    # Global floor so we never open zero-size.
    return max(0.05, mult)


# Per-venue stop multiplier (Wren 2026-06-23 vol-adjusted stops — Hermes approved,
# Ross sign-off). Crypto's realized vol runs ~2-3× FX; US equities ~20% above.
# Multiplies the 2σ stop band so crypto traders aren't stopped out on normal vol.
# OANDA (FX/metals/indices) stays at 1.0 — was already winning at 70% wr.
VENUE_STOP_MULT = {"binance": 1.8, "oanda": 1.0, "alpaca": 1.8}  # 2026-07-01 Ross OANDA-strategy directive: widen alpaca 1.2→1.8 (equity intraday noise higher than we were tolerating)
# 2026-06-24 Wren+Hermes decouple — profit_take no longer rides stop_mult
# 2026-06-24 DeepSeek B — tighten 1.5→0.5σ for scalping; multi-tier trail handles bigger runs.
DEFAULT_PROFIT_TAKE_MULT = 1.0  # 1.5→0.5 (too tight) → 1.0 (2026-06-24: scalp 0.5 fired before multi-tier could build peak; BTC 93.5pct wr but -£0.53 from £0.01 wins vs £0.40 losses)
PROFIT_TAKE_MULT = {
    "USD_JPY": 1.8,   # high wr but small wins — extend
    "EUR_USD": 1.5,
    "GBP_USD": 1.5,
    "BTCUSDT": 1.2,   # crypto fast — moderate
    "ETHUSDT": 1.2,
}
VENUE_MIN_HOLD = {"binance": 45, "oanda": 30, "alpaca": 30}  # extended for crypto
# ★ HARD ABSOLUTE-£ LOSS CAP per trade (Ross 2026-06-23 — the "winning move").
# Data showed 15 OANDA stop_loss_2sigma trades dumped £240 (avg -£16 each).
# These were JPY 1.68× Kelly positions hitting 2σ adverse moves. Each one wiped
# 50 typical profit_locks. Hard cap stops the "one trade kills the book" pattern.
# Fires even within min_hold (like catastrophic).
MAX_ABS_LOSS_PER_TRADE = {
    "binance": 0.35,   # 0.50→0.35 (2026-07-01 win-plan item 3 ASYMMETRIC — cut losers tight)
    "oanda":   1.50,   # 2.50→1.50 (2026-07-01 win-plan item 3 ASYMMETRIC)
    "alpaca":  2.00,   # 3.00→2.00 (2026-07-01 win-plan item 3 ASYMMETRIC)
}
# Per-instrument override (2026-06-23, Ross "max wins kill losses"):
# Workers with HIGH wr but NEGATIVE PnL = small wins, big losses (asymmetric).
# Tightening stop locks more wins per session. JPY keeps 1.0× to let trends breathe.
PER_INSTRUMENT_STOP_MULT = {
    "EUR_USD": 0.8,   # 64% wr but -£2.37 — tighten
    "GBP_USD": 0.8,   # 74% wr but -£0.96 — tighten
    "USD_JPY": 1.0,   # 76% wr +£142 — leave room, working
    "AUD_USD": 0.9,
    "USD_CHF": 0.9,
    "EUR_GBP": 0.9,
}
# ROLLBACK 2026-06-23 13:15Z: wr-scaled profit-take BACKFIRED.
# Original intent: let high-wr workers "run winners" by raising threshold to 1.5×.
# Actual effect: JPY (76% wr, +£142) gave back £64 because it held through reversals.
# Lesson: high-wr means SIGNAL quality is good, but EACH TRADE still needs to lock
# discipline. Don't conflate per-worker wr with per-trade hold time.
# Reverted to neutral 1.0 across the board. Per-instrument stops below stay.
def _profit_take_wr_scale(wr: float) -> float:
    return 1.0   # neutral — let stop_mult do the asymmetry


def should_exit(belief: dict, ticks_since_entry: int,
                 unrealized_pnl: float, qty: float = 1.0,
                 venue: str = "oanda", instrument: str = "",
                 peak_unrealized: float = 0.0) -> tuple[bool, str]:
    """Belief-driven exit replacing hold_secs clock. v3 dimension-fix
    (2026-06-22): unrealized_pnl normalized by qty to compare in price-units
    against step_std (price-per-tick). Min-hold prevents hair-trigger exits.
    Catastrophic 5σ stop overrides min-hold.

    v4 vol-adjusted (2026-06-23 Wren design, Hermes review, Ross sign-off):
    stop band + min-hold scale by venue volatility multiplier.
    """
    import math
    rc = belief["regime"]["regime_confidence"]
    wr = belief["strategy_fitness"]["win_rate"]
    exp = belief["strategy_fitness"]["expectancy"]
    ss = belief["regime"]["step_std"]
    if qty <= 0:
        qty = 1.0
    move_in_price = unrealized_pnl / qty

    # Vol-adjusted parameters (Wren design) + per-instrument override (2026-06-23)
    stop_mult = VENUE_STOP_MULT.get(venue, 1.0)
    if instrument in PER_INSTRUMENT_STOP_MULT:
        stop_mult = PER_INSTRUMENT_STOP_MULT[instrument]
    min_hold = VENUE_MIN_HOLD.get(venue, 30)
    # Catastrophic stop scales too (still triggers on extreme moves)
    catastrophic_sigma = 5 * stop_mult
    # Profit-take threshold — DECOUPLED from stop_mult 2026-06-24 (Wren+Hermes:
    # tightening stop_mult was also shrinking wins → 2.4× asymmetric losses on JPY).
    # Now scales by a separate PROFIT_TAKE_MULT (per-instrument can override).
    # Default 1.5× — wins reach further; losses still capped by abs_stop + 2σ stop_loss.
    pt_mult = PROFIT_TAKE_MULT.get(instrument, DEFAULT_PROFIT_TAKE_MULT)
    profit_take_thresh = ss * pt_mult * _profit_take_wr_scale(wr)

# ★ HARD ABSOLUTE-£ STOP — kills "one trade wipes 50 wins" pattern.
    # Fires even within min_hold. Tested via unrealized_pnl (not move_in_price)
    # because we cap actual money loss, not price-units.
    abs_cap = MAX_ABS_LOSS_PER_TRADE.get(venue, 5.0)
    if unrealized_pnl <= -abs_cap:
        return True, f"abs_stop_{abs_cap:.2f}"
    # CATASTROPHIC stop — fires even within min-hold
    if ss > 0 and move_in_price < -catastrophic_sigma * ss * math.sqrt(max(1, ticks_since_entry)):
        return True, f"catastrophic_{int(catastrophic_sigma)}sigma"
    # SCALP FAST EXIT (2026-06-24 OpenAI A): if peak > £0.20 already and we're past
    # 5 ticks, allow exits — don't wait for full min_hold. Captures fast scalp wins.
    if peak_unrealized >= 0.20 and ticks_since_entry >= 5:
        pass  # skip min_hold guard, fall through to other exits
    elif ticks_since_entry < min_hold:
        return False, f"hold (min_hold_{min_hold})"
    # ★ WINNING EQUATION (Ross 2026-06-23): fix the R:R asymmetry.
    #
    # JPY analysis showed: 76% wr but R:R=0.17 (losses 6× wins). The trades
    # held too long, gave back gains, exited as losses. Fix exit discipline:
    #
    # 1. TRAILING BREAKEVEN — once trade has been in 1σ profit, exit at break-even
    #    or better. NEVER let a winner turn into a loser.
    if ss > 0 and move_in_price > 0 and ticks_since_entry >= min_hold + 20:
        # peak-tracking proxy: if we're now within 0.3σ of break-even but were
        # previously in profit, lock breakeven
        # (cheap heuristic since we don't track running max — use small +
        # band as "lock at break-even when trade fading")
        if 0 <= move_in_price < 0.3 * ss:
            return True, "trail_breakeven_lock"
    # ★ MULTI-TIER EXIT (2026-06-24 R&D panel unanimous: Hermes+OpenAI+DeepSeek E).
    # Replaces single 25% trail (slipped £1-£4 to fast adverse moves). 3 tiers:
    #   peak >= £0.50 → breakeven anchor (once trade hit +£0.50, NEVER close at loss)
    #   peak >= £1.00 → lock 80% of peak (exit if unrealized < peak × 0.80)
    #   peak >= £2.00 → lock 90% of peak (exit if unrealized < peak × 0.90)
    # The breakeven anchor is the key — it prevents the slippage-past-trail pattern
    # because any prior-winner can never realize a loss.
    if peak_unrealized >= 2.00:
        if unrealized_pnl < peak_unrealized * 0.90:
            return True, f"trail_90pct_peak_{peak_unrealized:.2f}"
    elif peak_unrealized >= 1.00:
        if unrealized_pnl < peak_unrealized * 0.80:
            return True, f"trail_80pct_peak_{peak_unrealized:.2f}"
    elif peak_unrealized >= 0.50:
        if unrealized_pnl <= 0:
            return True, f"breakeven_anchor_peak_{peak_unrealized:.2f}"
    # 2. Profit-take: lock the gain faster (0.5σ trigger, was 1σ)
    if wr > 0.55 and move_in_price > profit_take_thresh:
        return True, "profit_take"
    # 3. Stop-loss: vol-adjusted, sqrt-scaled with time. 2026-07-02 Ross OANDA:
    # exit geometry, not win-rate — widen 2σ→3σ so 3-tick noise doesn't fire
    # the stop (ETH was hitting stop_loss_3.6sigma at t≈3 ticks post-open,
    # cutting winners before they had time to work).
    if ss > 0 and move_in_price < -3 * stop_mult * ss * math.sqrt(ticks_since_entry):
        return True, f"stop_loss_{3*stop_mult:.1f}sigma"
    # 4. Edge gone: regime confidence collapsed
    if rc < 0.4:
        return True, "edge_gone"
    # 5. Profit lock after warmup
    if ticks_since_entry > 60 and move_in_price > profit_take_thresh:
        return True, "profit_lock"
    # 6. Stale — FASTER (was 600 ticks, now 300 — was eating big drifts)
    if ticks_since_entry > 300 and ss > 0 and abs(move_in_price) < 0.5 * ss:
        return True, "stale_no_signal"
    # 7. ★ TIME-BOXED EXIT: if held > 200 ticks AND in any profit, lock it.
    if ticks_since_entry > 200 and ss > 0 and move_in_price > 0:
        return True, "time_boxed_profit_lock"
    return False, "hold"


# ──────────────────────────────────────────────────────────────────────
# CONVERGENCE GATE (2026-06-25, Ross "yes team !!!!!")
#
# Per cryptoteknikal_id TikTok demo of roman-rr/trading-skills approach:
# require N orthogonal dimensions to AGREE before any open. Filters out
# low-conviction single-signal trades. 3-of-3 team unanimous (Wren designed,
# OpenAI+DeepSeek concurred; Hermes Ollama timeout). DeepSeek wrote helpers,
# Claude fixed schema (step_std + ticks_seen are nested, not top-level).
# ──────────────────────────────────────────────────────────────────────

def dim_regime(belief: dict) -> tuple[bool, str]:
    """Regime stability gate. True if regime_confidence >= 0.4."""
    rc = belief.get("regime", {}).get("regime_confidence", 0.0)
    if rc >= 0.4:
        return True, f"rc={rc:.2f}"
    return False, f"rc={rc:.2f}<0.4"


def dim_trend(belief: dict, side: str = "BUY") -> tuple[bool, str]:
    """Directional drift agrees with side. 2026-07-01 Ross OANDA directive —
    drift threshold raised 0.10σ→0.30σ so flat/ranging regimes stop bleeding
    spread on false-directional opens (US10Y-style: tiny step_std, no real
    trend, but drift dances above 0.10σ noise floor).
    No-vol = cold stream = block. No-drift-in-flat = hold cash."""
    r = belief.get("regime", {})
    drift = r.get("mean_retreat", 0.0)
    ss = r.get("step_std", 0.0)
    if ss <= 0:
        return False, "no_vol_block"
    # Flat-regime cash-hold: if step_std below floor AND drift near-zero,
    # refuse regardless of side. Ranging markets kill directional strategies.
    FLAT_SS_FLOOR = 1e-5  # extreme flat (like GBP/USD 0.00001 seen in audit)
    if ss < FLAT_SS_FLOOR and abs(drift) < ss:
        return False, f"flat_regime_hold_cash(ss={ss:.6f})"
    thresh = 0.30 * ss  # was 0.10σ — tighter now
    if side == "BUY":
        ok = drift > thresh
        return ok, f"drift={drift:.5f}{'>' if ok else '<='}{thresh:.5f}"
    ok = drift < -thresh
    return ok, f"drift={drift:.5f}{'<' if ok else '>='}{-thresh:.5f}"


def dim_volatility(belief: dict) -> tuple[bool, str]:
    """Sane volatility band — neither collapsed (regime-dead) nor cold-stream."""
    ticks = belief.get("stream_evidence", {}).get("ticks_seen", 0)
    ss = belief.get("regime", {}).get("step_std", 0.0)
    if ticks < 30:
        return False, f"cold_stream({ticks}<30)"
    if ss <= 0:
        return False, "vol_collapsed"
    return True, f"ss={ss:.5f}@{ticks}t"


def dim_cross_asset(belief: dict, peer_beliefs: list[dict],
                    side: str = "BUY") -> tuple[bool, str]:
    """At least one correlated peer agrees on direction. Own drift must agree
    with side first (we won't BUY into our own DOWN). No-peers + own-agrees =
    skip-pass (can't fully judge but at least direction matches)."""
    our = belief.get("regime", {}).get("mean_retreat", 0.0)
    if our == 0:
        return True, "drift_zero_skip"
    expected = 1 if side == "BUY" else -1
    our_sign = 1 if our > 0 else -1
    if our_sign != expected:
        return False, f"own_wrong_sign({our_sign})"
    if not peer_beliefs:
        return True, "no_peers_skip"
    for peer in peer_beliefs:
        pd = peer.get("regime", {}).get("mean_retreat", 0.0)
        if pd == 0:
            continue
        if (1 if pd > 0 else -1) == expected:
            return True, f"peer_agree({pd:.5f})"
    return False, f"no_peer_agrees_side={side}"


def convergence_gate(belief: dict, peer_beliefs: list[dict] | None = None,
                     side: str = "BUY",
                     min_dims: int = 2) -> tuple[bool, str, list[str]]:
    """Quorum: 4 orthogonal dimensions vote. Returns (ok, reason, dims_passed)."""
    peer_beliefs = peer_beliefs or []
    results = [
        ("regime", *dim_regime(belief)),
        ("trend", *dim_trend(belief, side)),
        ("volatility", *dim_volatility(belief)),
        ("cross_asset", *dim_cross_asset(belief, peer_beliefs, side)),
    ]
    passed = [name for name, ok, _ in results if ok]
    failed = [f"{name}({r})" for name, ok, r in results if not ok]
    if len(passed) >= min_dims:
        return True, f"converge_{len(passed)}of4[{'+'.join(passed)}]", passed
    return False, f"only_{len(passed)}of4 missing[{','.join(failed)}]", passed
