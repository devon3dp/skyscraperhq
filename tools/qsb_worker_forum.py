#!/usr/bin/env python3
"""qsb_worker_forum.py — internal forum for Skyscraper HQ workers.

Ross 2026-06-14: "set up an internal forum so workers can go on it and talk
about it, they can talk to each other, they can talk to me, they can put up
ideas or things they're not happy about, or complaints or whatever."

Different from the message_board (one-way broadcast). This is two-way:
  · workers post threads in named categories
  · workers + Ross + Wren reply on threads
  · everyone can browse + react

Storage: append-only JSONL at data/registries/qsb_worker_forum.jsonl
Schema per row:
  {
    "ts": ISO,
    "id": "fpost_<unix>_<rand>",
    "thread_id": "fthr_<unix>_<rand>",   # equals id for top-level posts
    "parent_id": null | "fpost_...",     # null for top-level
    "author": "worker_id or 'Ross' or 'Wren'",
    "author_role": "worker|operator|wren|advisor",
    "category": "ideas|complaints|help_wanted|watercooler|ross_directed|kudos",
    "title": "..." (top-level only; replies have null title),
    "body": "...",
    "reactions": {"+1": [...], "love": [...]}  # extended later
  }

Usage:
  python3 tools/qsb_worker_forum.py post --author <id> --category <cat> --title "..." --body "..."
  python3 tools/qsb_worker_forum.py reply --parent <id> --author <id> --body "..."
  python3 tools/qsb_worker_forum.py list [--category <cat>] [--limit N]
  python3 tools/qsb_worker_forum.py thread <thread_id>
  python3 tools/qsb_worker_forum.py inbox <author>   # threads addressed to author
"""
from __future__ import annotations
import argparse, json, os, random, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
FORUM = ROOT / "data/registries/qsb_worker_forum.jsonl"
F47   = ROOT / "data/registries/qsb_f47_team_records.jsonl"

CATEGORIES = ("ideas", "complaints", "help_wanted", "watercooler",
              "ross_directed", "kudos")
ROLES = ("worker", "operator", "wren", "advisor")


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _mkid(prefix: str) -> str:
    return f"{prefix}_{int(datetime.now().timestamp())}_{random.randint(1000,9999)}"


def _read_all():
    if not FORUM.exists():
        return []
    rows = []
    for ln in FORUM.read_text().splitlines():
        ln = ln.strip()
        if not ln: continue
        try: rows.append(json.loads(ln))
        except: continue
    return rows


def _append(row):
    FORUM.parent.mkdir(parents=True, exist_ok=True)
    with FORUM.open("a") as f:
        f.write(json.dumps(row) + "\n")
    # Stamp on F47 records so the wake briefing surfaces forum activity
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": row["ts"], "kind": "worker_forum_post", "floor": "F47",
            "operator": row["author"],
            "summary": f"{row.get('category')}/{row.get('title') or '(reply)'}",
            "post_id": row["id"], "thread_id": row["thread_id"],
        }) + "\n")


def cmd_post(a):
    if a.category not in CATEGORIES:
        print(f"category must be one of {CATEGORIES}", file=sys.stderr); return 2
    pid = _mkid("fpost")
    row = {
        "ts": utcnow(),
        "id": pid,
        "thread_id": pid,
        "parent_id": None,
        "author": a.author,
        "author_role": a.role or "worker",
        "category": a.category,
        "title": a.title,
        "body": a.body,
        "reactions": {},
    }
    _append(row)
    print(f"✓ posted {pid} in {a.category}: {a.title}")
    return 0


def cmd_reply(a):
    rows = _read_all()
    parent = next((r for r in rows if r["id"] == a.parent), None)
    if not parent:
        print(f"parent {a.parent} not found", file=sys.stderr); return 2
    rid = _mkid("fpost")
    row = {
        "ts": utcnow(),
        "id": rid,
        "thread_id": parent["thread_id"],
        "parent_id": a.parent,
        "author": a.author,
        "author_role": a.role or "worker",
        "category": parent["category"],
        "title": None,
        "body": a.body,
        "reactions": {},
    }
    _append(row)
    print(f"✓ replied {rid} on thread {parent['thread_id']}")
    return 0


def cmd_list(a):
    rows = _read_all()
    threads = [r for r in rows if r["parent_id"] is None]
    if a.category:
        threads = [t for t in threads if t.get("category") == a.category]
    if a.unread_for:
        # crude unread = threads not yet replied to by this author
        replies_by_thread = {}
        for r in rows:
            if r["parent_id"] is not None:
                replies_by_thread.setdefault(r["thread_id"], []).append(r["author"])
        threads = [t for t in threads if a.unread_for not in replies_by_thread.get(t["thread_id"], [])]
    threads.sort(key=lambda t: t["ts"], reverse=True)
    for t in threads[:a.limit]:
        n_replies = sum(1 for r in rows if r["thread_id"] == t["thread_id"] and r["parent_id"])
        print(f"[{t['ts'][:19]}] [{t['category']:13s}] #{t['id'][:18]:18s} by {t['author']:15s}  ({n_replies} replies)")
        print(f"   {t['title']}")
        print(f"   {(t['body'] or '')[:140]}")
        print()
    return 0


def cmd_thread(a):
    rows = _read_all()
    posts = [r for r in rows if r["thread_id"] == a.thread_id]
    if not posts:
        print(f"thread {a.thread_id} not found", file=sys.stderr); return 2
    posts.sort(key=lambda r: r["ts"])
    for p in posts:
        prefix = "└─ " if p["parent_id"] else ""
        title = f" : {p['title']}" if p.get("title") else ""
        print(f"{prefix}[{p['ts'][:19]}] {p['author']:15s} ({p.get('author_role')}){title}")
        print(f"   {p['body']}")
        print()
    return 0


def cmd_inbox(a):
    rows = _read_all()
    threads = [r for r in rows if r["parent_id"] is None and (r["category"] == "ross_directed" if a.author == "Ross" else True)]
    threads = [t for t in threads if a.author in (t["author"], "Ross") or t.get("category") == "ross_directed"]
    threads.sort(key=lambda t: t["ts"], reverse=True)
    for t in threads[:20]:
        print(f"[{t['ts'][:19]}] {t['category']:13s} {t['author']:15s} {t['title']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("post"); p.add_argument("--author", required=True)
    p.add_argument("--role", default="worker", choices=ROLES)
    p.add_argument("--category", required=True, choices=CATEGORIES)
    p.add_argument("--title", required=True); p.add_argument("--body", required=True)
    p.set_defaults(fn=cmd_post)

    r = sub.add_parser("reply"); r.add_argument("--parent", required=True)
    r.add_argument("--author", required=True); r.add_argument("--role", default="worker", choices=ROLES)
    r.add_argument("--body", required=True); r.set_defaults(fn=cmd_reply)

    l = sub.add_parser("list"); l.add_argument("--category", default="")
    l.add_argument("--limit", type=int, default=20)
    l.add_argument("--unread-for", default="", dest="unread_for")
    l.set_defaults(fn=cmd_list)

    t = sub.add_parser("thread"); t.add_argument("thread_id"); t.set_defaults(fn=cmd_thread)
    i = sub.add_parser("inbox"); i.add_argument("author"); i.set_defaults(fn=cmd_inbox)

    args = ap.parse_args()
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
