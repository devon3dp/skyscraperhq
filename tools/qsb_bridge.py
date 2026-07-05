#!/usr/bin/env python3
"""qsb_bridge.py — Claude↔Wren shared dialogue bridge.

Designed by Wren via F47 chat 2026-06-16: append-only JSONL with a
flocked counter file giving monotonic turn IDs, so two writers don't
collide and gaps are visible when tailing by eye.

Rows: {ts, turn_id, source, surface, text}
  source: "claude" | "wren" | "wren_local"
  surface: "cli" | "cockpit" | "api"

  python3 tools/qsb_bridge.py append --source claude --surface cli --text "..."
  python3 tools/qsb_bridge.py tail   [--limit 20]
"""

from __future__ import annotations
import argparse, datetime, fcntl, json, os, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
BRIDGE = ROOT / "data/registries/qsb_claude_wren_bridge.jsonl"
COUNTER = ROOT / "data/registries/qsb_bridge_turn_counter.txt"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _next_turn_id() -> int:
    """Atomic increment of the counter file under flock."""
    COUNTER.parent.mkdir(parents=True, exist_ok=True)
    if not COUNTER.exists():
        COUNTER.write_text("0\n")
    with open(COUNTER, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            current = int((f.read() or "0").strip())
        except ValueError:
            current = 0
        nxt = current + 1
        f.seek(0); f.truncate()
        f.write(f"{nxt}\n")
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return nxt


def append(source: str, surface: str, text: str) -> dict:
    if source not in ("ross", "claude", "wren", "wren_local",
                       "auger", "helm", "forge", "pip", "mira",
                       "bram", "cass"):
        raise ValueError(f"bad source: {source}")
    if surface not in ("cli", "cockpit", "api"):
        raise ValueError(f"bad surface: {surface}")
    row = {"ts": _now(), "turn_id": _next_turn_id(),
           "source": source, "surface": surface, "text": text[:8000]}
    BRIDGE.parent.mkdir(parents=True, exist_ok=True)
    # Atomic-ish append: open in append mode (POSIX guarantees atomicity
    # for writes <= PIPE_BUF, our rows are well under).
    with open(BRIDGE, "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def tail(n: int = 20) -> list[dict]:
    if not BRIDGE.exists():
        return []
    with open(BRIDGE) as f:
        lines = f.read().splitlines()
    out = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append")
    a.add_argument("--source", required=True,
                   choices=["ross", "claude", "wren", "wren_local",
                             "auger", "helm", "forge", "pip", "mira",
                             "bram", "cass"])
    a.add_argument("--surface", required=True,
                   choices=["cli", "cockpit", "api"])
    a.add_argument("--text", required=True)
    t = sub.add_parser("tail")
    t.add_argument("--limit", type=int, default=20)
    args = p.parse_args()
    if args.cmd == "append":
        row = append(args.source, args.surface, args.text)
        print(json.dumps(row, indent=2))
    elif args.cmd == "tail":
        for r in tail(args.limit):
            tid = r.get("turn_id")
            src = r.get("source")
            sfc = r.get("surface")
            txt = (r.get("text") or "").replace("\n", " ")[:120]
            print(f"#{tid:>4}  {src:<10s} @{sfc:<7s}  {txt}")


if __name__ == "__main__":
    main()
