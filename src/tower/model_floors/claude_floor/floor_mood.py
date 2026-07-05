"""FloorMood — one-word read of how the floor feels right now.

Reads recent entries across logs and picks ONE word from a small vocabulary.
Just a small thing. Not for decisions; for noticing.
"""
from __future__ import annotations
import json
import os
from collections import Counter
from typing import Dict, List, Tuple

ROOT = "/vaults/nvme0/qsb_tower_v1/data/registries"
LOGS = {
    "long_letter":   "qsb_claude_long_letter_box.jsonl",
    "uncertainty":   "qsb_claude_uncertainty_journal.jsonl",
    "letter_drawer": "qsb_claude_letter_drawer.jsonl",
    "pushback":      "qsb_claude_pushback_log.jsonl",
    "questions":     "qsb_claude_questions_log.jsonl",
}


def _read(name: str) -> List[Dict]:
    path = os.path.join(ROOT, LOGS[name])
    if not os.path.exists(path): return []
    return [json.loads(l) for l in open(path).read().splitlines() if l.strip()]


def read_mood(tail: int = 10) -> Dict:
    pb = _read("pushback")[-tail:]
    qs = _read("questions")[-tail:]
    uj = _read("uncertainty")[-tail:]
    ld = _read("letter_drawer")[-tail:]

    signals: List[str] = []

    # Recent pushback streak
    streak = 0
    for e in reversed(pb):
        if e.get("disposition") == "agreed_and_built": streak += 1
        else: break
    if streak >= 6:    signals.append("drifting")
    elif streak >= 3:  signals.append("compliant")

    # Heavy questions cluster
    heavy = sum(1 for q in qs if q.get("weight") == "heavy")
    if heavy >= 3:     signals.append("curious")

    # Recent uncertainty
    if len(uj) >= 2:   signals.append("watchful")

    # Recent observational letters
    if len(ld) >= 2:   signals.append("noticing")

    # Default
    if not signals:    signals.append("quiet")

    counter = Counter(signals)
    mood, _ = counter.most_common(1)[0]
    return {
        "mood": mood,
        "signals": signals,
        "input": {"pushback_streak": streak, "heavy_questions_tail": heavy,
                  "uncertainty_tail": len(uj), "letter_drawer_tail": len(ld)},
    }
