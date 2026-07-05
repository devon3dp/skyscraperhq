#!/usr/bin/env python3
"""
QSB Tower V1.3 — Floor 42 Binance Paper Strategy Lab V1

Phase: BINANCE_FLOOR_42_TRADING_FLOOR_V1

Reads Binance public market data and produces paper-only signal observations
for the unified animated cockpit. Never places orders.

Signal modes: observe, long_bias, short_bias, no_trade.
"""

from pathlib import Path
from datetime import datetime, timezone
import json

from tower.binance_floor import BinanceGateway, LOCKED_FALSE

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/binance_paper_strategy_lab.jsonl"

POLICY_PATH = REG / "binance_floor_policy.json"
LATEST_PATH = REG / "binance_paper_strategy_latest.json"


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


def _kline_metrics(klines):
    """
    Compute conservative paper metrics from 5m klines.
    Binance kline row: [openTime, open, high, low, close, volume, closeTime, ...]
    """
    if not klines or len(klines) < 4:
        return None

    closes = [_to_float(k[4]) for k in klines if _to_float(k[4]) is not None]
    if len(closes) < 4:
        return None

    last = closes[-1]
    ref_3 = closes[-4] if len(closes) >= 4 else closes[0]
    ref_10 = closes[-11] if len(closes) >= 11 else closes[0]
    ref_20 = closes[-21] if len(closes) >= 21 else closes[0]

    def pct(a, b):
        if not a or not b:
            return None
        return ((a - b) / b) * 100.0

    return {
        "last_close": last,
        "candles_used": len(closes),
        "momentum_3_pct": pct(last, ref_3),
        "momentum_10_pct": pct(last, ref_10),
        "momentum_20_pct": pct(last, ref_20),
    }


def _classify(symbol, ticker_row, kline_metrics, order_book):
    """
    Conservative paper-only crypto heuristic. Never a trade recommendation.
    Tags: observe | long_bias | short_bias | no_trade.
    """
    pct_change = _to_float((ticker_row or {}).get("priceChangePercent"))
    vol_quote = _to_float((ticker_row or {}).get("quoteVolume"))

    bids = (order_book or {}).get("bids") or []
    asks = (order_book or {}).get("asks") or []
    best_bid = _to_float(bids[0][0]) if bids else None
    best_ask = _to_float(asks[0][0]) if asks else None

    if best_bid is None or best_ask is None:
        return "no_trade", "missing order book", {
            "pct_change_24h": pct_change, "quote_volume_24h": vol_quote,
        }

    mid = (best_bid + best_ask) / 2
    last = _to_float((ticker_row or {}).get("lastPrice"))
    if last is None:
        last = (kline_metrics or {}).get("last_close") or mid

    spread = best_ask - best_bid
    spread_pct = (spread / last) * 100.0 if last else None

    detail = {
        "spread_pct": spread_pct,
        "mid": mid,
        "last": last,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "pct_change_24h": pct_change,
        "quote_volume_24h": vol_quote,
        "momentum_3_pct": (kline_metrics or {}).get("momentum_3_pct"),
        "momentum_10_pct": (kline_metrics or {}).get("momentum_10_pct"),
        "momentum_20_pct": (kline_metrics or {}).get("momentum_20_pct"),
        "kline_candles_used": (kline_metrics or {}).get("candles_used"),
    }

    if spread_pct is not None and spread_pct > 0.5:
        return "no_trade", "spread_pct > 0.5%", detail

    mom_10 = detail["momentum_10_pct"]
    mom_20 = detail["momentum_20_pct"]
    mom_3 = detail["momentum_3_pct"]

    if mom_10 is None or mom_20 is None:
        return "observe", "insufficient kline history", detail

    if mom_10 > 0.3 and mom_20 > 0.5 and (mom_3 is None or mom_3 > -0.1):
        return "long_bias", "upward momentum across 10 and 20 candle windows", detail
    if mom_10 < -0.3 and mom_20 < -0.5 and (mom_3 is None or mom_3 < 0.1):
        return "short_bias", "downward momentum across 10 and 20 candle windows", detail

    return "observe", "no aligned momentum pattern", detail


