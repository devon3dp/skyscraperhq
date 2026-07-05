#!/usr/bin/env python3
"""
QSB Tower V1.3 — Cross-Market Bus V1

Phase: FLOOR_43_CONNECTED_STOCK_EXCHANGE_FLOOR_V1

Read-only synthesis of OANDA Floor 41 + Binance Floor 42 + Stock Floor 43
into a single cross-market view. Produces advisory cross-market labels.

Hard contract:
- Reads registries only. Never calls any provider directly.
- Produces labels only — never an order, never an execution decision.
- Every published record sets execution_allowed=false, paper_only=true,
  advisory_only=true, not_financial_advice=true.
"""

from pathlib import Path
from datetime import datetime, timezone
import json


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOG = ROOT / "data/logs/cross_market_bus.jsonl"

BUS_LATEST_PATH    = REG / "cross_market_bus_latest.json"
CORR_LATEST_PATH   = REG / "cross_market_correlation_latest.json"

# Sources used by the bus
SRC_OANDA_STRATEGY = REG / "oanda_paper_strategy_latest.json"
SRC_OANDA_LEDGER   = REG / "floor41_paper_ledger.json"
SRC_OANDA_STATUS   = REG / "oanda_trading_floor_status.json"
SRC_OANDA_SNAPSHOT = REG / "oanda_trading_floor_latest_snapshot.json"

SRC_BINANCE_STATUS    = REG / "binance_floor_status.json"
SRC_BINANCE_STRATEGY  = REG / "binance_paper_strategy_latest.json"
SRC_BINANCE_SNAPSHOT  = REG / "binance_market_snapshot_latest.json"

SRC_STOCK_STATUS    = REG / "stock_floor_status.json"
SRC_STOCK_STRATEGY  = REG / "stock_paper_strategy_latest.json"
SRC_STOCK_SNAPSHOT  = REG / "stock_market_snapshot_latest.json"

SRC_STRATEGY_INTEL    = REG / "strategy_intelligence_latest.json"
SRC_STRATEGY_CORR     = REG / "strategy_autoloop_correlation_latest.json"
SRC_OPENCLAW_SANDBOX  = REG / "openclaw_sandbox_latest.json"
SRC_WORKER_TICK       = REG / "worker_sandbox_latest_tick.json"
SRC_SANDBOX_PERF      = REG / "sandbox_performance_latest.json"

STALENESS_FRESH_SEC = 180
STALENESS_STALE_SEC = 900

# Anything we add to the published payload that holds a "lock" key remains False.
ADVISORY_LOCKS = {
    "execution_allowed": False,
    "order_created": False,
    "paper_order_created": False,
    "live_order_created": False,
    "cross_market_execution_enabled": False,
    "stock_order_execution_enabled": False,
    "stock_live_trading_enabled": False,
    "stock_paper_order_execution_enabled": False,
    "binance_order_execution_enabled": False,
    "binance_live_trading_enabled": False,
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "openclaw_real_tool_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False,
}


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


def _staleness_sec(ts_str):
    if not ts_str:
        return None
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return None


def _market_state(latest_ts, error=None):
    if error:
        return {"status": "error", "latest_ts": latest_ts, "error": str(error)[:200]}
    age = _staleness_sec(latest_ts)
    if age is None:
        return {"status": "unknown", "latest_ts": latest_ts, "error": None}
    if age <= STALENESS_FRESH_SEC:
        return {"status": "ready", "latest_ts": latest_ts, "error": None, "age_sec": age}
    if age <= STALENESS_STALE_SEC:
        return {"status": "stale", "latest_ts": latest_ts, "error": None, "age_sec": age}
    return {"status": "offline", "latest_ts": latest_ts, "error": None, "age_sec": age}


