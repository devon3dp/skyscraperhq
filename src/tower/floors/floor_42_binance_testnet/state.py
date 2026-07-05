"""Floor 42 state, gates, guardrails."""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List
import json
import os

from tower.cognitive_kernel import ROOT, REG, now


FLOOR_ID = "floor_42_binance_testnet"
FLOOR_LABEL = "Floor 42 — Binance Testnet"

FLAGS: Dict[str, bool] = {
    "testnet_only":                          True,
    "live_real_money_binance_enabled":       False,
    "binance_order_execution_enabled":       False,   # public; CLAUDE.md hard line
    "binance_testnet_order_execution_enabled": False, # flips True only when creds present
    "external_api_calls_enabled":            False,
    "autonomous_dispatch_enabled":           False,
    "preview_only":                          True,
    "kill_switch_on":                        False,
}

GUARDS: Dict[str, Any] = {
    "execution_mode":         "TESTNET_ONLY",
    "binance_env_required":   "testnet",
    "base_url_testnet":       "https://testnet.binance.vision",
    "base_url_production":    "https://api.binance.com",   # NEVER used by this scaffold
    "allowed_symbols":        ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"),
    "max_quantity_per_order_quote_usdt": 200.0,    # cap per order
    "max_open_trades":        3,
    "max_trades_per_hour":    6,
    "max_spread_bps":         15.0,    # 0.15%
    "max_daily_loss_usdt":    50.0,
    "kill_switch_must_be_off": True,
    "manual_confirmation_required": True,
}

REGISTRY_NAME = "qsb_floor42_binance_testnet_state.json"


def creds_present() -> bool:
    return all(os.environ.get(v) for v in (
        "QSB_BINANCE_TESTNET_API_KEY",
        "QSB_BINANCE_TESTNET_API_SECRET",
    ))


def _credentials_check() -> Dict[str, Any]:
    needed = [
        "QSB_BINANCE_TESTNET_API_KEY",
        "QSB_BINANCE_TESTNET_API_SECRET",
    ]
    return {
        "needed_env_vars": needed,
        "seen": [v for v in needed if os.environ.get(v)],
        "missing": [v for v in needed if not os.environ.get(v)],
        "ready": all(os.environ.get(v) for v in needed),
    }


def floor_state_snapshot() -> Dict[str, Any]:
    creds = _credentials_check()
    return {
        "ok": True,
        "kind": "qsb_floor42_binance_testnet_state",
        "generated_ts": now(),
        "floor_id": FLOOR_ID,
        "floor_label": FLOOR_LABEL,
        "status": ("ready_for_orders" if creds["ready"]
                    else "awaiting_credentials"),
        "flags": dict(FLAGS),
        "guards": dict(GUARDS),
        "credentials": creds,
        "policy": (
            "Binance testnet only. Real-money endpoints hard-disabled. "
            "Workers need certification + manual confirm to place. "
            "All guardrails enforced server-side before any API call."
        ),
        "onboarding_steps": [
            "1. Visit https://testnet.binance.vision and log in with GitHub.",
            "2. Generate an API key + secret on the testnet (one-time).",
            "3. Save the key + secret in /vaults/nvme0/qsb_tower_v1/.env.binance_testnet:",
            "     export QSB_BINANCE_TESTNET_API_KEY='...'",
            "     export QSB_BINANCE_TESTNET_API_SECRET='...'",
            "4. Run: source .env.binance_testnet && python3 tools/qsb_binance.py preflight",
            "5. Once preflight reports OK, certified workers may place testnet orders via CLI.",
        ],
        "world_clock_aware": True,
        "trading_sessions_module": "tower.cognitive_kernel.trading_sessions",
    }


def persist_floor_state() -> Path:
    snap = floor_state_snapshot()
    p = REG / REGISTRY_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return p


def tick() -> Dict[str, Any]:
    return floor_state_snapshot()
