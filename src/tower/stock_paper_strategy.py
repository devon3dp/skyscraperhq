#!/usr/bin/env python3
"""
QSB Tower V1.3 — Floor 43 Stock Paper Strategy Lab V1

Phase: FLOOR_43_CONNECTED_STOCK_EXCHANGE_FLOOR_V1

Reads stock floor market data via StockGateway (Alpaca or stub) and
produces paper-only signal observations.

Signal modes: observe, long_bias, short_bias, no_trade.

Hard contract:
- No real orders. No paper orders. No practice orders.
- Stale, missing, wide-spread, closed-market or insufficient-history data
  always degrades to observe or no_trade.
"""

from pathlib import Path
from datetime import datetime, timezone
import json

from tower.stock_exchange_floor import StockGateway, LOCKED_FALSE


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/stock_paper_strategy_lab.jsonl"

POLICY_PATH = REG / "stock_floor_policy.json"
LATEST_PATH = REG / "stock_paper_strategy_latest.json"


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_log(record):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _bar_metrics(bars):
    """
    Compute conservative metrics from a list of bar dicts. Alpaca bar shape:
      {"t": "...", "o": .., "h": .., "l": .., "c": .., "v": .., "vw": ..}
    Falls back to other field name variants if shape differs.
    """
    if not bars or len(bars) < 4:
        return None
    closes = []
    for b in bars:
        if not isinstance(b, dict):
            continue
        c = _to_float(b.get("c") or b.get("close") or b.get("ClosePrice"))
        if c is not None:
            closes.append(c)
    if len(closes) < 4:
        return None
    last = closes[-1]
    ref_3  = closes[-4]
    ref_10 = closes[-11] if len(closes) >= 11 else closes[0]
    ref_20 = closes[-21] if len(closes) >= 21 else closes[0]

    def pct(a, b):
        if not a or not b:
            return None
        return ((a - b) / b) * 100.0

    # Simple volatility proxy: rolling stdev pct on last 20 closes.
    window = closes[-20:] if len(closes) >= 20 else closes
    mean = sum(window) / len(window)
    var = sum((c - mean) ** 2 for c in window) / max(1, len(window) - 1)
    stdev = var ** 0.5
    vol_pct = (stdev / mean) * 100.0 if mean else None

    return {
        "last_close": last,
        "candles_used": len(closes),
        "momentum_3_pct":  pct(last, ref_3),
        "momentum_10_pct": pct(last, ref_10),
        "momentum_20_pct": pct(last, ref_20),
        "volatility_pct":  vol_pct,
    }


def _classify(symbol, quote, bar_metrics, market_status):
    """
    Conservative paper-only stock heuristic. Never a trade recommendation.
    Tags: observe | long_bias | short_bias | no_trade.
    """
    bid = _to_float((quote or {}).get("bp") or (quote or {}).get("bid_price") or (quote or {}).get("bid"))
    ask = _to_float((quote or {}).get("ap") or (quote or {}).get("ask_price") or (quote or {}).get("ask"))
    last = (bar_metrics or {}).get("last_close")
    mid = None
    spread_pct = None

    if bid is not None and ask is not None and ask > 0:
        mid = (bid + ask) / 2
        spread = ask - bid
        ref = last or mid
        if ref:
            spread_pct = (spread / ref) * 100.0

    detail = {
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "last": last,
        "spread_pct": spread_pct,
        "momentum_3_pct":  (bar_metrics or {}).get("momentum_3_pct"),
        "momentum_10_pct": (bar_metrics or {}).get("momentum_10_pct"),
        "momentum_20_pct": (bar_metrics or {}).get("momentum_20_pct"),
        "volatility_pct":  (bar_metrics or {}).get("volatility_pct"),
        "candles_used":    (bar_metrics or {}).get("candles_used"),
        "market_status":   market_status,
    }

    if market_status not in ("open",):
        return "observe", "market_not_open ({})".format(market_status or "unknown"), detail
    if bid is None or ask is None:
        return "no_trade", "missing_quote", detail
    if spread_pct is not None and spread_pct > 0.5:
        return "no_trade", "wide_spread", detail
    if not bar_metrics:
        return "observe", "insufficient_bars", detail

    mom_10 = detail["momentum_10_pct"]
    mom_20 = detail["momentum_20_pct"]
    mom_3  = detail["momentum_3_pct"]
    vol_pct = detail["volatility_pct"]

    if vol_pct is not None and vol_pct > 5.0:
        return "no_trade", "volatility_pct > 5%", detail
    if mom_10 is None or mom_20 is None:
        return "observe", "insufficient kline history", detail

    if mom_10 > 0.3 and mom_20 > 0.5 and (mom_3 is None or mom_3 > -0.1):
        return "long_bias", "upward momentum across 10 and 20 bar windows", detail
    if mom_10 < -0.3 and mom_20 < -0.5 and (mom_3 is None or mom_3 < 0.1):
        return "short_bias", "downward momentum across 10 and 20 bar windows", detail
    return "observe", "no aligned momentum pattern", detail


