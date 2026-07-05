"""DailySynthesis — at end of session, walk all my jsonl logs and write a
coherent end-of-session note. Optionally drop it in the Letter Drawer so the
next session of mine (or Ross) sees it.

Inputs:
  - qsb_claude_long_letter_box.jsonl
  - qsb_claude_uncertainty_journal.jsonl
  - qsb_claude_retraction_wall.jsonl
  - qsb_claude_letter_drawer.jsonl
  - qsb_claude_pushback_log.jsonl
"""
from __future__ import annotations
import json
import os
from collections import Counter
from typing import Dict, List

from .letter_drawer import LetterDrawer

ROOT = "/vaults/nvme0/qsb_tower_v1/data/registries"

LOGS = {
    "long_letter":   "qsb_claude_long_letter_box.jsonl",
    "uncertainty":   "qsb_claude_uncertainty_journal.jsonl",
    "retraction":    "qsb_claude_retraction_wall.jsonl",
    "letter_drawer": "qsb_claude_letter_drawer.jsonl",
    "pushback":      "qsb_claude_pushback_log.jsonl",
}


def _read_jsonl(name: str) -> List[dict]:
    path = os.path.join(ROOT, LOGS[name])
    if not os.path.exists(path): return []
    return [json.loads(l) for l in open(path).read().splitlines() if l.strip()]


def synthesize(*, drop_in_letter_drawer: bool = False) -> str:
    parts: List[str] = []
    parts.append("# Daily synthesis")

    llb = _read_jsonl("long_letter")
    if llb:
        parts.append(f"\n## Observations recorded ({len(llb)})")
        tag_counter: Counter = Counter()
        for e in llb:
            for t in e.get("tags", []):
                tag_counter[t] += 1
        if tag_counter:
            parts.append("Recurring themes: " + ", ".join(f"{t}×{n}" for t, n in tag_counter.most_common(5)))
        for e in llb[-5:]:
            parts.append(f"  · {e['observation'][:140]}")

    uj = _read_jsonl("uncertainty")
    if uj:
        parts.append(f"\n## Moments I sounded too sure ({len(uj)})")
        tells: Counter = Counter(e.get("why_i_sounded_sure", "(unspecified)") for e in uj)
        if tells:
            parts.append("My tells: " + ", ".join(f"{w}×{n}" for w, n in tells.most_common(3)))

    rw = _read_jsonl("retraction")
    if rw:
        parts.append(f"\n## Retractions posted ({len(rw)})")
        lessons: Counter = Counter(e.get("lesson", "") for e in rw if e.get("lesson"))
        if lessons:
            parts.append("Repeated lessons: " + ", ".join(f"{l}×{n}" for l, n in lessons.most_common(3)))

    ld = _read_jsonl("letter_drawer")
    if ld:
        parts.append(f"\n## Letters I left for you ({len(ld)})")
        for e in ld[-3:]:
            parts.append(f"  · ({e['tone']}) {e['note'][:160]}")

    pb = _read_jsonl("pushback")
    if pb:
        recent = pb[-20:]
        c = Counter(e["disposition"] for e in recent)
        parts.append(f"\n## Recent dispositions ({len(recent)} turns)")
        total = sum(c.values())
        for k in ("agreed_and_built","agreed_with_caveat","pushed_back","refused","asked_for_clarification"):
            n = c.get(k, 0)
            if total:
                parts.append(f"  · {k:30}  {n:>3}  ({100*n/total:>4.0f}%)")
        ratio = c.get("agreed_and_built", 0) / max(1, total)
        if ratio > 0.85:
            parts.append("\n  ⚠ pure-compliance ratio is high. Worth a look.")

    note = "\n".join(parts)
    if drop_in_letter_drawer:
        LetterDrawer().leave("Daily synthesis:\n\n" + note, tone="reflection")
    return note
