#!/usr/bin/env python3
"""qsb_image.py — Operator CLI to approve free-image drafts.

Usage:
  qsb_image.py list                       # show all drafts
  qsb_image.py approve <draft_id> [-n …]  # approve + promote to Floor 46
  qsb_image.py promoted                   # show already-promoted SKUs

Approval ≠ publish. Publishing remains a separate operator gate
(live_listings_publishing_enabled) that requires a separate Claude phase.
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tower.cognitive_kernel import COG_REG
from tower.cognitive_kernel.free_image_promotion import free_image_promotion
from tower.cognitive_kernel.free_image_catalog import persist as persist_catalog


def cmd_list(args) -> int:
    persist_catalog()  # ensure freshness
    cat = json.loads((COG_REG / "cognitive_free_image_catalog.json").read_text())
    drafts = cat.get("draft_sample") or []
    if not drafts:
        print("(no drafts)")
        return 0
    print(f"{len(drafts)} free-image draft(s):")
    for d in drafts:
        print(f"  · {d.get('draft_id')}  sku={d.get('sku')}  "
              f"source={d.get('source_name')}  "
              f"cat={d.get('category')}  "
              f"price=${d.get('suggested_price'):.2f}  "
              f"proj_rev=${d.get('projected_revenue'):.2f}")
    return 0


def cmd_approve(args) -> int:
    fip = free_image_promotion()
    fip.load_approvals()
    a = fip.approve(args.draft_id, approved_by="operator",
                     note=(args.note or ""))
    if not a:
        print(f"draft {args.draft_id} not found.", file=sys.stderr)
        return 2
    promoted = fip.promote_approved()
    fip.persist()
    print(f"approved: {args.draft_id}  sku={a.sku}")
    if promoted:
        print(f"  → promoted to Floor 46 catalog: {promoted}")
    else:
        print(f"  (already in catalog or could not promote)")
    return 0


def cmd_promoted(args) -> int:
    fip = free_image_promotion()
    fip.load_approvals()
    rows = [a for a in fip._approvals.values() if a.promoted]
    if not rows:
        print("(none promoted yet)")
        return 0
    for a in rows:
        print(f"  · {a.draft_id}  sku={a.sku}  source={a.source_name}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Operator CLI for approving free-image draft listings.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(func=cmd_list)
    p = sub.add_parser("approve")
    p.add_argument("draft_id")
    p.add_argument("-n", "--note", default="")
    p.set_defaults(func=cmd_approve)
    sub.add_parser("promoted").set_defaults(func=cmd_promoted)
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
