#!/usr/bin/env python3
"""qsb_binance.py — operator CLI for the Binance testnet floor."""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
ENV = ROOT / ".env.binance_testnet"
if ENV.exists():
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        if line.startswith("export "): line = line[7:]
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))

sys.path.insert(0, str(ROOT / "src"))


def cmd_preflight(args):
    from tower.floors.floor_42_binance_testnet.placement import preflight
    print(json.dumps(preflight(), indent=2))
    return 0


def cmd_place(args):
    from tower.floors.floor_42_binance_testnet.placement import place_for_worker
    out = place_for_worker(
        worker_id=args.worker, symbol=args.symbol, side=args.side,
        quote_qty_usdt=args.usdt,
        entry_reason=args.reason,
        confirm_practice_order=bool(args.confirm),
    )
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 2


def cmd_status(args):
    from tower.floors.floor_42_binance_testnet.state import floor_state_snapshot
    print(json.dumps(floor_state_snapshot(), indent=2))
    return 0


def cmd_open(args):
    from tower.floors.floor_42_binance_testnet.placement import (
        BinanceTestnetClient, BinanceTestnetNotConfigured,
    )
    try:
        c = BinanceTestnetClient()
    except BinanceTestnetNotConfigured as e:
        print(f"not configured: {e}", file=sys.stderr)
        return 2
    print(json.dumps(c.open_orders(args.symbol), indent=2))
    return 0


def main():
    p = argparse.ArgumentParser(description="QSB Binance testnet CLI.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight").set_defaults(func=cmd_preflight)
    sub.add_parser("status").set_defaults(func=cmd_status)
    op = sub.add_parser("open")
    op.add_argument("--symbol", default=None)
    op.set_defaults(func=cmd_open)
    pl = sub.add_parser("place")
    pl.add_argument("worker"); pl.add_argument("symbol")
    pl.add_argument("side", choices=["BUY", "SELL", "buy", "sell"])
    pl.add_argument("usdt", type=float)
    pl.add_argument("--reason", required=True)
    pl.add_argument("--confirm", action="store_true")
    pl.set_defaults(func=cmd_place)
    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
