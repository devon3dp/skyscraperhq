#!/usr/bin/env python3
"""
QSB Tower V1.3 — Floor 41 Paper Ledger

Records paper-only signal observations from the OANDA Paper Strategy Lab.

No real orders.
No practice orders.
No live trading.
No worker execution.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import uuid

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/floor41_paper_ledger.jsonl"

LEDGER_PATH = REG / "floor41_paper_ledger.json"

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
    "direct_provider_access": False
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


def append_jsonl(path, record):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def pip_size(instrument):
    return 0.01 if instrument and instrument.endswith("_JPY") else 0.0001


def latest_prior_mid(entries, instrument):
    for entry in reversed(entries):
        if entry.get("instrument") == instrument and isinstance(entry.get("mid"), (int, float)):
            return entry["mid"]
    return None


class Floor41PaperLedger:
    def __init__(self):
        data = load_json(LEDGER_PATH, {})
        self.entries = data.get("entries", []) if isinstance(data, dict) else []

    def record_lab(self, lab):
        ts = datetime.now(timezone.utc).isoformat()
        new_entries = []

        instruments = lab.get("instruments", [])
        account = lab.get("account", {})

        for metric in instruments:
            instrument = metric.get("instrument")
            mid = metric.get("mid")
            prior_mid = latest_prior_mid(self.entries, instrument)
            delta = None
            delta_pips = None

            if isinstance(mid, (int, float)) and isinstance(prior_mid, (int, float)):
                delta = mid - prior_mid
                delta_pips = delta / pip_size(instrument)

            signal = metric.get("paper_signal", "observe")
            paper_direction = {
                "long_bias": "paper_long_bias",
                "short_bias": "paper_short_bias",
                "observe": "flat_observation",
                "no_trade": "flat_no_trade"
            }.get(signal, "flat_observation")

            entry = {
                "id": f"paper_{uuid.uuid4().hex[:12]}",
                "ts": ts,
                "floor": "floor_41",
                "source": "oanda_paper_strategy_lab_v1",
                "instrument": instrument,
                "paper_signal": signal,
                "paper_direction": paper_direction,
                "paper_reason": metric.get("paper_reason"),
                "bid": metric.get("bid"),
                "ask": metric.get("ask"),
                "mid": mid,
                "spread_pips": metric.get("spread_pips"),
                "top_liquidity_imbalance": metric.get("top_liquidity_imbalance"),
                "prior_mid": prior_mid,
                "simulated_delta": delta,
                "simulated_delta_pips_since_prior_observation": delta_pips,
                "account_nav": account.get("NAV"),
                "paper_only": True,
                "not_financial_advice": True,
                "locks": LOCKS
            }

            new_entries.append(entry)
            append_jsonl(LOG, entry)

        self.entries.extend(new_entries)

        ledger = {
            "ledger": "floor41_paper_ledger_v1",
            "updated_ts": ts,
            "entry_count": len(self.entries),
            "latest_entry_count": len(new_entries),
            "entries": self.entries[-500:],
            "latest_entries": new_entries,
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True
        }

        write_json(LEDGER_PATH, ledger)
        write_json(RUNTIME / "floor41_paper_ledger_latest.json", ledger)
        return ledger

    def status(self):
        data = load_json(LEDGER_PATH, {})
        entries = data.get("entries", [])
        latest = data.get("latest_entries", [])

        pips = [
            e.get("simulated_delta_pips_since_prior_observation")
            for e in entries
            if isinstance(e.get("simulated_delta_pips_since_prior_observation"), (int, float))
        ]

        return {
            "ledger": "floor41_paper_ledger_v1",
            "entry_count": len(entries),
            "latest_entry_count": len(latest),
            "latest_entries": latest[-10:],
            "simulated_observation_delta_pips_total": sum(pips) if pips else 0,
            "paper_only": True,
            "not_financial_advice": True,
            "locks": LOCKS
        }


def record_lab(lab):
    return Floor41PaperLedger().record_lab(lab)


def status():
    return Floor41PaperLedger().status()


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
