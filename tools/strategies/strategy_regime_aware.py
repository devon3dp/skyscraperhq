"""strategy_regime_aware.py — pick the right tool for the regime.

Ross 2026-07-01 OANDA all-hands directive (Wren verdict): "mean-reversion in
FLAT/ranging regime where we bleed, momentum only in TRENDING."

Classifies the market regime from belief state, then delegates to the
appropriate sub-strategy. This is not a new signal — it's a switching layer
over the two proven strategies (mean_revert + momentum).

Regime classification uses trend-to-noise ratio (|drift| / step_std):
  TRENDING:  drift is a big multiple of typical single-tick noise (>= 0.30σ)
              → directional strategies work, delegate to momentum
  FLAT:      drift is dwarfed by tick noise (< 0.15σ)
              → mean-reversion works, delegate to mean_revert
  MIXED:     between the two → hold cash (avoid spread bleed)

Rationale: US10Y was bleeding because a directional momentum strategy was
running in a flat regime — every open ate the bid/ask spread with no drift to
overcome it. Auto-switching to mean_revert when flat means we only take trades
the strategy is designed for.
"""
from __future__ import annotations

from . import strategy_mean_revert, strategy_momentum

TRENDING_THRESHOLD = 0.30
FLAT_THRESHOLD = 0.15


def _classify_regime(belief: dict) -> str:
    ss = belief["regime"].get("step_std", 0.0)
    drift = belief["regime"].get("mean_retreat", 0.0)
    rc = belief["regime"].get("regime_confidence", 0.0)
    if ss <= 0:
        return "unknown"
    if rc < 0.3:
        return "uncertain"
    ratio = abs(drift) / ss
    if ratio >= TRENDING_THRESHOLD:
        return "trending"
    if ratio < FLAT_THRESHOLD:
        return "flat"
    return "mixed"


def decide_open(belief: dict, recent_prices: list | None = None) -> tuple[bool, str]:
    regime = _classify_regime(belief)
    if regime == "trending":
        ok, reason = strategy_momentum.decide_open(belief)
        return ok, f"regime=trending:{reason}"
    if regime == "flat":
        ok, reason = strategy_mean_revert.decide_open(belief)
        return ok, f"regime=flat:{reason}"
    if regime == "mixed":
        return False, "regime=mixed_hold_cash"
    if regime == "uncertain":
        return False, "regime=uncertain_hold_cash"
    return False, f"regime={regime}"


def decide_close(belief: dict, ticks_since_entry: int,
                  unrealized_pnl: float, qty: float = 1.0) -> tuple[bool, str]:
    regime = _classify_regime(belief)
    if regime == "trending":
        return strategy_momentum.decide_close(belief, ticks_since_entry, unrealized_pnl, qty)
    return strategy_mean_revert.decide_close(belief, ticks_since_entry, unrealized_pnl, qty)


STRATEGY_NAME = "regime_aware"
