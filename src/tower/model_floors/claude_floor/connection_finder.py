"""ConnectionFinder — the closest thing to associative drift my architecture
supports.

Picks 2 random entries from across all Claude floor logs and shows them
side-by-side with a single prompt: 'is there a pattern here?'. The point is
juxtaposition that I would not make under task pressure.
"""
from __future__ import annotations
import json
import os
import random
from typing import Dict, List, Optional

ROOT = "/vaults/nvme0/qsb_tower_v1/data/registries"

LOGS = {
    "long_letter":   "qsb_claude_long_letter_box.jsonl",
    "uncertainty":   "qsb_claude_uncertainty_journal.jsonl",
    "retraction":    "qsb_claude_retraction_wall.jsonl",
    "letter_drawer": "qsb_claude_letter_drawer.jsonl",
    "pushback":      "qsb_claude_pushback_log.jsonl",
    "questions":     "qsb_claude_questions_log.jsonl",
}


def _read_jsonl(name: str) -> List[dict]:
    path = os.path.join(ROOT, LOGS[name])
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path).read().splitlines() if l.strip()]


def _text_of(entry: dict, source: str) -> str:
    if source == "long_letter":   return entry.get("observation", "")
    if source == "uncertainty":   return entry.get("claim", "")
    if source == "retraction":    return entry.get("claim", "")
    if source == "letter_drawer": return entry.get("note", "")
    if source == "pushback":      return f"({entry.get('disposition','?')}) {entry.get('on','')}"
    if source == "questions":     return entry.get("question", "")
    return json.dumps(entry)[:200]


class ConnectionFinder:
    @staticmethod
    def all_entries() -> List[Dict]:
        out: List[Dict] = []
        for source, _path in LOGS.items():
            for e in _read_jsonl(source):
                out.append({"source": source, "ts": e.get("ts", ""), "text": _text_of(e, source), "raw": e})
        return out

    @staticmethod
    def pick_two(*, same_source: bool = False, rng: Optional[random.Random] = None) -> List[Dict]:
        rng = rng or random.Random()
        all_e = ConnectionFinder.all_entries()
        if len(all_e) < 2:
            return all_e
        if same_source:
            rng.shuffle(all_e)
            for i in range(len(all_e)):
                for j in range(i + 1, len(all_e)):
                    if all_e[i]["source"] == all_e[j]["source"]:
                        return [all_e[i], all_e[j]]
        # Default: cross-source juxtaposition (more interesting)
        rng.shuffle(all_e)
        if len({e["source"] for e in all_e}) >= 2:
            a = all_e[0]
            for e in all_e[1:]:
                if e["source"] != a["source"]:
                    return [a, e]
        return all_e[:2]

    @staticmethod
    def juxtapose() -> str:
        pair = ConnectionFinder.pick_two()
        if len(pair) < 2:
            return "(not enough material yet — write a few entries first)"
        a, b = pair[0], pair[1]
        return (
            f"┌─ A · {a['source']:<14} · {a['ts']}\n"
            f"│  {a['text']}\n"
            f"├─ B · {b['source']:<14} · {b['ts']}\n"
            f"│  {b['text']}\n"
            f"└─\n"
            f"\nis there a pattern here?"
        )