class BinancePaperStrategyLab:
    def __init__(self):
        self.policy = load_json(POLICY_PATH, {})
        self.gateway = BinanceGateway()

    def run(self, symbols=None):
        if symbols is None:
            symbols = self.policy.get("default_symbols") or [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"
            ]
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.split(",") if s.strip()]

        tickers_by_symbol = {}
        try:
            tickers = self.gateway.ticker_24h(symbols)
            if isinstance(tickers, dict):
                tickers = [tickers]
            for t in tickers or []:
                if isinstance(t, dict) and t.get("symbol"):
                    tickers_by_symbol[t["symbol"]] = t
        except Exception as exc:
            tickers_by_symbol["_error"] = str(exc)

        results = []
        counts = {"observe": 0, "long_bias": 0, "short_bias": 0, "no_trade": 0}
        for sym in symbols:
            ticker = tickers_by_symbol.get(sym, {}) if isinstance(tickers_by_symbol.get(sym), dict) else {}
            order_book = None
            kline_metrics = None
            errors = []

            try:
                order_book = self.gateway.order_book(sym, limit=5)
            except Exception as exc:
                errors.append("order_book: {}".format(exc))

            try:
                klines = self.gateway.klines(sym, interval="5m", limit=40)
                kline_metrics = _kline_metrics(klines)
            except Exception as exc:
                errors.append("klines: {}".format(exc))

            signal, reason, detail = _classify(sym, ticker, kline_metrics, order_book)
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
                "spread_pct": detail.get("spread_pct"),
                "mid": detail.get("mid"),
                "last": detail.get("last"),
                "best_bid": detail.get("best_bid"),
                "best_ask": detail.get("best_ask"),
                "pct_change_24h": detail.get("pct_change_24h"),
                "quote_volume_24h": detail.get("quote_volume_24h"),
                "momentum_3_pct": detail.get("momentum_3_pct"),
                "momentum_10_pct": detail.get("momentum_10_pct"),
                "momentum_20_pct": detail.get("momentum_20_pct"),
                "kline_candles_used": detail.get("kline_candles_used"),
                "execution_allowed": False,
                "order_created": False,
                "paper_only": True,
                "not_financial_advice": True,
                "locks": LOCKED_FALSE,
            })

        lab = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "floor": "floor_42",
            "department": "Binance Trading Floor",
            "phase": "BINANCE_FLOOR_42_TRADING_FLOOR_V1",
            "lab": "Binance Paper Strategy Lab V1",
            "mode": "binance_paper_strategy_lab",
            "environment": self.gateway.env_name,
            "default_symbols": symbols,
            "signal_counts": counts,
            "results": results,
            "credentials_present": {
                "api_key_present": bool(self.gateway.api_key),
                "api_secret_present": bool(self.gateway._api_secret),
            },
            "locks": LOCKED_FALSE,
            "execution_allowed": False,
            "order_created": False,
            "paper_only": True,
            "not_financial_advice": True,
        }

        write_json(LATEST_PATH, lab)
        write_json(RUNTIME / "binance_paper_strategy_latest.json", lab)
        append_log({k: v for k, v in lab.items() if k not in ("results",)} | {
            "result_count": len(results),
        })
        return lab

    def dashboard(self):
        latest = load_json(LATEST_PATH, {})
        return {
            "floor": "floor_42",
            "department": "Binance Trading Floor",
            "panel": "Binance Paper Strategy Lab",
            "status": "healthy" if latest.get("results") else "waiting",
            "latest_ts": latest.get("ts"),
            "mode": "binance_paper_strategy_lab",
            "environment": latest.get("environment"),
            "signal_counts": latest.get("signal_counts", {}),
            "results": latest.get("results", []),
            "locks": LOCKED_FALSE,
            "execution_allowed": False,
            "order_created": False,
            "paper_only": True,
            "not_financial_advice": True,
        }


def run(symbols=None):
    return BinancePaperStrategyLab().run(symbols)


def dashboard():
    return BinancePaperStrategyLab().dashboard()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
