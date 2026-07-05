"""L11 — ATR-based dynamic exits.

TP-Pip proposal + Acer-Cass schema + HQ-Claude ships (Forge silent on this pass).

compute_atr:  Wilder's true-range averaged over `period`.
apply_dynamic_exit:  symmetric stop / take-profit from entry using ATR × multiplier.

Bars are (high, low, close) tuples. All floats.
"""
from __future__ import annotations


def compute_atr(bars: list[tuple[float, float, float]], period: int = 14) -> float:
    """Average True Range.

    True Range for bar i (i >= 1):
        max(H_i - L_i, |H_i - C_{i-1}|, |L_i - C_{i-1}|)
    First bar has no previous close, so TR = H - L.

    Returns 0.0 if fewer than `period` bars are provided (undefined ATR).
    """
    if not bars or len(bars) < period:
        return 0.0
    tr_values: list[float] = []
    prev_close: float | None = None
    for h, l, c in bars:
        if prev_close is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        tr_values.append(tr)
        prev_close = c
    # Wilder's smoothing: start with simple average over `period`, then EMA
    atr = sum(tr_values[:period]) / period
    for tr in tr_values[period:]:
        atr = ((atr * (period - 1)) + tr) / period
    return atr


def apply_dynamic_exit(entry_price: float, atr: float,
                       multiplier: float = 1.5) -> dict:
    """Symmetric stop / take-profit from entry using ATR × multiplier.

    Returns {'stop', 'take_profit', 'atr', 'multiplier', 'range'}.
    Long-side geometry (subtract for stop, add for TP). Short-side is the
    caller's responsibility to invert.
    """
    band = atr * multiplier
    return {
        "stop": entry_price - band,
        "take_profit": entry_price + band,
        "atr": atr,
        "multiplier": multiplier,
        "range": band,
    }


if __name__ == "__main__":
    bars = [
        (10.5, 10.0, 10.3),
        (10.7, 10.2, 10.5),
        (10.9, 10.4, 10.6),
        (11.0, 10.5, 10.8),
        (11.2, 10.6, 11.0),
    ] * 3  # 15 bars, one more than period=14
    atr = compute_atr(bars, period=14)
    exits = apply_dynamic_exit(entry_price=11.0, atr=atr, multiplier=1.5)
    print(f"ATR={atr:.4f}")
    print(f"stop={exits['stop']:.4f}  take_profit={exits['take_profit']:.4f}  range={exits['range']:.4f}")
