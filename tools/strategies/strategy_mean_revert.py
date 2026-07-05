"""strategy_mean_revert.py — fade extremes.

Open when price is stretched beyond 2σ from local mean (the |mean_retreat|
exceeds 2 * step_std). Bet on snap-back. Exit when price reverts to near mean
OR position holds too long.

Team co-write 2026-06-22:
  Hermes-8b drafted entry as abs(mean_retreat) > 2*step_std (good math)
  Hermes also gated entry on expectancy < -0.5 (BUG — would only trade when
    historically losing, which is anti-mean-revert)
  Wren-fast specified the interface
  Claude integrated — dropped Hermes's expectancy gate, added direction-aware
    exit on reversion to mean (|mr| < 0.5*ss), added time-stop at 200 ticks.
"""
from __future__ import annotations


def decide_open(belief: dict) -> tuple[bool, str]:
    mr = belief["regime"]["mean_retreat"]
    ss = belief["regime"]["step_std"]
    rc = belief["regime"]["regime_confidence"]
    if rc < 0.3:
        return False, "low_regime_confidence"
    if ss < 1e-6:
        return False, "flat_market"
    # Stretched > 2σ → entry
    if abs(mr) < 2 * ss:
        return False, f"not_stretched (|mr|={abs(mr):.5f} < 2σ={2*ss:.5f})"
    # Note: direction is "fade" — if mr > 0 (overbought), short; mr < 0, long.
    # For v1 we always go LONG (simplification), so only fade oversold.
    if mr > 0:
        return False, "mean_revert_v1_only_fades_oversold (would_need_short)"
    return True, f"mean_revert_enter (oversold mr={mr:.5f})"


def decide_close(belief: dict, ticks_since_entry: int,
                  unrealized_pnl: float, qty: float = 1.0) -> tuple[bool, str]:
    """v3 (2026-06-22): dimension-fix — normalize pnl to price-units via /qty."""
    import math
    mr = belief["regime"]["mean_retreat"]
    ss = belief["regime"]["step_std"]
    if qty <= 0:
        qty = 1.0
    move_in_price = unrealized_pnl / qty
    if move_in_price < -5 * ss * math.sqrt(max(1, ticks_since_entry)):
        return True, "mean_revert_catastrophic_5sigma"
    if ticks_since_entry < 30:
        return False, "hold (min_hold_30)"
    if abs(mr) < 0.1 * ss:
        return True, "mean_reverted"
    if move_in_price > ss:
        return True, "mean_revert_profit_lock"
    if mr < -3 * ss:
        return True, "mean_revert_stop_running_against_us"
    if ticks_since_entry > 200:
        return True, "mean_revert_time_stop"
    return False, "hold"


STRATEGY_NAME = "mean_revert"
