"""regime_detector_math.py — pure math for skyscraper regime classification.

NO I/O. Classifies a price window into trend/range/volatile/quiet with a
confidence score 0-1.

Authorship:
  Hermes-8b drafted classify_regime + regime_changed skeletons + 4-regime taxonomy
  Claude integrated, fixed: builtin shadowing (range), inverted-confidence min/max
  bug, t-stat-based slope replacing slope_z_score, volatility-ratio for volatile.

The four skyscraper regimes:
  trend     — directional move (|t-stat of slope| > 2)
  range     — oscillates around mean (low slope, mean-reversions seen)
  volatile  — recent return std >> long-window return std (ratio > 1.5)
  quiet     — low slope AND low volatility
"""
from __future__ import annotations
import math
import statistics


def _ols_slope_tstat(ys: list[float]) -> float:
    """Linear-regression slope t-statistic for y vs index. Higher |t| = stronger trend."""
    n = len(ys)
    if n < 3:
        return 0.0
    xs = list(range(n))
    x_mean = (n - 1) / 2
    y_mean = sum(ys) / n
    num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    slope = num / den
    intercept = y_mean - slope * x_mean
    residuals = [ys[i] - (intercept + slope * xs[i]) for i in range(n)]
    ssr = sum(r ** 2 for r in residuals)
    if ssr == 0 or n <= 2:
        return 0.0
    se = math.sqrt(ssr / (n - 2)) / math.sqrt(den)
    if se == 0:
        return 0.0
    return slope / se


def _returns(prices: list[float]) -> list[float]:
    return [(prices[i] - prices[i - 1]) / prices[i - 1]
            for i in range(1, len(prices)) if prices[i - 1]]


def classify_regime(prices: list[float], min_n: int = 30) -> tuple[str, float]:
    """Return (regime_name, confidence 0-1). 'insufficient_data' if too few prices."""
    if len(prices) < min_n:
        return "insufficient_data", 0.0
    rets = _returns(prices)
    if not rets:
        return "insufficient_data", 0.0

    t_stat = _ols_slope_tstat(prices)
    long_vol = statistics.stdev(rets) if len(rets) >= 2 else 0.0
    recent_n = max(10, len(rets) // 3)
    recent_vol = statistics.stdev(rets[-recent_n:]) if len(rets[-recent_n:]) >= 2 else long_vol
    vol_ratio = (recent_vol / long_vol) if long_vol > 0 else 1.0

    abs_t = abs(t_stat)
    # Score each regime in [0, 1]
    scores = {
        "trend": min(1.0, abs_t / 4.0),               # t=4 → score 1.0
        "volatile": min(1.0, max(0.0, (vol_ratio - 1.0) / 1.0)),  # ratio 2.0 → 1.0
        "range": min(1.0, max(0.0, (2.0 - abs_t) / 2.0) * (1.0 - min(1.0, max(0.0, (vol_ratio - 1.0))))),
        "quiet": min(1.0, max(0.0, (2.0 - abs_t) / 2.0) * (1.0 - min(1.0, recent_vol / 0.002))),
    }
    winner = max(scores, key=scores.get)
    return winner, round(scores[winner], 3)


def regime_changed(prev_regime: str, new_regime: str, new_confidence: float,
                   min_confidence: float = 0.6) -> bool:
    """True iff regime label actually changed AND new_confidence above floor (anti-flap)."""
    if prev_regime == new_regime:
        return False
    return new_confidence >= min_confidence
