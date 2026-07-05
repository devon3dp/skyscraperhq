"""strategy_momentum.py — follow the drift.

Open when price is drifting up with some volatility (real movement, not flat).
Exit when drift flips OR price has run AND we're in profit OR we're underwater
beyond 2σ.

Team co-write 2026-06-22:
  Hermes-8b drafted entry/exit conditions
  Wren-fast specified the (signal, reason) interface — float signal kept for
    future refactor, currently using bool
  Claude integrated — fixed Hermes's overtight win_rate gate (would have never
    fired at cold-start wr=0.4), added downside stop on MOMENTUM_EXIT (Hermes
    only had upside profit-lock, no stop-loss), used step_std-relative stop
    so it scales per instrument.
"""
from __future__ import annotations


def decide_open(belief: dict) -> tuple[bool, str]:
    mr = belief["regime"]["mean_retreat"]
    ss = belief["regime"]["step_std"]
    rc = belief["regime"]["regime_confidence"]
    if rc < 0.3:
        return False, "low_regime_confidence"
    if ss < 1e-6:
        return False, "flat_market_no_volatility"
    if mr <= 0:
        return False, "drift_not_positive"
    return True, f"momentum_enter (mr={mr:.5f} ss={ss:.5f})"


def decide_close(belief: dict, ticks_since_entry: int,
                  unrealized_pnl: float, qty: float = 1.0) -> tuple[bool, str]:
    """v3 (2026-06-22): Wren min-hold + Hermes intent + Claude dimension-fix.
    Normalizes unrealized_pnl into PRICE-UNITS via /qty so the threshold can be
    expressed in step_std (price-per-tick) terms regardless of instrument size.
    """
    import math
    mr = belief["regime"]["mean_retreat"]
    ss = belief["regime"]["step_std"]
    if qty <= 0:
        qty = 1.0
    move_in_price = unrealized_pnl / qty  # signed price-units of move
    # Catastrophic 5σ stop in price units — overrides min-hold
    if move_in_price < -5 * ss * math.sqrt(max(1, ticks_since_entry)):
        return True, "momentum_catastrophic_5sigma"
    if ticks_since_entry < 30:
        return False, "hold (min_hold_30)"
    if mr < 0:
        return True, "momentum_drift_flipped"
    if move_in_price < -3 * ss * math.sqrt(ticks_since_entry):
        return True, "momentum_stop_loss_3sigma"
    if ticks_since_entry > 60 and move_in_price > ss:
        return True, "momentum_profit_lock"
    if ticks_since_entry > 300 and abs(move_in_price) < ss:
        return True, "momentum_stale"
    return False, "hold"


STRATEGY_NAME = "momentum"