def _safe(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _oanda_observations(strategy):
    """Build [{symbol, paper_signal, direction, market}] from OANDA registries."""
    out = []
    for r in (strategy or {}).get("results") or []:
        if not isinstance(r, dict):
            continue
        sig = r.get("paper_signal") or "observe"
        out.append({
            "symbol": r.get("instrument"),
            "market": "fx",
            "paper_signal": sig,
            "direction": r.get("paper_direction") or "flat_observation",
            "confidence": r.get("confidence"),
            "spread_pips": r.get("spread_pips"),
            "momentum_10": r.get("momentum_10_pips"),
            "execution_allowed": False,
            "paper_only": True,
        })
    return out


def _binance_observations(strategy):
    out = []
    for r in (strategy or {}).get("results") or []:
        if not isinstance(r, dict):
            continue
        sig = r.get("paper_signal") or "observe"
        out.append({
            "symbol": r.get("symbol"),
            "market": "crypto",
            "paper_signal": sig,
            "direction": r.get("paper_direction") or "flat_observation",
            "pct_change_24h": r.get("pct_change_24h"),
            "spread_pct": r.get("spread_pct"),
            "momentum_10": r.get("momentum_10_pct"),
            "execution_allowed": False,
            "paper_only": True,
        })
    return out


def _stock_observations(strategy):
    out = []
    for r in (strategy or {}).get("results") or []:
        if not isinstance(r, dict):
            continue
        sig = r.get("paper_signal") or "observe"
        out.append({
            "symbol": r.get("symbol"),
            "market": "equity",
            "paper_signal": sig,
            "direction": r.get("paper_direction") or "flat_observation",
            "spread_pct": r.get("spread_pct"),
            "momentum_10": r.get("momentum_10_pct"),
            "volatility_pct": r.get("volatility_pct"),
            "market_status": r.get("market_status"),
            "stale": r.get("stale", False),
            "execution_allowed": False,
            "paper_only": True,
        })
    return out


def _bias_score(observations):
    """Tally long_bias - short_bias counts in a market group."""
    long_n = sum(1 for o in observations if o.get("paper_signal") == "long_bias")
    short_n = sum(1 for o in observations if o.get("paper_signal") == "short_bias")
    return long_n, short_n


def _label_cross_market(fx_obs, crypto_obs, stock_obs, per_market):
    """
    Produce advisory cross-market labels. Strictly observational.
    Allowed labels:
      risk_on_watch, risk_off_watch, dollar_strength_watch,
      crypto_equity_alignment, equity_fx_divergence, no_cross_signal.
    """
    labels = []
    reasons = []

    fx_long, fx_short = _bias_score(fx_obs)
    cr_long, cr_short = _bias_score(crypto_obs)
    st_long, st_short = _bias_score(stock_obs)

    # If no market is ready, just return no_cross_signal
    ready = sum(1 for k in per_market.values() if k.get("status") in ("ready", "stale"))
    if ready == 0:
        return ["no_cross_signal"], ["no markets ready"]

    # crypto_equity_alignment: both crypto and equities lean the same direction
    if cr_long >= 1 and st_long >= 1 and cr_short == 0 and st_short == 0:
        labels.append("crypto_equity_alignment")
        reasons.append("crypto and equity samples lean long; possible risk_on")
    elif cr_short >= 1 and st_short >= 1 and cr_long == 0 and st_long == 0:
        labels.append("crypto_equity_alignment")
        reasons.append("crypto and equity samples lean short; possible risk_off")

    # equity_fx_divergence: equities long while FX (USD pairs) lean short of USD, or vice versa
    if (st_long >= 1 and fx_short >= 1) or (st_short >= 1 and fx_long >= 1):
        labels.append("equity_fx_divergence")
        reasons.append("stocks and FX samples diverge on direction")

    # dollar_strength_watch: any USD-major pair leaning short USD or long USD
    for o in fx_obs:
        sym = (o.get("symbol") or "").upper()
        if "USD" not in sym:
            continue
        # In QSB FX symbols like EUR_USD, "long_bias" = long base / short USD
        if o.get("paper_signal") in ("long_bias", "short_bias"):
            labels.append("dollar_strength_watch")
            reasons.append("USD-pair {} reporting {}".format(sym, o.get("paper_signal")))
            break

    # risk_on_watch / risk_off_watch are the broader aggregations
    total_long  = fx_long + cr_long + st_long
    total_short = fx_short + cr_short + st_short
    if total_long >= 2 and total_short == 0:
        labels.append("risk_on_watch")
        reasons.append("{} cross-market long_bias samples".format(total_long))
    elif total_short >= 2 and total_long == 0:
        labels.append("risk_off_watch")
        reasons.append("{} cross-market short_bias samples".format(total_short))

    # de-dup and default
    labels = list(dict.fromkeys(labels))
    if not labels:
        labels = ["no_cross_signal"]
        reasons.append("no cross-market signal threshold met")
    return labels, reasons


def _safe_pairs(fx_obs, crypto_obs, stock_obs):
    """Pairs of (a, b) of opposite-direction observations across markets for correlation list."""
    out = []
    pools = [("fx", fx_obs), ("crypto", crypto_obs), ("equity", stock_obs)]
    flat = []
    for market, obs in pools:
        for o in obs:
            flat.append((market, o))
    for i, (m1, a) in enumerate(flat):
        for m2, b in flat[i + 1:]:
            if m1 == m2:
                continue
            sa = a.get("paper_signal")
            sb = b.get("paper_signal")
            if sa not in ("long_bias", "short_bias") or sb not in ("long_bias", "short_bias"):
                continue
            kind = "aligned" if sa == sb else "divergent"
            out.append({
                "left_market": m1,
                "left_symbol": a.get("symbol"),
                "left_signal": sa,
                "right_market": m2,
                "right_symbol": b.get("symbol"),
                "right_signal": sb,
                "kind": kind,
                "advisory_only": True,
                "execution_allowed": False,
            })
            if len(out) >= 24:
                return out
    return out


class CrossMarketBus:
    def __init__(self):
        pass

    def build(self):
        ts_now = datetime.now(timezone.utc).isoformat()

        # OANDA sources
        oanda_strategy = load_json(SRC_OANDA_STRATEGY, {})
        oanda_status   = load_json(SRC_OANDA_STATUS, {})
        oanda_ledger   = load_json(SRC_OANDA_LEDGER, {})
        oanda_snap     = load_json(SRC_OANDA_SNAPSHOT, {})

        # Binance
        binance_status   = load_json(SRC_BINANCE_STATUS, {})
        binance_strategy = load_json(SRC_BINANCE_STRATEGY, {})
        binance_snap     = load_json(SRC_BINANCE_SNAPSHOT, {})

        # Stocks
        stock_status   = load_json(SRC_STOCK_STATUS, {})
        stock_strategy = load_json(SRC_STOCK_STRATEGY, {})
        stock_snap     = load_json(SRC_STOCK_SNAPSHOT, {})

        # Strategy/correlation/openclaw/worker context (optional)
        strategy_intel = load_json(SRC_STRATEGY_INTEL, {})
        strategy_corr  = load_json(SRC_STRATEGY_CORR, {})
        openclaw_l     = load_json(SRC_OPENCLAW_SANDBOX, {})
        worker_tick    = load_json(SRC_WORKER_TICK, {})
        sandbox_perf   = load_json(SRC_SANDBOX_PERF, {})

        oanda_ts   = oanda_strategy.get("ts") or _safe(oanda_status, "status_ts") or _safe(oanda_snap, "snapshot_ts")
        binance_ts = binance_strategy.get("ts") or _safe(binance_status, "status_ts") or _safe(binance_snap, "snapshot_ts")
        stocks_ts  = stock_strategy.get("ts") or _safe(stock_status, "status_ts") or _safe(stock_snap, "snapshot_ts")

        per_market = {
            "oanda":   _market_state(oanda_ts,   error=oanda_status.get("market_data_error")
                                                          or oanda_status.get("public_market_data_error")),
            "binance": _market_state(binance_ts, error=binance_status.get("public_market_data_error")),
            "stocks":  _market_state(stocks_ts,  error=stock_status.get("public_market_data_error")),
        }

        fx_obs     = _oanda_observations(oanda_strategy)
        crypto_obs = _binance_observations(binance_strategy)
        stock_obs  = _stock_observations(stock_strategy)

        labels, reasons = _label_cross_market(fx_obs, crypto_obs, stock_obs, per_market)
        pairs = _safe_pairs(fx_obs, crypto_obs, stock_obs)

        packet_count = sum(1 for o in (fx_obs + crypto_obs + stock_obs)
                           if o.get("paper_signal") in ("long_bias", "short_bias"))

        bus = {
            "ts": ts_now,
            "phase": "FLOOR_43_CONNECTED_STOCK_EXCHANGE_FLOOR_V1",
            "bus": "QSB Cross-Market Bus V1",
            "per_market_status": per_market,
            "fx_observations":     fx_obs,
            "crypto_observations": crypto_obs,
            "stock_observations":  stock_obs,
            "cross_market_labels": labels,
            "label_reasons": reasons,
            "packet_count": packet_count,
            "openclaw_context": {
                "ts": openclaw_l.get("ts"),
                "execution_enabled": False,
                "recommendation_count": len(openclaw_l.get("recommendations") or openclaw_l.get("latest_recommendations") or []),
            },
            "strategy_context": {
                "intel_ts": strategy_intel.get("latest_ts") or strategy_intel.get("ts"),
                "correlation_ts": strategy_corr.get("ts"),
            },
            "worker_context": {
                "latest_tick_ts": worker_tick.get("ts"),
                "lift_packet_count": len((worker_tick or {}).get("lift_packets") or []),
            },
            "sandbox_performance_ts": sandbox_perf.get("ts"),
            "oanda_ledger_entry_count": (oanda_ledger or {}).get("entry_count") or 0,
            "advisory_only": True,
            "paper_only": True,
            "not_financial_advice": True,
            **ADVISORY_LOCKS,
        }

        write_json(BUS_LATEST_PATH, bus)

        correlation = {
            "ts": ts_now,
            "phase": "FLOOR_43_CONNECTED_STOCK_EXCHANGE_FLOOR_V1",
            "bus": "QSB Cross-Market Correlation V1",
            "correlations": pairs,
            "advisory_only": True,
            "paper_only": True,
            "not_financial_advice": True,
            **ADVISORY_LOCKS,
        }
        write_json(CORR_LATEST_PATH, correlation)

        append_log({
            "ts": ts_now,
            "bus": bus["bus"],
            "per_market_status": {k: v.get("status") for k, v in per_market.items()},
            "labels": labels,
            "packet_count": packet_count,
            "pair_count": len(pairs),
            "advisory_only": True,
            "paper_only": True,
            "execution_allowed": False,
        })

        return bus

    def status(self):
        bus = load_json(BUS_LATEST_PATH, {})
        return {
            "ts": bus.get("ts"),
            "bus": bus.get("bus") or "QSB Cross-Market Bus V1",
            "per_market_status": bus.get("per_market_status") or {},
            "cross_market_labels": bus.get("cross_market_labels") or ["no_cross_signal"],
            "packet_count": bus.get("packet_count") or 0,
            "advisory_only": True,
            "paper_only": True,
            "not_financial_advice": True,
            **ADVISORY_LOCKS,
        }


def build():
    return CrossMarketBus().build()


def status():
    return CrossMarketBus().status()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
