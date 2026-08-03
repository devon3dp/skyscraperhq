#!/usr/bin/env python3
"""qsb_f43_stock_status_refresh.py — HONEST Floor 43 status/snapshot refresh.

Floor 43 (Alpaca Paper STOCKS) is PAPER PREVIEW-ONLY. This tool writes a FRESH,
TRUTHFUL status + market snapshot to:
    data/registries/stock_floor_status.json
    data/registries/stock_market_snapshot_latest.json
by driving the existing read-only engine in
    src/tower/stock_exchange_floor.py

Why this exists: the engine's own load_local_env_file() reads a repo-root
.env.alpaca that does not exist, so a bare run reports credentials_absent even
though real PAPER creds live in the F28 vault (.env.alpaca_paper) — the same
file the live tick-stream daemon (tools/qsb_f43_alpaca_stream.py) already uses.
This tool loads those creds the identical way the stream does, so the status is
HONEST: real Alpaca /v2/clock market_status (open/closed) and real /v2/account
read state, instead of a 7-week-stale credentials_absent placeholder.

HARD SAFETY (unchanged, enforced by the engine, not weakened here):
    - stock_order_execution_enabled      = False  (real placement BLOCKED)
    - stock_paper_order_execution_enabled= True   (paper preview only)
    - all order endpoints refused by the gateway regardless of env flags.
This tool ONLY reads (clock/account/quotes/bars). It never places an order.

Secrets are loaded into the process env and NEVER printed or logged.

Usage:
    python3 tools/qsb_f43_stock_status_refresh.py            # refresh once
    python3 tools/qsb_f43_stock_status_refresh.py --quiet    # minimal stdout
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
VAULT = ROOT / "floors/floor_28_security_department/vault/.env.alpaca_paper"
REG = ROOT / "data/registries"
STATUS_PATH = REG / "stock_floor_status.json"
SNAPSHOT_PATH = REG / "stock_market_snapshot_latest.json"

# Make src/tower importable exactly like the engine expects.
sys.path.insert(0, str(ROOT / "src"))


def load_vault_creds() -> None:
    """Load ALPACA_API_KEY/SECRET from the F28 vault into os.environ.

    Mirrors tools/qsb_f43_alpaca_stream.py load_vault(). Uses setdefault so a
    real environment value (if the operator exported one) wins. Never logs the
    values. If the vault file is absent, we leave env untouched and the engine
    will honestly report credentials_absent.
    """
    if not VAULT.exists():
        return
    for line in VAULT.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = re.sub(r"^export\s+", "", line)
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh Floor 43 honest status/snapshot.")
    ap.add_argument("--quiet", action="store_true", help="minimal stdout")
    args = ap.parse_args()

    load_vault_creds()

    # Import AFTER creds are in env; the engine reads os.environ at construction.
    from tower.stock_exchange_floor import StockGateway  # type: ignore

    gw = StockGateway()  # provider auto-selected (alpaca when creds present)
    status = gw.status()          # writes STATUS_PATH
    snap = gw.snapshot()          # writes SNAPSHOT_PATH

    # Build a NON-SECRET summary for stdout / systemd journal.
    creds = status.get("credentials", {}) or {}
    summary = {
        "status_ts": status.get("status_ts"),
        "provider": status.get("provider"),
        "environment": status.get("environment"),
        "credentials_present": bool(creds.get("api_key_present")),
        "public_market_data_ready": status.get("public_market_data_ready"),
        "public_market_data_error": status.get("public_market_data_error"),
        "account_read_ready": status.get("account_read_ready"),
        "market_status": status.get("market_status"),
        "snapshot_data_quality": snap.get("data_quality"),
        "snapshot_stale": snap.get("stale"),
        "quote_symbols": sorted((snap.get("quotes") or {}).keys()),
        # SAFETY posture — always surfaced so nobody mistakes this for live.
        "stock_order_execution_enabled": status.get("stock_order_execution_enabled"),
        "stock_paper_order_execution_enabled": status.get("stock_paper_order_execution_enabled"),
        "order_endpoints_blocked": status.get("order_endpoints_blocked"),
        "paper_only": status.get("paper_only"),
    }
    if not args.quiet:
        print(json.dumps(summary, indent=2))
    else:
        ms = summary["market_status"]
        dq = summary["snapshot_data_quality"]
        print(f"F43 refreshed: market={ms} data={dq} "
              f"creds={summary['credentials_present']} "
              f"placement_blocked={summary['order_endpoints_blocked']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
