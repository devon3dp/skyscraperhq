#!/usr/bin/env python3
"""qsb_research.py — Operator CLI for the research queue.

Usage:
  qsb_research.py file "<question>" [--by ID] [--purpose P] [--urls URL ...]
  qsb_research.py list
  qsb_research.py show <item_id>
  qsb_research.py allowlist
  qsb_research.py review <item_id> [-n note]

The 'service' command is intentionally NOT here — servicing requires a
fresh Claude session with WebFetch authorisation. See
scripts/qsb_phase_research_servicing.sh (separate phase).
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tower.cognitive_kernel.research_queue import research_queue


def _persist(rq):
    rq.persist()


def cmd_file(args) -> int:
    rq = research_queue(); rq.load_from_snapshot()
    item = rq.file(
        question=args.question,
        purpose=(args.purpose or "operator_request"),
        requested_by=(getattr(args, "by", None) or "operator"),
        target_urls=(args.urls or []),
    )
    _persist(rq)
    print(f"filed: {item.item_id}")
    return 0


def cmd_list(args) -> int:
    rq = research_queue(); rq.load_from_snapshot()
    snap = rq.snapshot()
    if not snap["item_count"]:
        print("(queue empty)")
        return 0
    print(f"{snap['item_count']} item(s)  by_status={snap['by_status']}")
    for r in snap["items"][-40:]:
        print(f"  {r['item_id']}  [{r['status']}]  by={r['requested_by']}  "
              f"purpose={r['purpose']}")
        print(f"      q: {r['question'][:120]}")
    return 0


def cmd_show(args) -> int:
    rq = research_queue(); rq.load_from_snapshot()
    snap = rq.snapshot()
    item = next((r for r in snap["items"]
                  if r["item_id"] == args.item_id), None)
    if not item:
        print(f"item {args.item_id} not found.", file=sys.stderr)
        return 2
    print(json.dumps(item, indent=2))
    return 0


def cmd_allowlist(args) -> int:
    rq = research_queue()
    snap = rq.snapshot()
    print(json.dumps(snap.get("allowlist_default") or [], indent=2))
    return 0


def cmd_review(args) -> int:
    rq = research_queue(); rq.load_from_snapshot()
    ok = rq.operator_review(args.item_id, note=(args.note or ""))
    _persist(rq)
    print("reviewed" if ok else "(not in answered state — skipped)")
    return 0 if ok else 2


def main():
    parser = argparse.ArgumentParser(description="QSB research queue CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("file")
    p.add_argument("question")
    p.add_argument("--by", default="operator")
    p.add_argument("--purpose", default="operator_request")
    p.add_argument("--urls", nargs="*", default=[])
    p.set_defaults(func=cmd_file)
    sub.add_parser("list").set_defaults(func=cmd_list)
    p = sub.add_parser("show"); p.add_argument("item_id")
    p.set_defaults(func=cmd_show)
    sub.add_parser("allowlist").set_defaults(func=cmd_allowlist)
    p = sub.add_parser("review")
    p.add_argument("item_id"); p.add_argument("-n", "--note", default="")
    p.set_defaults(func=cmd_review)
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
