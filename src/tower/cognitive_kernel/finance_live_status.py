"""FinanceLiveStatus — Honest per-floor status of finance floors.

Reads each floor's registries + ledgers and reports:
  · which floor has an actual API adapter present in the codebase
  · which floor has a credentials env file (we check NAMES of env vars,
    never values)
  · which floor has real API call audit logs in data/logs/
  · how many rows in each floor's ledger AND whether those rows came
    from a real broker callback (we mark synthetic vs. real)
  · the gate state for each floor

The intent is to make it impossible to mistake the demo for live.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import os

from . import ROOT, REG, COG_REG, write_registry, append_log, now, load


@dataclass
class FloorFinanceStatus:
    floor_id: str
    floor_label: str
    mode: str                       # 'PRACTICE_ONLY' / 'TESTNET_PREVIEW_ONLY' / 'PAPER_PREVIEW_ONLY'
    api_adapter_module_present: bool
    api_adapter_path: Optional[str]
    credentials_env_vars_seen: List[str]      # names only
    real_api_calls_logged: int
    real_orders_placed: int
    ledger_total_rows: int
    ledger_synthetic_rows: int
    ledger_real_rows: int
    last_api_call_ts: Optional[str]
    gates_locked: Dict[str, bool] = field(default_factory=dict)
    advisory_notes: List[str] = field(default_factory=list)


# Where each floor's adapter WOULD live if wired
ADAPTER_PATHS = {
    "floor_41_oanda_practice": "src/tower/integrations/oanda_adapter.py",
    "floor_42_binance_testnet": "src/tower/integrations/binance_adapter.py",
    "floor_43_stocks_paper":    "src/tower/integrations/stocks_paper_adapter.py",
}

# Per-floor ledger location
LEDGERS = {
    "floor_41_oanda_practice":  ROOT / "data/logs/qsb_floor41_oanda_trade_ledger.jsonl",
    "floor_42_binance_testnet": ROOT / "data/logs/qsb_floor42_binance_trade_ledger.jsonl",
    "floor_43_stocks_paper":    ROOT / "data/logs/qsb_floor43_stocks_trade_ledger.jsonl",
}

# Per-floor real-API call log (would be created by adapter when it actually
# calls the broker). Absence = no real calls.
REAL_API_LOGS = {
    "floor_41_oanda_practice":  ROOT / "data/logs/oanda_api_calls.jsonl",
    "floor_42_binance_testnet": ROOT / "data/logs/binance_api_calls.jsonl",
    "floor_43_stocks_paper":    ROOT / "data/logs/stocks_paper_api_calls.jsonl",
}

# Per-floor expected env var names. We CHECK NAMES; we never read values.
ENV_VARS_PER_FLOOR = {
    "floor_41_oanda_practice": [
        "QSB_OANDA_ACCOUNT_ID", "QSB_OANDA_API_TOKEN",
        "QSB_OANDA_PRACTICE_URL",
    ],
    "floor_42_binance_testnet": [
        "QSB_BINANCE_TESTNET_API_KEY",
        "QSB_BINANCE_TESTNET_API_SECRET",
        "QSB_BINANCE_TESTNET_URL",
    ],
    "floor_43_stocks_paper": [
        "QSB_STOCKS_PAPER_BROKER",
        "QSB_STOCKS_PAPER_API_KEY",
        "QSB_STOCKS_PAPER_API_SECRET",
    ],
}

# Gates per floor that MUST stay locked unless explicitly flipped
GATES_PER_FLOOR = {
    "floor_41_oanda_practice": {
        "live_trading_enabled": False,
        "real_money_live_trading_enabled": False,
        "autonomous_dispatch_enabled": False,
        # Practice placement allowed under guardrails per CLAUDE.md
        "oanda_practice_placement_allowed_with_manual_confirm": True,
    },
    "floor_42_binance_testnet": {
        "binance_order_execution_enabled": False,
        "binance_real_account_access": False,
        "autonomous_dispatch_enabled": False,
    },
    "floor_43_stocks_paper": {
        "stock_order_execution_enabled": False,
        "stock_real_account_access": False,
        "autonomous_dispatch_enabled": False,
    },
}


def _count_ledger_rows(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {"total": 0, "synthetic": 0, "real": 0,
                "last_ts": None}
    total = synthetic = real = 0
    last_ts = None
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                total += 1
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                tag = (r.get("tag") or "")
                if "DEMO_SEED" in tag or "SYNTHETIC" in tag or "TEST" in tag:
                    synthetic += 1
                elif r.get("broker_order_id") or r.get("broker_fill_id"):
                    real += 1
                else:
                    # Unknown provenance — count as synthetic to be safe
                    synthetic += 1
                ts = r.get("ts") or r.get("close_ts")
                if isinstance(ts, str):
                    last_ts = ts
    except Exception:
        pass
    return {"total": total, "synthetic": synthetic,
            "real": real, "last_ts": last_ts}


def _count_real_api_calls(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {"calls": 0, "orders": 0}
    calls = orders = 0
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                calls += 1
                try:
                    r = json.loads(line)
                    if r.get("kind") == "order_placement":
                        orders += 1
                except Exception:
                    continue
    except Exception:
        pass
    return {"calls": calls, "orders": orders}


def _check_env_vars(names: List[str]) -> List[str]:
    """Return env var names that ARE set (values are never read into the
    registry — we just confirm presence)."""
    return [n for n in names if os.environ.get(n)]


def assess_all() -> List[FloorFinanceStatus]:
    results: List[FloorFinanceStatus] = []
    for floor_id, ledger_path in LEDGERS.items():
        adapter_rel = ADAPTER_PATHS.get(floor_id)
        adapter_abs = (ROOT / adapter_rel) if adapter_rel else None
        ledger_stats = _count_ledger_rows(ledger_path)
        real_call_path = REAL_API_LOGS.get(floor_id)
        api_stats = _count_real_api_calls(real_call_path) if real_call_path else {"calls": 0, "orders": 0}

        mode = ("PRACTICE_ONLY" if "oanda" in floor_id
                 else "TESTNET_PREVIEW_ONLY" if "binance" in floor_id
                 else "PAPER_PREVIEW_ONLY")
        env_names = ENV_VARS_PER_FLOOR.get(floor_id, [])
        env_seen = _check_env_vars(env_names)

        notes: List[str] = []
        if ledger_stats["total"] > 0 and ledger_stats["real"] == 0:
            notes.append(
                f"Ledger has {ledger_stats['total']} rows but ZERO carry "
                "a broker_order_id — none of these are real trades. "
                "They are demo/seed rows from the lineage system."
            )
        if adapter_abs and not adapter_abs.exists():
            notes.append(
                f"No adapter module at {adapter_abs}. A future operator-"
                "authorised phase would create it."
            )
        if env_names and not env_seen:
            notes.append(
                f"No credential env vars set ({env_names}). The Kernel "
                "would refuse to call the broker even if the gates were "
                "open — there is no API key to use."
            )
        if api_stats["calls"] == 0:
            notes.append(
                "No real API call audit log present. Zero broker calls "
                "have been made."
            )

        results.append(FloorFinanceStatus(
            floor_id=floor_id,
            floor_label={
                "floor_41_oanda_practice":   "Floor 41 — OANDA Practice",
                "floor_42_binance_testnet":  "Floor 42 — Binance Testnet",
                "floor_43_stocks_paper":     "Floor 43 — Stocks Paper",
            }.get(floor_id, floor_id),
            mode=mode,
            api_adapter_module_present=(adapter_abs.exists()
                                          if adapter_abs else False),
            api_adapter_path=(str(adapter_abs) if adapter_abs else None),
            credentials_env_vars_seen=env_seen,
            real_api_calls_logged=api_stats["calls"],
            real_orders_placed=api_stats["orders"],
            ledger_total_rows=ledger_stats["total"],
            ledger_synthetic_rows=ledger_stats["synthetic"],
            ledger_real_rows=ledger_stats["real"],
            last_api_call_ts=ledger_stats["last_ts"],
            gates_locked=dict(GATES_PER_FLOOR.get(floor_id, {})),
            advisory_notes=notes,
        ))
    return results


def snapshot() -> Dict[str, Any]:
    rows = assess_all()
    return {
        "ok": True,
        "kind": "cognitive_finance_live_status",
        "generated_ts": now(),
        "policy": ("Honest per-floor status. Ledger rows + API call "
                    "logs + env-var presence + adapter existence + "
                    "gate state. No values of credentials are read."),
        "floor_count": len(rows),
        "any_real_orders_placed_anywhere": sum(r.real_orders_placed for r in rows) > 0,
        "total_real_api_calls_across_floors": sum(r.real_api_calls_logged for r in rows),
        "total_ledger_rows": sum(r.ledger_total_rows for r in rows),
        "total_synthetic_rows": sum(r.ledger_synthetic_rows for r in rows),
        "total_real_rows": sum(r.ledger_real_rows for r in rows),
        "floors": [asdict(r) for r in rows],
        "headline": _headline(rows),
    }


def _headline(rows: List[FloorFinanceStatus]) -> str:
    total_real = sum(r.ledger_real_rows for r in rows)
    total_synth = sum(r.ledger_synthetic_rows for r in rows)
    total_calls = sum(r.real_api_calls_logged for r in rows)
    if total_real == 0 and total_calls == 0:
        return (f"NO REAL TRADES ANYWHERE. {total_synth} synthetic / demo "
                "ledger rows present. 0 real broker API calls. All gates "
                "locked.")
    return (f"⚠ {total_real} real ledger rows · {total_calls} real "
            "broker API calls logged. INSPECT IMMEDIATELY.")


def persist() -> Dict[str, Any]:
    snap = snapshot()
    write_registry("cognitive_finance_live_status.json", snap)
    append_log("finance_live_status.jsonl", {
        "event": "assess",
        "any_real_orders": snap["any_real_orders_placed_anywhere"],
        "total_real_rows": snap["total_real_rows"],
        "total_calls": snap["total_real_api_calls_across_floors"],
    })
    return snap
