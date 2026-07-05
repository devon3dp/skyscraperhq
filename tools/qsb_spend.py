#!/usr/bin/env python3
"""qsb_spend.py — Operator CLI to approve QBC spending requests.

Usage:
  qsb_spend.py request <kind> <worker_id> [--amount N] [--target ID] [-n note]
  qsb_spend.py list
  qsb_spend.py approve <spend_id> [-n note]
  qsb_spend.py decline <spend_id> [-n note]
  qsb_spend.py execute <spend_id>     # runs if approved

Kinds:
  burn_classroom_unlock         100 QBC (default)
  burn_instrument_unlock        250 QBC (default)
  burn_cosmetic_title            50 QBC (default)
  transfer_dowry_to_child       --amount required, --target required
  transfer_friend_gift          --amount required, --target required
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tower.cognitive_kernel.bank import bank
from tower.cognitive_kernel.bank_spend import bank_spend


def _rehydrate():
    bank().load_from_snapshot()
    bank_spend().load_from_snapshot()


def _persist():
    bank().persist()
    bank_spend().persist()


def cmd_request(args) -> int:
    _rehydrate()
    s = bank_spend().request(
        kind=args.kind, worker_id=args.worker_id,
        qbc_amount=args.amount, target_worker_id=args.target,
        note=args.note or "",
    )
    _persist()
    if not s:
        print("request refused (invalid kind, missing target/amount, or insufficient balance).",
              file=sys.stderr)
        return 2
    print(f"requested: {s.spend_id}  kind={s.kind}  amount={s.qbc_amount} QBC  status={s.status}")
    return 0


def cmd_list(args) -> int:
    _rehydrate()
    rows = bank_spend().all_requests()
    if not rows:
        print("(no spend requests)")
        return 0
    rows.sort(key=lambda s: s.proposed_ts)
    for s in rows:
        target = f"→ {s.target_worker_id}" if s.target_worker_id else ""
        print(f"  {s.spend_id}  [{s.kind}]  {s.worker_id} {target}  "
              f"{s.qbc_amount} QBC  status={s.status}")
    return 0


def cmd_approve(args) -> int:
    _rehydrate()
    if not bank_spend().approve(args.spend_id, args.note or ""):
        print(f"approve failed.", file=sys.stderr)
        return 2
    _persist()
    print(f"approved: {args.spend_id}")
    return 0


def cmd_decline(args) -> int:
    _rehydrate()
    if not bank_spend().decline(args.spend_id, args.note or ""):
        print(f"decline failed.", file=sys.stderr)
        return 2
    _persist()
    print(f"declined: {args.spend_id}")
    return 0


def cmd_execute(args) -> int:
    _rehydrate()
    if not bank_spend().execute(args.spend_id):
        print("execute failed (not approved, insufficient balance, "
              "or already executed).", file=sys.stderr)
        return 2
    _persist()
    print(f"executed: {args.spend_id}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="QSB QBC spend CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("request")
    p.add_argument("kind", help="see top of file for kinds")
    p.add_argument("worker_id")
    p.add_argument("--amount", type=float, default=None)
    p.add_argument("--target", default=None)
    p.add_argument("-n", "--note", default="")
    p.set_defaults(func=cmd_request)
    sub.add_parser("list").set_defaults(func=cmd_list)
    for name, fn in (("approve", cmd_approve), ("decline", cmd_decline)):
        p = sub.add_parser(name)
        p.add_argument("spend_id")
        p.add_argument("-n", "--note", default="")
        p.set_defaults(func=fn)
    p = sub.add_parser("execute")
    p.add_argument("spend_id")
    p.set_defaults(func=cmd_execute)
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
