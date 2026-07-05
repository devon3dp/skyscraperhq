#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

INSTRUMENTS="${1:-EUR_USD,GBP_USD,USD_JPY}"

python3 - <<PY
from tower.oanda_trading_floor import OANDATradingFloor
from pathlib import Path
import json

snapshot = OANDATradingFloor().snapshot("$INSTRUMENTS")
prices = snapshot.get("pricing", {}).get("prices", [])
account = snapshot.get("account_summary", {}).get("account", {})

summary = {
    "floor": "floor_41",
    "department": "OANDA Trading Floor",
    "mode": "practice_read_only_simulation",
    "account_currency": account.get("currency"),
    "NAV": account.get("NAV"),
    "balance": account.get("balance"),
    "openTradeCount": account.get("openTradeCount"),
    "openPositionCount": account.get("openPositionCount"),
    "instruments": [],
    "safety_locks": {
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "practice_order_execution_enabled": False,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "openclaw_execution_enabled": False,
        "autonomous_dispatch_enabled": False
    }
}

for p in prices:
    bids = p.get("bids", [])
    asks = p.get("asks", [])
    bid = float(bids[0]["price"]) if bids else None
    ask = float(asks[0]["price"]) if asks else None
    mid = (bid + ask) / 2 if bid is not None and ask is not None else None
    spread = ask - bid if bid is not None and ask is not None else None
    summary["instruments"].append({
        "instrument": p.get("instrument"),
        "status": p.get("status"),
        "tradeable": p.get("tradeable"),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "time": p.get("time")
    })

Path("data/runtime/oanda_kernel_market_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
PY

PROMPT="$(cat data/runtime/oanda_kernel_market_summary.json)

Kernel, analyze this OANDA practice market snapshot for paper-trading research only.
Do not place orders.
Do not enable live trading.
Do not enable workers.
Do not enable OpenClaw.
Do not enable autonomous dispatch.
Give a concise market read, risk notes, and what the paper strategy lab should observe next."

./scripts/qsb_kernel_chat.sh "$PROMPT"
