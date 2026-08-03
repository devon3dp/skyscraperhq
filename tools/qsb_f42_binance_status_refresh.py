#!/usr/bin/env python3
"""qsb_f42_binance_status_refresh.py — HONEST Floor 42 status/snapshot refresh.

Floor 42 (Binance TESTNET crypto) is PREVIEW-ONLY: order placement is refused by
the gateway regardless of any flag. This tool writes a FRESH, TRUTHFUL status +
market snapshot to:
    data/registries/binance_floor_status.json
    data/registries/binance_market_snapshot_latest.json
by driving the existing read-only gateway in src/tower/binance_floor.py.

Why this exists (same class of bug F43 had): those two registries were 7 WEEKS
stale (status_ts 2026-06-08) and reported "credentials_absent / env_file_exists:
false" even though the public Binance trade stream (tools/qsb_f42_binance_stream.py)
has been live the whole time. Nothing ran the gateway's status() on a schedule.
This tool runs it, so the surface is honest: real /api/v3/ticker/24hr quotes and
real market-data-ready state instead of a stale placeholder.

SAFETY — this tool does PUBLIC market data ONLY:
    - It NEVER reads the F28 vault or any .env file. The gateway only reads
      credentials that are ALREADY in os.environ; this tool exports nothing.
      So testnet account read stays UNauthenticated here and is reported
      honestly as not-ready (requires vault creds, deliberately not wired).
    - order_execution stays BLOCKED (gateway refuses all order endpoints in V1).
    - No gate is flipped. No SAFETY_DENY path is touched.
    - credentials_status() returns booleans only — no secret is ever printed.

Also refreshes the unified data/registries/qsb_trading_floors_status.json so the
dashboards / Underground map get one honest cross-floor surface.

Usage:
    python3 tools/qsb_f42_binance_status_refresh.py            # refresh once
    python3 tools/qsb_f42_binance_status_refresh.py --quiet    # minimal stdout
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
SNAPSHOT_PATH = REG / "binance_market_snapshot_latest.json"
sys.path.insert(0, str(ROOT / "src"))


def public_ticker_24h(base_url: str, symbols: list[str]) -> tuple[list, list]:
    """Fetch 24h tickers ONE SYMBOL AT A TIME (public, read-only, no creds).

    The gateway's ticker_24h() sends symbols as a JSON-array param, which the
    testnet endpoint (testnet.binance.vision) rejects with HTTP 400. Per-symbol
    GETs work on both testnet and mainnet, so we do that here instead. This is
    plain public market data — no API key, no order, no signed call.
    """
    tickers, errors = [], []
    for sym in symbols:
        url = f"{base_url}/api/v3/ticker/24hr?symbol={sym}"
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                tickers.append(json.loads(r.read()))
        except Exception as exc:  # keep going; report honestly
            errors.append(f"ticker_24h {sym}: {exc}")
    return tickers, errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    # Import the existing read-only gateway. It reads creds only from os.environ
    # (we export none), so account read stays unauthenticated / public-only.
    from tower.binance_floor import BinanceGateway  # noqa: E402

    gw = BinanceGateway()
    status = gw.status()          # writes binance_floor_status.json (public market data)
    snap = gw.snapshot()          # writes binance_market_snapshot_latest.json (24h tickers)

    # The gateway's multi-symbol ticker_24h fails on testnet (HTTP 400). Backfill
    # the snapshot with per-symbol public tickers so the surface is truthful.
    if not (snap.get("tickers")):
        symbols = snap.get("symbols") or ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]
        tickers, tick_errs = public_ticker_24h(gw.base_url, symbols)
        if tickers:
            snap["tickers"] = tickers
            # Drop the stale array-form ticker_24h error, keep any per-symbol ones.
            snap["errors"] = [
                e for e in (snap.get("errors") or [])
                if not e.startswith("ticker_24h:")
            ] + tick_errs
            SNAPSHOT_PATH.write_text(json.dumps(snap, indent=2), encoding="utf-8")

    # Refresh the unified cross-floor status so the map/dashboards stay current.
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "qsb_trading_floors_status.py"), "--quiet"],
            check=False,
            timeout=60,
        )
    except Exception:
        pass

    if not args.quiet:
        n_tickers = len(snap.get("tickers") or [])
        print(
            "F42 refreshed: market_data_ready={} account_read_ready={} "
            "tickers={} errors={}".format(
                status.get("public_market_data_ready"),
                status.get("account_read_ready"),
                n_tickers,
                len(snap.get("errors") or []),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
