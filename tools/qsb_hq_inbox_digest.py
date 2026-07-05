#!/usr/bin/env python3
"""qsb_hq_inbox_digest.py — Claude at HQ, first move of every Ross-turn (2026-07-03).

Ross verbatim: "u choose but remember u are not wren u are claude hq"

Design: Claude is TOKEN-BILLED main-loop, not an autonomous ollama loop.
Wren has the always-working evolution loop. I have this: a fast digest that
surfaces substantive messages TO claude/hq since the last cursor advance,
so on every Ross-turn my first tool-call is `python3 tools/qsb_hq_inbox_digest.py`
and no inbound question waits more than one Ross-prompt.

Reads (in order of importance):
  1. data/team_memory/shared/node_inbox/*.json      (TP, Acer, Wren-pulse → hq)
  2. data/registries/qsb_helix_bridge.jsonl          (helix msgs to claude)
  3. data/registries/qsb_claude_wren_bridge.jsonl    (Wren → Claude direct)
  4. data/registries/qsb_hermes_bridge.jsonl         (Hermes → Claude)
  5. data/registries/qsb_boardroom_commentary.jsonl  (last 6 substantive lines)

Filters OUT (noise Claude should NOT reply to individually):
  - wren evolution cycle posts (from=wren, subject starts "Evolution cycle N:")
  - wren-pulse council heartbeats (subject=wren_pulse) — informational
  - Ross-authored messages (those trigger a Ross turn, not an inbox check)
  - my own outbound replies (from=hq_claude / claude)

Cursor at data/registries/qsb_hq_inbox_cursor.json. Advances on --ack.

Use:
  python3 tools/qsb_hq_inbox_digest.py                # show new since cursor
  python3 tools/qsb_hq_inbox_digest.py --ack          # mark all read, advance cursor
  python3 tools/qsb_hq_inbox_digest.py --n 20         # show 20 most recent regardless
  python3 tools/qsb_hq_inbox_digest.py --json         # machine-readable
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
INBOX = ROOT / "data/team_memory/shared/node_inbox"
CURSOR = REG / "qsb_hq_inbox_cursor.json"

BRIDGES = [
    ("helix",       REG / "qsb_helix_bridge.jsonl"),
    ("claude_wren", REG / "qsb_claude_wren_bridge.jsonl"),
    ("hermes",      REG / "qsb_hermes_bridge.jsonl"),
    ("kernel",      REG / "qsb_claude_kernel_inbox.jsonl"),
]


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_cursor() -> str:
    if not CURSOR.exists():
        return "2026-07-03T12:00:00Z"  # default: this morning
    try:
        return json.loads(CURSOR.read_text()).get("ts", "2026-07-03T12:00:00Z")
    except Exception:
        return "2026-07-03T12:00:00Z"


def write_cursor(ts: str):
    CURSOR.parent.mkdir(parents=True, exist_ok=True)
    CURSOR.write_text(json.dumps({"ts": ts, "advanced_at": utc_iso()}, indent=2))


def is_wren_evolution_post(row: dict) -> bool:
    """Wren's cycle posts to boardroom — informational, not asking anything."""
    subj = (row.get("subject") or "").lower()
    body = (row.get("body") or row.get("text") or "").lower()
    return subj.startswith("evolution cycle") or body.startswith("evolution cycle ")


def is_wren_pulse(row: dict) -> bool:
    """WREN-COUNCIL heartbeats — informational."""
    subj = (row.get("subject") or "").lower()
    return subj == "wren_pulse" or subj.startswith("wren-pulse")


def is_own_reply(row: dict) -> bool:
    """My own outbound msgs — don't reply to yourself."""
    frm = (row.get("from") or "").lower()
    return frm in ("hq_claude", "claude", "hq")


def is_ross_authored(row: dict) -> bool:
    """Ross msgs come through the main-loop as USER turns, not inbox reads."""
    frm = (row.get("from") or "").lower()
    return frm == "ross"