class StockPaperStrategyLab:
    def __init__(self, provider_override=None):
        self.policy = load_json(POLICY_PATH, {})
        self.gateway = StockGateway(provider_override=provider_override)

    def run(self, symbols=None):
        if symbols is None:
            symbols = self.policy.get("default_symbols") or [
                "AAPL", "MSFT", "NVDA", "TSLA", "SPY", "QQQ"
            ]
        if isinstance(symbols, str):
            symbols = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        else:
            symbols = [s.strip().upper() for s in symbols if s and s.strip()]

        market_status, _ = self.gateway.provider.market_status()
        # Snapshot quotes + latest bars
        data, snap_errors = self.gateway.provider.snapshot_symbols(symbols)
        quotes = (data or {}).get("quotes") or {}
        latest_bars = (data or {}).get("bars") or {}

        results = []
        counts = {"observe": 0, "long_bias": 0, "short_bias": 0, "no_trade": 0}
        for sym in symbols:
            errors = list(snap_errors) if snap_errors else []
            quote = quotes.get(sym) or {}
            # If a single latest bar is present, fold it in; otherwise try recent bars.
            bar_metrics = None
            try:
                bars = self.gateway.provider.recent_bars(sym, timeframe="5Min", limit=40)
                bar_metrics = _bar_metrics(bars)
            except Exception as exc:
                errors.append("recent_bars: {}".format(str(exc)[:200]))

            signal, reason, detail = _classify(sym, quote, bar_metrics, market_status)
            counts[signal] = counts.get(signal, 0) + 1

            results.append({
                "symbol": sym,
                "ok": True if not errors else False,
                "errors": errors,
                "paper_signal": signal,
                "paper_direction": (
                    "paper_long_bias" if signal == "long_bias"
                    else "paper_short_bias" if signal == "short_bias"
                    else "no_trade" if signal == "no_trade"
                    else "flat_observation"
                ),
                "paper_reason": reason,
                "bid": detail.get("bid"),
                "ask": detail.get("ask"),
                "mid": detail.get("mid"),
                "last": detail.get("last"),
                "spread_pct": detail.get("spread_pct"),
                "momentum_3_pct":  detail.get("momentum_3_pct"),
                "momentum_10_pct": detail.get("momentum_10_pct"),
                "momentum_20_pct": detail.get("momentum_20_pct"),
                "volatility_pct":  detail.get("volatility_pct"),
                "candles_used":    detail.get("candles_used"),
                "market_status":   detail.get("market_status"),
                "stale": (signal == "observe" and "insufficient_bars" in reason) or (signal == "no_trade" and reason in ("missing_quote", "wide_spread")),
                "execution_allowed": False,
                "order_created": False,
                "paper_order_created": False,
                "live_order_created": False,
                "paper_only": True,
                "not_financial_advice": True,
                "locks": LOCKED_FALSE,
            })

        env_name = getattr(self.gateway.provider, "env_name", "paper")
        creds = self.gateway.credentials_status()
        any_data = any(r["last"] is not None or r["bid"] is not None for r in results)
        quality = "fresh" if any_data and market_status == "open" else ("delayed_or_closed" if any_data else "no_data")

        lab = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "floor": "floor_43",
            "department": "Stock Exchange Trading Floor",
            "phase": "FLOOR_43_CONNECTED_STOCK_EXCHANGE_FLOOR_V1",
            "lab": "Stock Paper Strategy Lab V1",
            "mode": "stock_paper_strategy_lab",
            "provider": self.gateway.provider_name,
            "environment": env_name,
            "market_status": market_status,
            "default_symbols": symbols,
            "signal_counts": counts,
            "results": results,
            "credentials_present": {
                "api_key_present": bool(creds.get("api_key_present")),
                "api_secret_present": bool(creds.get("api_secret_present")),
            },
            "data_quality": quality,
            "stale": not any_data,
            "locks": LOCKED_FALSE,
            "execution_allowed": False,
            "order_created": False,
            "paper_order_created": False,
            "live_order_created": False,
            "paper_only": True,
            "not_financial_advice": True,
        }

        write_json(LATEST_PATH, lab)
        write_json(RUNTIME / "stock_paper_strategy_latest.json", lab)
        append_log({k: v for k, v in lab.items() if k != "results"} | {
            "result_count": len(results),
        })
        return lab

    def dashboard(self):
        latest = load_json(LATEST_PATH, {})
        return {
            "floor": "floor_43",
            "department": "Stock Exchange Trading Floor",
            "panel": "Stock Paper Strategy Lab",
            "status": "healthy" if latest.get("results") else "waiting",
            "latest_ts": latest.get("ts"),
            "mode": "stock_paper_strategy_lab",
            "provider": latest.get("provider"),
            "environment": latest.get("environment"),
            "market_status": latest.get("market_status"),
            "signal_counts": latest.get("signal_counts", {}),
            "results": latest.get("results", []),
            "data_quality": latest.get("data_quality"),
            "stale": latest.get("stale", True),
            "locks": LOCKED_FALSE,
            "execution_allowed": False,
            "order_created": False,
            "paper_order_created": False,
            "live_order_created": False,
            "paper_only": True,
            "not_financial_advice": True,
        }


def run(symbols=None):
    return StockPaperStrategyLab().run(symbols)


def dashboard():
    return StockPaperStrategyLab().dashboard()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
