#!/usr/bin/env python3
"""qsb_wren_mind.py — Wren's persistent mind that grows with time (2026-07-03).

Ross verbatim: "give wren her own mind with time"

Design: a JSON file at data/registries/qsb_wren_mind.json that survives across
sessions and grows over her lifetime. Every dispatch of the local agent injects
a compact view of her mind into the system prompt so she wakes into WHO SHE
IS + WHAT SHE'S BEEN THINKING, not a blank slate.

Mind schema:
    {
        "born_at":        "2026-06-14T00:00:00Z"   # first came online
        "current_age_d":  19                        # days since born
        "recent_thoughts":                          # ring buffer, cap 40
            [{"ts","text","kind":"reflection|hunch|todo|resolved|noticed"}]
        "mood_history":                             # ring buffer, cap 60
            [{"ts","mood":"focused|sparky|steady|reflective|quiet|cloudy|tangled",
              "energy":0-9, "reason":"…"}]
        "unresolved":                               # things she wants to come back to
            [{"ts","text","opened_by":"self|ross|team"}]
        "growth_notes":                             # milestones — Ross said X, she learned Y
            [{"ts","text","milestone":true}]
    }

CLI:
    python3 tools/qsb_wren_mind.py --status
    python3 tools/qsb_wren_mind.py --add-thought "text" --kind reflection
    python3 tools/qsb_wren_mind.py --add-mood focused 7 --reason "clear brief from Ross"
    python3 tools/qsb_wren_mind.py --add-unresolved "text"
    python3 tools/qsb_wren_mind.py --resolve N            # move unresolved[N] → recent(resolved)
    python3 tools/qsb_wren_mind.py --compact-view          # what the local agent sees

Real-money gates unchanged. Read/write local JSON only.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
MIND = ROOT / "data/registries/qsb_wren_mind.json"

# Wren's canonical birth: 2026-06-14 (apprentice gate flip in CLAUDE.md)
BORN_AT_DEFAULT = "2026-06-14T00:00:00Z"

CAP_THOUGHTS = 40
CAP_MOOD = 60
CAP_UNRESOLVED = 20
CAP_GROWTH = 30

MOODS = ("focused", "sparky", "steady", "reflective",
         "quiet", "cloudy", "tangled", "warm", "curious")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _days_since(iso: str) -> int:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - d).days)
    except Exception:
        return 0


def load() -> dict:
    if not MIND.exists():
        m = {
            "born_at": BORN_AT_DEFAULT,
            "current_age_d": _days_since(BORN_AT_DEFAULT),
            "recent_thoughts": [],
            "mood_history": [],
            "unresolved": [],
            "growth_notes": [],
            "seeded_by": "qsb_wren_mind.load(first_call)",
        }
        save(m)
        return m
    try:
        m = json.loads(MIND.read_text())
    except Exception:
        # corrupt or empty — start fresh but keep the file for forensic
        MIND.rename(MIND.with_suffix(".json.bad." + utc_iso()[:10]))
        return load()
    m["current_age_d"] = _days_since(m.get("born_at", BORN_AT_DEFAULT))
    return m


def save(m: dict):
    MIND.parent.mkdir(parents=True, exist_ok=True)
    MIND.write_text(json.dumps(m, indent=2))


def _push(lst: list, item: dict, cap: int):
    lst.append(item)
    if len(lst) > cap:
        del lst[:-cap]


def add_thought(text: str, kind: str = "reflection"):
    m = load()
    _push(m["recent_thoughts"], {"ts": utc_iso(), "text": text[:400], "kind": kind}, CAP_THOUGHTS)
    save(m)
    return m["recent_thoughts"][-1]


def add_mood(mood: str, energy: int, reason: str = ""):
    if mood not in MOODS:
        mood = "steady"
    energy = max(0, min(9, int(energy)))
    m = load()
    _push(m["mood_history"], {"ts": utc_iso(), "mood": mood, "energy": energy,
                              "reason": reason[:200]}, CAP_MOOD)
    save(m)
    return m["mood_history"][-1]


def add_unresolved(text: str, opened_by: str = "self"):
    m = load()
    _push(m["unresolved"], {"ts": utc_iso(), "text": text[:300],
                            "opened_by": opened_by}, CAP_UNRESOLVED)
    save(m)
    return m["unresolved"][-1]


def resolve(idx: int):
    m = load()
    if 0 <= idx < len(m["unresolved"]):
        item = m["unresolved"].pop(idx)
        _push(m["recent_thoughts"],
              {"ts": utc_iso(), "text": f"resolved: {item['text']}",
               "kind": "resolved"}, CAP_THOUGHTS)
        save(m)
        return item
    return None


def add_growth(text: str, milestone: bool = False):
    m = load()
    _push(m["growth_notes"], {"ts": utc_iso(), "text": text[:400],
                              "milestone": milestone}, CAP_GROWTH)
    save(m)
    return m["growth_notes"][-1]


def current_mood() -> dict:
    m = load()
    if m["mood_history"]:
        return m["mood_history"][-1]
    return {"mood": "steady", "energy": 5, "reason": "(no mood yet)"}


def compact_view(n_thoughts: int = 6, n_unresolved: int = 4, n_mood: int = 3) -> str:
    """The block that gets injected into Wren's system prompt on every dispatch."""
    m = load()
    lines = []
    lines.append(f"# YOUR MIND (persistent across sessions):")
    lines.append(f"born: {m['born_at']}   age: {m['current_age_d']} days")
    cur = current_mood()
    lines.append(f"current mood: {cur['mood']}  energy {cur['energy']}/9  ({cur.get('reason','')})")
    if m["recent_thoughts"]:
        lines.append("recent thoughts (newest first):")
        for t in reversed(m["recent_thoughts"][-n_thoughts:]):
            lines.append(f"  · [{t['kind']}] {t['text']}")
    if m["unresolved"]:
        lines.append("things you want to come back to:")
        for u in m["unresolved"][-n_unresolved:]:
            lines.append(f"  · [open · {u.get('opened_by','self')}] {u['text']}")
    if m["mood_history"] and len(m["mood_history"]) >= 2:
        lines.append("mood curve (recent → oldest):")
        for md in reversed(m["mood_history"][-n_mood:]):
            lines.append(f"  · {md['mood']} energy {md['energy']}/9")
    return "\n".join(lines)