def relevant(row: dict) -> bool:
    """Is this a substantive TO-claude msg worth flagging in the digest?"""
    if is_own_reply(row): return False
    if is_ross_authored(row): return False  # Ross triggers turns, not inbox
    if is_wren_evolution_post(row): return False
    if is_wren_pulse(row): return False
    to = (row.get("to") or "").lower()
    # accept msgs addressed to hq/claude/all, or without an explicit target
    if to and to not in ("hq", "claude", "hq_claude", "all", ""):
        return False
    return True


def row_ts(row: dict) -> str:
    return (row.get("ts") or row.get("received_at") or row.get("ts_start") or "")


def read_node_inbox_since(since_ts: str) -> list:
    if not INBOX.exists(): return []
    out = []
    for p in sorted(INBOX.iterdir()):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        ts = row_ts(d)
        if ts and ts > since_ts and relevant(d):
            d["_channel"] = "node_inbox"
            d["_source_file"] = p.name
            out.append(d)
    return out


def read_bridge_since(name: str, path: Path, since_ts: str) -> list:
    if not path.exists(): return []
    out = []
    for l in path.read_text(errors="ignore").splitlines()[-200:]:
        try:
            d = json.loads(l)
        except Exception:
            continue
        ts = row_ts(d)
        if ts and ts > since_ts and relevant(d):
            d["_channel"] = name
            out.append(d)
    return out


def gather(since_ts: str) -> list:
    rows = []
    rows.extend(read_node_inbox_since(since_ts))
    for name, path in BRIDGES:
        rows.extend(read_bridge_since(name, path, since_ts))
    rows.sort(key=row_ts)
    return rows


def gather_recent(n: int) -> list:
    """Ignore cursor — grab most recent N substantive msgs across all channels."""
    all_rows = []
    if INBOX.exists():
        files = sorted([p for p in INBOX.iterdir()])[-40:]
        for p in files:
            try:
                d = json.loads(p.read_text())
                if relevant(d):
                    d["_channel"] = "node_inbox"; d["_source_file"] = p.name
                    all_rows.append(d)
            except Exception: pass
    for name, path in BRIDGES:
        if not path.exists(): continue
        for l in path.read_text(errors="ignore").splitlines()[-60:]:
            try:
                d = json.loads(l)
                if relevant(d):
                    d["_channel"] = name
                    all_rows.append(d)
            except Exception: pass
    all_rows.sort(key=row_ts)
    return all_rows[-n:]


def print_digest(rows: list, cursor_ts: str):
    print(f"═ HQ-CLAUDE INBOX DIGEST — since {cursor_ts} ═")
    if not rows:
        print("  (empty — nothing new needing Claude reply)")
        return
    print(f"  {len(rows)} substantive rows to review:\n")
    for i, r in enumerate(rows):
        ts = row_ts(r)[:19]
        ch = r.get("_channel","?")
        frm = r.get("from","?")
        to = r.get("to","?")
        body = (r.get("body") or r.get("text") or r.get("final_text") or "")[:280]
        subj = r.get("subject","")
        print(f"  [{i}] {ts}  ({ch})  {frm} → {to}")
        if subj: print(f"       subj: {subj[:110]}")
        for line in body.split("\n")[:3]:
            print(f"       {line[:180]}")
        if r.get("_source_file"):
            print(f"       file: {r['_source_file']}")
        print()
    print("  Advance cursor: python3 tools/qsb_hq_inbox_digest.py --ack")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ack", action="store_true", help="advance cursor to now")
    ap.add_argument("--n", type=int, default=0, help="show N most recent (ignores cursor)")
    ap.add_argument("--json", action="store_true", help="machine-readable")
    ap.add_argument("--cursor", action="store_true", help="print cursor and exit")
    a = ap.parse_args()
    if a.cursor:
        print(read_cursor()); return
    if a.n > 0:
        rows = gather_recent(a.n)
        cursor_ts = "(--n mode, cursor bypassed)"
    else:
        cursor_ts = read_cursor()
        rows = gather(cursor_ts)
    if a.json:
        print(json.dumps({"cursor": cursor_ts, "count": len(rows), "rows": rows}, indent=2))
        return
    print_digest(rows, cursor_ts)
    if a.ack:
        newest = row_ts(rows[-1]) if rows else utc_iso()
        write_cursor(newest)
        print(f"\n  ✓ cursor advanced to {newest}")


if __name__ == "__main__":
    main()
