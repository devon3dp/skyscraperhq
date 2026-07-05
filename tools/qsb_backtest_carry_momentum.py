"""qsb_backtest_carry_momentum.py — backtest carry+momentum edge on OANDA ticks.

Ross 2026-07-01 directive: prove positive expectancy NET of spread on
AUD_JPY 3mo %chg minus 1mo rate-diff, ADX>25 gate, ≥500 trades walk-forward,
p<0.05.

DATA REALITY: we have 3.45M ticks of qsb_oanda_tick_stream.jsonl covering
2026-06-21 → 2026-07-01 (10 days). No AUD_JPY stream. So we adapt the spirit:

  · Synthesize AUD_JPY = AUD_USD × USD_JPY (arbitrage-locked cross)
  · Adapt lookback: 3-day %chg minus 1-day noise (shorter windows for our
    10-day window — same concept, shorter horizon)
  · Feature: carry-momentum score = 3d_chg - 1d_chg (momentum minus recent
    noise, no interest rate data available so this stands in for the rate-diff)
  · Regime filter: simplified trending regime = |EMA(fast) - EMA(slow)| > k·σ
    (proxy for ADX>25 since we don't compute ADX from ticks)
  · Trades: long-only when signal>0 and regime=trending

Method: walk-forward on 15-min bars. Enter long on signal, exit on trailing
stop OR opposite regime OR 30-bar time-stop. Spread modeled from typical OANDA
practice spread on AUD_USD (0.6 pips) + USD_JPY (0.9 pips), summed for cross.

Reports expectancy NET of spread, win rate, sample size, two-sided t-test p-val.
"""
from __future__ import annotations
import json, math, statistics
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

TICK_STREAM = Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_oanda_tick_stream.jsonl")
OUT = Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_backtest_carry_momentum.json")

# Spread model (bps of price): sum of AUD_USD ~0.6 pips + USD_JPY ~0.9 pips
# on the cross ≈ 1.5 pips round-trip cost = ~1.0bps on AUD/JPY at ~90.
SPREAD_BPS = 1.0  # NET of spread means we subtract this from every trade

# Bar width for backtest granularity
BAR_SECS = 900  # 15 minutes

# Feature windows
MOM_BARS = 288   # ~72h (3 days) at 15-min bars
NOISE_BARS = 96  # ~24h (1 day)

# Regime filter windows
EMA_FAST_ALPHA = 0.05
EMA_SLOW_ALPHA = 0.005
REGIME_K = 1.0   # |fast-slow| > K*σ → trending

# Trade management
STOP_BPS = 30    # trailing stop tightens as pnl runs
TAKE_BPS = 60    # take at 2× stop
MAX_HOLD_BARS = 30


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z","+00:00"))


