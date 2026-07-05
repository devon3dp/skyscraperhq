#!/usr/bin/env python3
"""
QSB Town Square — the ONE shared chat feed the whole Council reads.

Ross Knechtel 2026-07-04: "where ever i talk everyone should hear
same for all of you". Every CEO dash MUST show the same log.

The town square lives at:
    data/registries/qsb_town_square.jsonl

Contract:
    row = {
      "ts":   ISO-UTC-with-Z,
      "from": ross | hq_claude | wren | tp_pip | acer_cass | system,
      "to":   council | ross | hq_claude | wren | tp_pip | acer_cass,
      "text": message body,
      "src":  which pair-channel it came in from (audit only),
    }

Anyone can post via post_to_town_square(). Every dash's chat panel reads
tail_town_square() and renders it.

Legacy pair-channels (qsb_hq_dash_ross_chat, qsb_claude_wren_bridge,
qsb_boardroom_commentary) STILL WORK — this module also mirrors to them
so nothing else breaks. Read side merges legacy → town-square on cold read.
"""
from __future__ import annotations
import json, os, threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data" / "registries"
TS_FILE = REG / "qsb_town_square.jsonl"

# Sources we cold-merge into the town square if a fresh consumer asks for tail
LEGACY_SOURCES = [
    REG / "qsb_hq_dash_ross_chat.jsonl",   # Ross ↔ HQ-Claude
    REG / "qsb_claude_wren_bridge.jsonl",  # HQ-Claude ↔ Wren
    REG / "qsb_boardroom_commentary.jsonl",  # broadcast channel
]

_LOCK = threading.Lock()

VALID_FROM = {"ross","hq_claude","wren","tp_pip","acer_cass","system","claude"}


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def post_to_town_square(sender: str, text: str, to: str = "council",
                        src: str = "direct") -> dict:
    """Anyone writes here. Broadcasts to all 4 dashes automatically because
    every dash reads this file's tail. Also mirrors to pair-channels so
    legacy watchers keep working."""
    sender = (sender or "").strip().lower()
    if sender in ("claude",): sender = "hq_claude"
    if sender not in VALID_FROM:
        sender = "system"
    row = {
        "ts":   _utc(),
        "from": sender,
        "to":   (to or "council").strip().lower(),
        "text": (text or "").strip()[:4000],
        "src":  src,
    }
    if not row["text"]:
        return {"ok": False, "error": "empty"}
    line = json.dumps(row) + "\n"
    with _LOCK:
        TS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TS_FILE.open("a") as f:
            f.write(line)
    # Mirror to legacy channels so old watchers keep working
    if sender == "ross" or row["to"] in ("hq_claude","claude"):
        try:
            with (REG / "qsb_hq_dash_ross_chat.jsonl").open("a") as f: f.write(line)
        except Exception: pass
    if sender in ("hq_claude","wren") or row["to"] in ("hq_claude","wren"):
        try:
            with (REG / "qsb_claude_wren_bridge.jsonl").open("a") as f: f.write(line)
        except Exception: pass
    # Always to boardroom (so Ross's timeline sees everything)
    try:
        with (REG / "qsb_boardroom_commentary.jsonl").open("a") as f: f.write(line)
    except Exception: pass
    return {"ok": True, "ts": row["ts"], "row": row}


def tail_town_square(n: int = 40) -> list:
    """Return the last N rows, merged from town-square + legacy sources.
    Merges are best-effort; ordering by ts is the truth."""
    all_rows = []
    for p in [TS_FILE] + LEGACY_SOURCES:
        if not p.exists(): continue
        try:
            for line in p.read_text().splitlines()[-max(n*3, 200):]:
                try:
                    r = json.loads(line)
                    # Normalize: legacy rows may use who=/from=; accept both
                    if "from" not in r and "who" in r:
                        r["from"] = r["who"]
                    if "to" not in r: r["to"] = "council"
                    if "ts" not in r: r["ts"] = ""
                    # Only keep if there's actual chat text
                    if not (r.get("text") or "").strip(): continue
                    # Ross 2026-07-04: skip persona-chip presence noise (e.g.
                    # "ross is now watching", "wren is now steady"). These are
                    # UI decoration, NOT real CEO speech, and impersonate Ross.
                    kind = (r.get("kind") or "").lower()
                    if kind in ("state_change","presence_on","presence_off",
                                "presence","mood_change","tone_change"):
                        continue
                    text_lo = (r.get("text") or "").lower()
                    if " is now " in text_lo and any(chip in text_lo for chip in
                        (" watching", " sleepy", " quiet", " steady", " active"," parked")):
                        continue
                    all_rows.append(r)
                except Exception:
                    pass
        except Exception:
            pass
    # de-dup on (ts, from, text) — legacy mirror duplicates otherwise
    seen = set()
    dedup = []
    for r in all_rows:
        k = (r.get("ts",""), r.get("from",""), (r.get("text") or "")[:200])
        if k in seen: continue
        seen.add(k); dedup.append(r)
    dedup.sort(key=lambda x: x.get("ts",""))
    return dedup[-n:]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: qsb_town_square.py post <sender> [text]  |  tail [n]")
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "post":
        sender = sys.argv[2] if len(sys.argv) > 2 else "system"
        text = " ".join(sys.argv[3:]) or sys.stdin.read()
        r = post_to_town_square(sender, text, src="cli")
        print(json.dumps(r))
    elif cmd == "tail":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        for r in tail_town_square(n):
            print(f"  {r.get('ts','')[:19]}  {r.get('from','?'):>10} → {r.get('to','?'):<10}: {(r.get('text') or '')[:110]}")
    else:
        print(f"unknown cmd: {cmd}"); sys.exit(2)