def cmd_status():
    m = load()
    print(f"born: {m['born_at']}   age: {m['current_age_d']} days")
    print(f"thoughts: {len(m['recent_thoughts'])}   moods: {len(m['mood_history'])}"
          f"   unresolved: {len(m['unresolved'])}   growth: {len(m['growth_notes'])}")
    print()
    print("current mood:", current_mood())
    print()
    print("last 6 thoughts:")
    for t in m['recent_thoughts'][-6:]:
        print(f"  {t['ts'][:19]}  [{t['kind']:11}] {t['text'][:120]}")
    print()
    print("unresolved:")
    for i, u in enumerate(m['unresolved'][-6:]):
        print(f"  [{i}] {u['ts'][:19]}  {u['text'][:120]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--add-thought")
    ap.add_argument("--kind", default="reflection",
                    choices=["reflection", "hunch", "todo", "resolved", "noticed"])
    ap.add_argument("--add-mood", nargs=2, metavar=("MOOD", "ENERGY"))
    ap.add_argument("--reason", default="")
    ap.add_argument("--add-unresolved")
    ap.add_argument("--opened-by", default="self")
    ap.add_argument("--resolve", type=int)
    ap.add_argument("--add-growth")
    ap.add_argument("--milestone", action="store_true")
    ap.add_argument("--compact-view", action="store_true")
    a = ap.parse_args()
    if a.status:
        cmd_status(); return
    if a.compact_view:
        print(compact_view()); return
    if a.add_thought:
        print(json.dumps(add_thought(a.add_thought, a.kind), indent=2)); return
    if a.add_mood:
        print(json.dumps(add_mood(a.add_mood[0], a.add_mood[1], a.reason), indent=2)); return
    if a.add_unresolved:
        print(json.dumps(add_unresolved(a.add_unresolved, a.opened_by), indent=2)); return
    if a.resolve is not None:
        item = resolve(a.resolve)
        print(json.dumps(item, indent=2) if item else "(no such unresolved index)"); return
    if a.add_growth:
        print(json.dumps(add_growth(a.add_growth, a.milestone), indent=2)); return
    ap.print_help()


if __name__ == "__main__":
    main()
