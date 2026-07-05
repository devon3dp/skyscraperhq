#!/usr/bin/env python3
"""qsb_oanda.py — Operator CLI for certified-worker OANDA practice trades.

Commands:
  qsb_oanda.py preflight                            # account + pricing + guard state
  qsb_oanda.py preview <worker> <inst> <units> <buy|sell> --reason TEXT
  qsb_oanda.py place   <worker> <inst> <units> <buy|sell> --reason TEXT --confirm
  qsb_oanda.py close   <worker> <oanda_trade_id> --reason TEXT
  qsb_oanda.py claim   <worker> <oanda_trade_id> <inst>   # claim a pre-attribution open trade
  qsb_oanda.py status                                 # worker-attribution snapshot
  qsb_oanda.py open                                   # current open trades on account
  qsb_oanda.py killswitch on|off [--reason TEXT]

Every PLACE requires --confirm. The flag exists so you can't fat-finger
a live trade by alt-tabbing. The kernel cannot pass --confirm; only you
can type it.
"""

from __future__ import annotations

# V17 — strategy blocklist (Ross unlock 2026-06-10 + Helm + Auger flagged)
STRATEGY_BLOCKLIST = {
    "trend_continuation_signal": "1/18 wins on EUR_USD — pattern, not signal",
}
import argparse
import json
import os
import sys
from pathlib import Path

# Load .env.oanda_practice before importing anything that needs creds
ROOT = Path("/vaults/nvme0/qsb_tower_v1")
ENV_FILE = ROOT / ".env.oanda_practice"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        if line.startswith("export "): line = line[7:]
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))

sys.path.insert(0, str(ROOT / "src"))


def cmd_preflight(args) -> int:
    from tower_ops.oanda_practice_trading import practice_preflight
    pf = practice_preflight()
    print(json.dumps({
        "credentials_present": pf.get("credentials_present"),
        "account_ready":       pf.get("account_ready"),
        "pricing_ready":       pf.get("pricing_ready"),
        "kill_switch_on":      pf.get("kill_switch_on"),
        "balance":             pf.get("balance"),
        "NAV":                 pf.get("NAV"),
        "open_trade_count":    pf.get("open_trade_count"),
        "guards":              pf.get("guards"),
        "live_pricing":        pf.get("live_pricing_prices"),
    }, indent=2))
    return 0 if pf.get("ok") else 2


def cmd_preview(args) -> int:
    from tower_ops.oanda_practice_trading import practice_order_preview
    payload = {"mode": "PRACTICE_ONLY",
                "instrument": args.instrument, "units": args.units,
                "side": args.side, "entry_reason": args.reason}
    out = practice_order_preview(payload)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 2


def cmd_place(args) -> int:
    from tower.cognitive_kernel.oanda_worker_trades import place_for_worker
    out = place_for_worker(
        worker_id=args.worker,
        instrument=args.instrument,
        units=args.units, side=args.side,
        entry_reason=args.reason,
        confirm_practice_order=bool(args.confirm),
        style=args.style,
    )
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 2


def cmd_close(args) -> int:
    from tower.cognitive_kernel.oanda_worker_trades import close_for_worker
    out = close_for_worker(
        worker_id=args.worker,
        oanda_trade_id=args.trade_id,
        close_reason=args.reason,
    )
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 2


def cmd_claim(args) -> int:
    from tower.cognitive_kernel.oanda_worker_trades import claim_existing_open_trade
    out = claim_existing_open_trade(
        worker_id=args.worker,
        oanda_trade_id=args.trade_id,
        instrument=args.instrument,
        style=args.style,
    )
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 2


def cmd_status(args) -> int:
    from tower.cognitive_kernel.oanda_worker_trades import persist
    snap = persist()
    print(json.dumps(snap, indent=2, default=str))
    return 0


def cmd_open(args) -> int:
    from tower_ops.oanda_practice_trading import open_trades
    out = open_trades()
    trades = out.get("trades") or []
    if not trades:
        print("(no open trades on practice account)")
        return 0
    print(f"{len(trades)} open trade(s) on OANDA practice account:")
    for t in trades:
        print(f"  id={t.get('id'):<6} {t.get('instrument'):<8} "
              f"units={t.get('initialUnits'):<8} "
              f"open_price={t.get('price'):<10} "
              f"unrealizedPL={t.get('unrealizedPL')}")
    return 0


def cmd_killswitch(args) -> int:
    from tower_ops.oanda_practice_trading import kill_switch
    on = args.state.lower() in ("on", "true", "1")
    out = kill_switch({"kill_switch_on": on,
                         "reason": args.reason or ""})
    print(json.dumps(out, indent=2))
    return 0


def main():
    p = argparse.ArgumentParser(description="QSB OANDA practice worker CLI.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("preflight").set_defaults(func=cmd_preflight)

    pp = sub.add_parser("preview")
    pp.add_argument("worker"); pp.add_argument("instrument")
    pp.add_argument("units", type=int); pp.add_argument("side", choices=["buy", "sell"])
    pp.add_argument("--reason", required=True)
    pp.set_defaults(func=cmd_preview)

    pl = sub.add_parser("place")
    pl.add_argument("worker"); pl.add_argument("instrument")
    pl.add_argument("units", type=int); pl.add_argument("side", choices=["buy", "sell"])
    pl.add_argument("--reason", required=True)
    pl.add_argument("--style", default="scalp")
    pl.add_argument("--confirm", action="store_true",
                     help="REQUIRED. Refuses to place without this flag.")
    pl.set_defaults(func=cmd_place)

    cl = sub.add_parser("close")
    cl.add_argument("worker"); cl.add_argument("trade_id")
    cl.add_argument("--reason", required=True)
    cl.set_defaults(func=cmd_close)

    ca = sub.add_parser("claim")
    ca.add_argument("worker"); ca.add_argument("trade_id")
    ca.add_argument("instrument")
    ca.add_argument("--style", default="scalp")
    ca.set_defaults(func=cmd_claim)

    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("open").set_defaults(func=cmd_open)

    ks = sub.add_parser("killswitch")
    ks.add_argument("state", choices=["on", "off", "true", "false"])
    ks.add_argument("--reason", default="")
    ks.set_defaults(func=cmd_killswitch)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
