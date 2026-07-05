#!/usr/bin/env python3
"""
QSB Tower V1.3 — Floor 41 OANDA Paper Strategy Lab V1

Creates paper-only market metrics and simulated signal candidates from OANDA
practice pricing snapshots.

No order placement.
No live trading.
No worker dispatch.
No external provider execution.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import statistics

from tower.oanda_trading_floor import OANDATradingFloor

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/oanda_paper_strategy_lab.jsonl"

LOCKS = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False,
}


def load_local_env_file():
    env = ROOT / ".env.oanda_practice"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line.startswith("export "):
            continue
        k, _, v = line.replace("export ", "", 1).partition("=")
        if not k:
            continue
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))


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


def first_float(items, key="price"):
    try:
        return float(items[0][key])
    except Exception:
        return None


def pip_size(instrument):
    return 0.01 if instrument and instrument.endswith("_JPY") else 0.0001


def classify_signal(metric):
    """
    Conservative paper-only heuristic.
    This is not a trade recommendation; it is a simulated research label.
    """
    spread_pips = metric.get("spread_pips")
    depth_bid = metric.get("top_bid_liquidity") or 0
    depth_ask = metric.get("top_ask_liquidity") or 0
    imbalance = metric.get("top_liquidity_imbalance") or 0

    if spread_pips is None:
        return "no_trade", "missing spread"

    if spread_pips > 2.0:
        return "no_trade", "spread too wide"

    if depth_bid + depth_ask <= 0:
        return "observe", "insufficient top-book liquidity"

    if imbalance > 0.25 and spread_pips <= 1.5:
        return "long_bias", "top-book bid liquidity exceeds ask liquidity"

    if imbalance < -0.25 and spread_pips <= 1.5:
        return "short_bias", "top-book ask liquidity exceeds bid liquidity"

    return "observe", "balanced book / no clear paper edge"


def metric_from_price(p):
    instrument = p.get("instrument")
    bids = p.get("bids") or []
    asks = p.get("asks") or []

    bid = first_float(bids)
    ask = first_float(asks)
    mid = (bid + ask) / 2 if bid is not None and ask is not None else None
    spread = ask - bid if bid is not None and ask is not None else None
    ps = pip_size(instrument)
    spread_pips = spread / ps if spread is not None and ps else None

    top_bid_liquidity = bids[0].get("liquidity", 0) if bids else 0
    top_ask_liquidity = asks[0].get("liquidity", 0) if asks else 0
    total_top = top_bid_liquidity + top_ask_liquidity
    imbalance = ((top_bid_liquidity - top_ask_liquidity) / total_top) if total_top else 0

    metric = {
        "instrument": instrument,
        "time": p.get("time"),
        "status": p.get("status"),
        "tradeable": p.get("tradeable"),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "spread_pips": spread_pips,
        "top_bid_liquidity": top_bid_liquidity,
        "top_ask_liquidity": top_ask_liquidity,
        "top_liquidity_imbalance": imbalance,
        "depth_levels_bid": len(bids),
        "depth_levels_ask": len(asks)
    }

    signal, reason = classify_signal(metric)
    metric["paper_signal"] = signal
    metric["paper_reason"] = reason
    return metric


class OANDAPaperStrategyLab:
    def __init__(self):
        load_local_env_file()
        self.policy = load_json(REG / "oanda_paper_strategy_policy.json", {})

    def run(self, instruments=None):
        if instruments is None:
            instruments = self.policy.get("default_instruments") or ["EUR_USD", "GBP_USD", "USD_JPY"]

        if isinstance(instruments, str):
            instruments = [x.strip() for x in instruments.split(",") if x.strip()]

        snapshot = OANDATradingFloor().snapshot(",".join(instruments))
        account = snapshot.get("account_summary", {}).get("account", {})
        prices = snapshot.get("pricing", {}).get("prices", []) if isinstance(snapshot.get("pricing"), dict) else []

        metrics = [metric_from_price(p) for p in prices]
        spreads = [m["spread_pips"] for m in metrics if isinstance(m.get("spread_pips"), (int, float))]

        counts = {}
        for m in metrics:
            counts[m["paper_signal"]] = counts.get(m["paper_signal"], 0) + 1

        lab = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "floor": "floor_41",
            "department": "OANDA Trading Floor",
            "lab": "Paper Strategy Lab V1",
            "mode": "practice_read_only_paper_simulation",
            "account": {
                "id": account.get("id"),
                "currency": account.get("currency"),
                "NAV": account.get("NAV"),
                "balance": account.get("balance"),
                "openTradeCount": account.get("openTradeCount"),
                "openPositionCount": account.get("openPositionCount"),
                "marginAvailable": account.get("marginAvailable")
            },
            "instruments": metrics,
            "summary": {
                "instrument_count": len(metrics),
                "tradeable_count": sum(1 for m in metrics if m.get("tradeable") is True),
                "avg_spread_pips": statistics.mean(spreads) if spreads else None,
                "signal_counts": counts,
                "errors": snapshot.get("errors", [])
            },
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True
        }

        write_json(REG / "oanda_paper_strategy_latest.json", lab)
        write_json(RUNTIME / "oanda_paper_strategy_latest.json", lab)
        append_log(lab)
        return lab

    def dashboard(self):
        latest = load_json(REG / "oanda_paper_strategy_latest.json", {})
        status = load_json(REG / "oanda_trading_floor_status.json", {})

        return {
            "floor": "floor_41",
            "department": "OANDA Trading Floor",
            "panel": "Paper Strategy Lab",
            "status": "healthy" if latest and not latest.get("summary", {}).get("errors") else "waiting",
            "latest_ts": latest.get("ts"),
            "mode": "practice_read_only_paper_simulation",
            "paper_trading_enabled": True,
            "paper_signal_generation_enabled": True,
            "local_model_commentary_enabled": True,
            "summary": latest.get("summary", {}),
            "instruments": latest.get("instruments", []),
            "locks": LOCKS,
            "not_financial_advice": True
        }


def run(instruments=None):
    return OANDAPaperStrategyLab().run(instruments)


def dashboard():
    return OANDAPaperStrategyLab().dashboard()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
