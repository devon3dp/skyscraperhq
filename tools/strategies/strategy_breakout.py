"""strategy_breakout.py — enter on regime confidence + ride the trend.

Open when regime_confidence is high (clear regime, post-shift) AND there's
real volatility AND drift confirms direction. Exit when regime decays OR
adverse move beyond 2σ OR trend matures.

Team co-write 2026-06-22:
  Hermes-8b drafted entry as regime_confidence > 0.7 (good signal)
  Hermes added "ticks_since_entry > 30" to ENTER (BUG — that variable only
    exists AFTER opening; can't gate entry on it)
  Wren-fast specified interface
  Claude integrated — removed Hermes's invalid ticks_since_entry from ENTER,
    added drift-confirmation gate (don't enter against the drift), added
    proper stop-loss to EXIT (Hermes had expectancy > 2.0 as exit gate which
    is wrong direction).
"""
from __future__ import annotations


def decide_open(belief: dict) -> tuple[bool, str]:
    mr = belief["regime"]["mean_retreat"]
    ss = belief["regime"]["step_std"]
    rc = belief["regime"]["regime_confidence"]
    # High regime confidence required
    if rc < 0.7:
        return False, f"breakout_needs_rc>=0.7 (have {rc:.2f})"
    if ss < 1e-6:
        return False, "flat_market"
    # We only go LONG in v1; require positive drift to confirm
    if mr <= 0:
        return False, f"breakout_v1_long_only (mr={mr:.5f})"
    return True, f"breakout_enter (rc={rc:.2f} mr={mr:.5f})"


def decide_close(belief: dict, ticks_since_entry: int,
                  unrealized_pnl: float, qty: float = 1.0) -> tuple[bool, str]:
    """v3 (2026-06-22): dimension-fix — normalize pnl to price-units via /qty."""
    import math
    rc = belief["regime"]["regime_confidence"]
    ss = belief["regime"]["step_std"]
    mr = belief["regime"]["mean_retreat"]
    if qty <= 0:
        qty = 1.0
    move_in_price = unrealized_pnl / qty
    if move_in_price < -5 * ss * math.sqrt(max(1, ticks_since_entry)):
        return True, "breakout_catastrophic_5sigma"
    if ticks_since_entry < 30:
        return False, "hold (min_hold_30)"
    if rc < 0.4:
        return True, "breakout_regime_collapsed"
    if mr < 0:
        return True, "breakout_drift_flipped"
    if move_in_price < -2 * ss * math.sqrt(ticks_since_entry):
        return True, "breakout_stop_loss_2sigma"
    if ticks_since_entry > 90 and move_in_price > ss:
        return True, "breakout_profit_lock"
    if ticks_since_entry > 400:
        return True, "breakout_time_stop"
    return False, "hold"


STRATEGY_NAME = "breakout"
