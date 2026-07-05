"""strategy_ta_classic.py — REAL technical analysis signal layer.

Per Ross 2026-06-23 'no coin flips, real intelligent trading design
algorithms if needed': the previous strategies relied on belief math
calibrated from OUR OWN trades (circular). This module reads the actual
PRICE SERIES via the rolling buffer maintained by the trader and applies
classical TA — EMA crossover + RSI confirmation.

Entry rule (long-only for now — short adds later):
  - EMA_FAST(12) crosses ABOVE EMA_SLOW(26)        ← momentum signal
  - RSI(14) < 70 (not overbought)                  ← anti-chase
  - regime_confidence >= 0.4                       ← still gates on belief

Exit rule:
  - EMA_FAST crosses BELOW EMA_SLOW                ← trend reversal
  - OR RSI > 80                                    ← overbought exit
  - OR catastrophic 5σ stop                        ← safety net
  - OR ticks_since_entry >= 30 min-hold first

Interfaces:
  decide_open(belief, recent_prices) -> (bool, reason)
  decide_close(belief, ticks_since_entry, unrealized_pnl, qty, recent_prices)
    -> (bool, reason)

recent_prices is a list of recent mid-prices (last 50-100), oldest first.
"""
from __future__ import annotations
import math


def _ema(prices: list[float], n: int) -> float | None:
    """Exponential moving average. Returns None if insufficient data."""
    if len(prices) < n:
        return None
    k = 2.0 / (n + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = p * k + ema * (1 - k)
    return ema


def _rsi(prices: list[float], n: int = 14) -> float | None:
    """RSI(n). 0-100 scale. None if insufficient data."""
    if len(prices) < n + 1:
        return None
    gains = []
    losses = []
    for i in range(1, n + 1):
        diff = prices[-i] - prices[-(i + 1)]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(-diff)
    avg_gain = sum(gains) / n if gains else 0
    avg_loss = sum(losses) / n if losses else 1e-9
    if avg_loss < 1e-9:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _ema_cross_signal(prices: list[float], fast: int = 12,
                       slow: int = 26) -> int:
    """Returns +1 if fast just crossed above slow (bullish),
    -1 if just crossed below (bearish), 0 otherwise."""
    if len(prices) < slow + 2:
        return 0
    ema_f_now = _ema(prices[-fast:], fast)
    ema_s_now = _ema(prices[-slow:], slow)
    ema_f_prev = _ema(prices[-fast - 1:-1], fast)
    ema_s_prev = _ema(prices[-slow - 1:-1], slow)
    if None in (ema_f_now, ema_s_now, ema_f_prev, ema_s_prev):
        return 0
    if ema_f_now > ema_s_now and ema_f_prev <= ema_s_prev:
        return +1
    if ema_f_now < ema_s_now and ema_f_prev >= ema_s_prev:
        return -1
    return 0


def decide_open(belief: dict, recent_prices: list[float] | None = None) -> tuple[bool, str]:
    """Iter 2: trend-following entry (not just cross moment).
    Enter when EMA_fast > EMA_slow (uptrend) AND RSI in healthy range.
    Crosses happen too rarely to be the only trigger."""
    if not recent_prices or len(recent_prices) < 27:
        return False, "ta_warming_up"
    rc = belief["regime"]["regime_confidence"]
    if rc < 0.4:
        return False, f"low_regime_conf rc={rc:.2f}"
    ema_f = _ema(recent_prices[-12:], 12)
    ema_s = _ema(recent_prices[-26:], 26)
    if ema_f is None or ema_s is None:
        return False, "ta_ema_warming"
    if ema_f <= ema_s:
        return False, "downtrend (ema_f<=ema_s)"
    rsi = _rsi(recent_prices, n=14)
    if rsi is None:
        return False, "ta_rsi_warming"
    if rsi >= 70:
        return False, f"rsi_overbought rsi={rsi:.1f}"
    if rsi <= 30:
        return False, f"rsi_oversold rsi={rsi:.1f}"
    # Optional: avoid entering near recent high (last 5 ticks)
    return True, f"ta_uptrend rsi={rsi:.1f} ema_gap={(ema_f-ema_s):.5f}"


def decide_close(belief: dict, ticks_since_entry: int,
                  unrealized_pnl: float, qty: float = 1.0,
                  recent_prices: list[float] | None = None) -> tuple[bool, str]:
    """Belief-driven catastrophic stop + TA-driven trend exit."""
    ss = belief["regime"]["step_std"]
    if qty <= 0:
        qty = 1.0
    move = unrealized_pnl / qty

    # Catastrophic stop (belief math, always fires)
    if ss > 0 and move < -5 * ss * math.sqrt(max(1, ticks_since_entry)):
        return True, "ta_catastrophic_5sigma"
    # Min-hold (belief-tick based, no clock)
    if ticks_since_entry < 30:
        return False, "ta_hold_min_30"
    # TA trend reversal — exit on bearish cross
    if recent_prices and len(recent_prices) >= 28:
        cross = _ema_cross_signal(recent_prices, fast=12, slow=26)
        if cross == -1:
            return True, "ta_trend_reversal"
        rsi = _rsi(recent_prices, n=14)
        # 80→95 (2026-06-24): RSI=100 fires on pure uptrend (no losses in 14 ticks);
        # was exiting eth_ta on every legit trend → 43% wr. 95 catches only the
        # truly extreme overbought, lets normal uptrends run.
        if rsi is not None and rsi > 95:
            return True, f"ta_rsi_exhausted rsi={rsi:.1f}"
    # Profit-take after warmup if move is meaningful
    if ticks_since_entry > 60 and ss > 0 and move > ss:
        return True, "ta_profit_take"
    return False, "hold"


STRATEGY_NAME = "ta_classic"
