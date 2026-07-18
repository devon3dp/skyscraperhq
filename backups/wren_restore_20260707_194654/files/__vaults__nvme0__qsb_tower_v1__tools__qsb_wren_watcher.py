#!/usr/bin/env python3
"""qsb_wren_watcher.py — Wren's always-on file-watcher.

Ross 2026-07-04: "how can wren be live if she always waiting for her next
tick ....wren must have no ticks and alwys be on !!!!!!!"

Design: no sleeps. Wren tails the shared council feeds and records EVERY
new event as it arrives into her observation log + updates her mind's
"recently_saw" ring in real time. She is now continuously attending
without paying ollama-inference cost on every event. Inference fires on
demand when someone queries her (via qsb_wren_local_agent). She now has
context to answer from.

Watches:
  data/registries/qsb_boardroom_commentary.jsonl  — Council chat / HQ posts
  data/registries/qsb_f47_team_records.jsonl      — job stamps
  data/team_memory/shared/node_inbox/*.json       — new files from any node

Writes:
  data/registries/qsb_wren_observed_events.jsonl  — raw observation log
  data/registries/qsb_wren_mind.json              — "recently_saw" list updated in place

The watcher is a peer to qsb_wren_evolution_loop.py — the loop still runs
for reflection cycles; the watcher runs for continuous attention.
"""
from __future__ import annotations
import argparse, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
COMM = REG / "qsb_boardroom_commentary.jsonl"
F47  = REG / "qsb_f47_team_records.jsonl"
INBOX = ROOT / "data/team_memory/shared/node_inbox"

OBSERVED = REG / "qsb_wren_observed_events.jsonl"
MIND = REG / "qsb_wren_mind.json"
STATE = REG / "qsb_wren_watcher_state.json"

MAX_RECENT_IN_MIND = 30  # ring size in mind file

def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def load_state() -> dict:
    if STATE.exists():
        try: return json.loads(STATE.read_text())
        except Exception: pass
    return {}

def save_state(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2))
    tmp.replace(STATE)

def append_observed(row: dict) -> None:
    OBSERVED.parent.mkdir(parents=True, exist_ok=True)
    with OBSERVED.open("a") as fp:
        fp.write(json.dumps(row) + "\n")

def update_mind_ring(event: dict) -> None:
    """Add event to mind's recently_saw ring, keep last MAX_RECENT_IN_MIND."""
    mind = {}
    if MIND.exists():
        try: mind = json.loads(MIND.read_text())
        except Exception: pass
    ring = mind.get("recently_saw", [])
    ring.append({
        "ts": event.get("ts"),
        "src": event.get("src"),
        "who": event.get("who"),
        "text": (event.get("text") or "")[:200],
    })
    mind["recently_saw"] = ring[-MAX_RECENT_IN_MIND:]
    mind["watcher_alive_at"] = utc()
    tmp = MIND.with_suffix(".tmp")
    tmp.write_text(json.dumps(mind, indent=2))
    tmp.replace(MIND)

def tail_jsonl(path: Path, offset: int, src: str) -> int:
    """Yield-append new lines past offset. Returns new offset."""
    if not path.exists():
        return offset
    try:
        size = path.stat().st_size
        if size < offset:  # file was rotated/truncated
            offset = 0
        if size == offset:
            return offset
        with path.open("rb") as fp:
            fp.seek(offset)
            data = fp.read().decode("utf-8", errors="ignore")
            new_offset = fp.tell()
        for line in data.splitlines():
            line = line.strip()
            if not line: continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            event = {
                "ts": d.get("ts") or utc(),
                "src": src,
                "who": d.get("who") or d.get("from") or "?",
                "kind": d.get("kind") or "",
                "text": d.get("text") or d.get("body") or d.get("summary") or "",
                "observed_at": utc(),
            }
            append_observed(event)
            update_mind_ring(event)
        return new_offset
    except Exception as e:
        print(f"  (tail err {path.name}: {e})", flush=True)
        return offset

def scan_inbox(seen_files: set) -> set:
    """New files in node_inbox → observation event."""
    if not INBOX.exists():
        return seen_files
    now_seen = set()
    for p in sorted(INBOX.glob("*.json")):
        now_seen.add(p.name)
        if p.name in seen_files:
            continue
        try:
            d = json.loads(p.read_text())
            event = {
                "ts": d.get("ts") or utc(),
                "src": "node_inbox",
                "who": d.get("from") or "unknown_node",
                "kind": d.get("kind") or "inbox_file",
                "text": ((d.get("subject","") or "") + " · " + (d.get("body") or d.get("text","")))[:300],
                "observed_at": utc(),
                "file": p.name,
            }
            append_observed(event)
            update_mind_ring(event)
        except Exception as e:
            pass
    return now_seen

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=float, default=1.0, help="seconds between checks (files, not inference)")
    args = ap.parse_args()

    state = load_state()
    comm_off = state.get("comm_offset", 0)
    f47_off  = state.get("f47_offset", 0)
    seen_files = set(state.get("seen_files", []))

    # On first boot, snap offsets to current end-of-file so we don't re-emit history
    if comm_off == 0 and COMM.exists():
        comm_off = COMM.stat().st_size
    if f47_off == 0 and F47.exists():
        f47_off = F47.stat().st_size

    print(f"[watcher] Wren observing at {utc()} — comm@{comm_off} f47@{f47_off} inbox={len(seen_files)}", flush=True)

    while True:
        try:
            comm_off = tail_jsonl(COMM, comm_off, "boardroom_commentary")
            f47_off  = tail_jsonl(F47, f47_off, "f47_records")
            seen_files = scan_inbox(seen_files)
            save_state({
                "comm_offset": comm_off,
                "f47_offset": f47_off,
                "seen_files": list(seen_files),
                "last_tick": utc(),
            })
        except Exception as e:
            print(f"[watcher] tick err: {e}", flush=True)
        time.sleep(args.poll)

if __name__ == "__main__":
    main()
