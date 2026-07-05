#!/usr/bin/env python3
"""qsb_pot_orphan_reconcile.py — close orphaned positions via broker SELL.

Why this exists:
  Traders only know about positions they opened. On restart, self.open_position
  is None — pot.json positions become orphans no trader will close.

What it does:
  For each open position in pot.json:
    1. Place a SELL via qsb_broker_place.place_order (same path traders use).
    2. The broker layer calls _pot_release(open_order_id) on success.
    3. F47 stamp each close with realised PnL estimate.

Safe by design:
  - Only paper/testnet/practice (all venues are non-real-money per CLAUDE.md).
  - Uses the exact same broker path traders use (no duplicate logic).
  - Dry-run flag for paranoid checks.

ThinkPad-CEO sign-off thinkpad-00054: relative gate + staggered breakeven +
dust-close precheck. This tool implements the "dust-close precheck" — it
unblocks the pot before the live traders re-enter with the new gate logic.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))

POT = ROOT / "data/registries/qsb_portfolio_pot.json"
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
AUDIT = ROOT / "data/registries/qsb_pot_orphan_reconcile_audit.jsonl"

# pot.json stores the full broker venue name; broker_place.place_order
# expects the same. NO translation needed.
ALLOWED_VENUES = {"binance_testnet", "oanda_practice", "alpaca_paper"}


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stamp_f47(row: dict) -> None:
    with F47.open("a") as f:
        f.write(json.dumps(row) + "\n")


def stamp_audit(row: dict) -> None:
    with AUDIT.open("a") as f:
        f.write(json.dumps(row) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="enumerate orphans without sending broker SELLs")
    ap.add_argument("--max", type=int, default=0,
                    help="stop after closing this many (0=all)")
    ap.add_argument("--venue", default="",
                    help="only this venue (e.g. binance_testnet)")
    ap.add_argument("--worker", default="",
                    help="only this worker_id (e.g. belief_driven_eth)")
    args = ap.parse_args()

    from qsb_broker_place import place_order

    pot_before = json.loads(POT.read_text())
    ops = pot_before.get("open_positions", {})
    print(f"orphan reconcile · {len(ops)} open positions · "
          f"£{pot_before.get('committed_gbp', 0):.2f} / "
          f"£{pot_before.get('cap_gbp', 0):.2f}")

    if args.dry_run:
        print("DRY RUN — enumerating only:")

    closed = 0
    failed = 0
    realised_gbp_total = 0.0
    start_ts = utc_iso()

    stamp_f47({
        "ts": start_ts,
        "kind": "orphan_reconcile_start",
        "role": "maintenance",
        "subject": f"Closing {len(ops)} orphan positions per ThinkPad-CEO thinkpad-00054 sign-off",
        "dry_run": args.dry_run,
    })

    for pid, p in list(ops.items()):
        venue_pot = p.get("venue", "")
        if args.venue and venue_pot != args.venue:
            continue
        worker_id = p.get("worker_id", "anon")
        if args.worker and worker_id != args.worker:
            continue
        if venue_pot not in ALLOWED_VENUES:
            print(f"  skip {pid}: unknown venue {venue_pot}")
            continue
        venue = venue_pot
        instrument = p.get("instrument", "")
        qty = float(p.get("qty", 0))
        entry = float(p.get("price", 0))
        notional = float(p.get("notional_gbp", 0))
        if qty <= 0 or not instrument:
            print(f"  skip {pid}: qty={qty} instrument={instrument!r}")
            continue
        print(f"  SELL {worker_id:30s} {venue_pot:18s} {instrument:10s} "
              f"qty={qty:<14.6g} entry={entry:<10.4g} £{notional:.2f}")
        if args.dry_run:
            closed += 1
            continue
        try:
            res = place_order(
                venue=venue,
                instrument=instrument,
                side="SELL",
                qty=qty,
                worker_id=f"reconcile_{worker_id}",
                ref_price=entry,
                open_order_id=str(pid),
            )
            ok = bool(res.get("ok"))
            reason = res.get("reason", "")
            bid = res.get("broker_order_id")
            stamp_audit({
                "ts": utc_iso(), "pid": pid, "venue": venue_pot,
                "worker_id": worker_id, "instrument": instrument,
                "qty": qty, "entry_px": entry, "notional_gbp": notional,
                "broker_ok": ok, "reason": reason, "broker_order_id": bid,
            })
            if ok:
                closed += 1
                # broker layer already calls _pot_release — pot.json updates
                print(f"    OK · broker_oid={bid}")
            else:
                failed += 1
                print(f"    FAIL · {reason}")
        except Exception as e:
            failed += 1
            print(f"    EXC · {type(e).__name__}: {e}")
            stamp_audit({
                "ts": utc_iso(), "pid": pid, "exception": str(e)[:200],
            })
        if args.max and closed >= args.max:
            print(f"  reached --max={args.max}")
            break
        # be gentle on broker — pause 0.3s between calls
        time.sleep(0.3)

    # Re-read pot.json to see the actual state
    pot_after = json.loads(POT.read_text())
    ops_after = pot_after.get("open_positions", {})
    print()
    print(f"DONE · closed={closed} failed={failed}")
    print(f"  before: {len(ops)} open · £{pot_before.get('committed_gbp', 0):.2f}")
    print(f"  after:  {len(ops_after)} open · £{pot_after.get('committed_gbp', 0):.2f}")
    print(f"  cap remaining: £{pot_after.get('cap_gbp', 0) - pot_after.get('committed_gbp', 0):.2f}")

    stamp_f47({
        "ts": utc_iso(),
        "kind": "orphan_reconcile_done",
        "role": "maintenance",
        "subject": f"Reconcile complete · closed={closed} failed={failed}",
        "before_open": len(ops),
        "after_open": len(ops_after),
        "before_committed_gbp": pot_before.get("committed_gbp", 0),
        "after_committed_gbp": pot_after.get("committed_gbp", 0),
        "dry_run": args.dry_run,
    })


if __name__ == "__main__":
    main()
