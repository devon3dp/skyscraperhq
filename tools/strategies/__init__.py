"""strategies package — diverse decision logic for belief-driven traders.

Each strategy module exports decide_open(belief) and decide_close(belief, ticks, pnl).

Phase 3 (2026-06-22):
  momentum     - follow the drift
  mean_revert  - fade extremes
  breakout     - enter on regime confidence + ride the trend
"""
from __future__ import annotations
from . import strategy_momentum, strategy_mean_revert, strategy_breakout
from . import strategy_ta_classic, strategy_regime_aware
from . import strategy_regime_adaptive

STRATEGIES = {
    "momentum":     strategy_momentum,
    "mean_revert":  strategy_mean_revert,
    "breakout":     strategy_breakout,
    "ta_classic":   strategy_ta_classic,
    "regime_aware": strategy_regime_aware,
    "regime_adaptive": strategy_regime_adaptive,
}

__all__ = ["STRATEGIES"]