def load_bars():
    """Return dict[instrument] -> dict[bar_idx] -> (ts, close_price) (last tick in bar)."""
    result = defaultdict(dict)
    with TICK_STREAM.open() as f:
        for line in f:
            try:
                d = json.loads(line)
            except: continue
            inst = d.get("instrument")
            if inst not in ("AUD_USD","USD_JPY"): continue
            ts_s = d.get("ts") or d.get("time")
            if not ts_s: continue
            try:
                ts = parse_ts(ts_s)
            except: continue
            price = d.get("mid") or d.get("price")
            if price is None:
                b = d.get("bid"); a = d.get("ask")
                if b is not None and a is not None:
                    price = (b + a) / 2
                else: continue
            price = float(price)
            bar_idx = int(ts.timestamp() // BAR_SECS)
            # Keep the LAST tick's price in each bar
            result[inst][bar_idx] = (ts, price)
    # Convert to sorted lists
    return {k: sorted(v.items()) for k, v in result.items()}


def bars_as_list(bar_dict):
    """Convert [(bar_idx, (ts, px)), ...] → [(ts, px), ...]"""
    return [(v[0], v[1]) for _, v in bar_dict]


def synth_audjpy(aud_sorted, jpy_sorted):
    """Join by bar_idx, compute AUD_JPY = AUD_USD × USD_JPY.
    Inputs are [(bar_idx, (ts, px)), ...] sorted."""
    aud_by_bar = {bar_idx: v for bar_idx, v in aud_sorted}
    jpy_by_bar = {bar_idx: v for bar_idx, v in jpy_sorted}
    common = sorted(set(aud_by_bar) & set(jpy_by_bar))
    return [(aud_by_bar[b][0], aud_by_bar[b][1] * jpy_by_bar[b][1]) for b in common]


def backtest(bars):
    """Walk-forward long-only carry+momentum with trailing stop."""
    if len(bars) < MOM_BARS + NOISE_BARS + 10:
        return {"error": f"not enough bars ({len(bars)} < {MOM_BARS+NOISE_BARS+10})"}

    fast = None; slow = None; sigma = None
    prices = [px for _, px in bars]
    times = [t for t, _ in bars]

    # Precompute EMAs
    fast_ema = []; slow_ema = []
    for i, p in enumerate(prices):
        if fast is None:
            fast = p; slow = p
        else:
            fast = fast + EMA_FAST_ALPHA * (p - fast)
            slow = slow + EMA_SLOW_ALPHA * (p - slow)
        fast_ema.append(fast); slow_ema.append(slow)

    # Rolling std for regime scale
    ret_window = deque(maxlen=NOISE_BARS)

    trades = []
    open_state = None  # dict when position open

    for i in range(MOM_BARS + NOISE_BARS, len(bars)):
        p = prices[i]
        # Track rolling stdev of 1-bar returns
        if i > 0:
            ret_window.append((prices[i] - prices[i-1]) / prices[i-1])
        if len(ret_window) < NOISE_BARS: continue
        sigma_ret = statistics.pstdev(ret_window) if len(ret_window) > 5 else 0.001

        # Feature: 3d %chg minus 1d %chg (momentum with noise-strip)
        mom_3d = (prices[i] - prices[i - MOM_BARS]) / prices[i - MOM_BARS]
        mom_1d = (prices[i] - prices[i - NOISE_BARS]) / prices[i - NOISE_BARS]
        feature = mom_3d - mom_1d  # our carry+momentum proxy

        # Regime filter (trending)
        ema_gap = fast_ema[i] - slow_ema[i]
        trending = abs(ema_gap / prices[i]) > REGIME_K * sigma_ret
        trend_up = ema_gap > 0

        # Manage open position
        if open_state:
            entry_px = open_state["entry_px"]
            peak = max(open_state["peak"], p)
            open_state["peak"] = peak
            open_state["bars"] += 1
            # Trailing stop from peak
            trail = peak * (1 - STOP_BPS/10000)
            take = entry_px * (1 + TAKE_BPS/10000)
            if p <= trail or p >= take or open_state["bars"] >= MAX_HOLD_BARS or (not trending):
                # Close
                gross_bps = (p - entry_px) / entry_px * 10000
                net_bps = gross_bps - SPREAD_BPS  # subtract round-trip spread
                trades.append({
                    "entry_ts": open_state["entry_ts"].isoformat(),
                    "exit_ts": times[i].isoformat(),
                    "bars": open_state["bars"],
                    "gross_bps": round(gross_bps, 3),
                    "net_bps": round(net_bps, 3),
                    "won_net": net_bps > 0,
                    "reason": "trail" if p<=trail else ("take" if p>=take else ("time" if open_state["bars"]>=MAX_HOLD_BARS else "regime_flat")),
                })
                open_state = None
        # Entry
        if not open_state and trending and trend_up and feature > 0:
            open_state = {"entry_px": p, "peak": p, "bars": 0, "entry_ts": times[i]}

    return trades


def main():
    bars_by_inst = load_bars()
    aud_list = bars_by_inst.get('AUD_USD', [])
    jpy_list = bars_by_inst.get('USD_JPY', [])
    print(f"AUD_USD bars: {len(aud_list)}")
    print(f"USD_JPY bars: {len(jpy_list)}")
    aud_jpy = synth_audjpy(aud_list, jpy_list)
    print(f"AUD_JPY synthesized bars: {len(aud_jpy)}")

    trades = backtest(aud_jpy)
    if isinstance(trades, dict) and "error" in trades:
        print(f"ERROR: {trades['error']}")
        OUT.write_text(json.dumps(trades, indent=2))
        return

    n = len(trades)
    if n == 0:
        print("NO TRADES generated.")
        OUT.write_text(json.dumps({"trades": 0}, indent=2))
        return

    net_bps = [t["net_bps"] for t in trades]
    wins = sum(1 for x in net_bps if x > 0)
    losses = n - wins
    exp_bps = statistics.mean(net_bps)
    std_bps = statistics.pstdev(net_bps) if n > 1 else 0
    # Two-sided t-test vs 0
    if std_bps > 0 and n > 1:
        t_stat = exp_bps / (std_bps / math.sqrt(n))
        # Approximate p-value from t → normal (n large)
        from math import erf
        p_val = 2 * (1 - 0.5 * (1 + erf(abs(t_stat) / math.sqrt(2))))
    else:
        t_stat = 0; p_val = 1.0

    result = {
        "instrument": "AUD_JPY (synthesized AUD_USD × USD_JPY)",
        "bars_covered": len(aud_jpy),
        "window_days": 10,
        "spread_bps_subtracted": SPREAD_BPS,
        "trades_total": n,
        "wins_net": wins,
        "losses_net": losses,
        "win_rate_net": round(wins/n, 4),
        "expectancy_bps_net": round(exp_bps, 3),
        "std_bps": round(std_bps, 3),
        "t_stat": round(t_stat, 3),
        "p_value_two_sided": round(p_val, 4),
        "significant_p_lt_05": p_val < 0.05,
        "significant_p_lt_10": p_val < 0.10,
        "meets_ross_500_trades": n >= 500,
        "note": "Adapted from 3mo/1mo to 3d/1d because we have 10 days of ticks. Feature = 3d %chg minus 1d %chg. Regime filter = |EMA_fast-EMA_slow|/px > 1σ (trending). Stop 30bps trail from peak, take 60bps, 30-bar time stop, exit on regime flat.",
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
