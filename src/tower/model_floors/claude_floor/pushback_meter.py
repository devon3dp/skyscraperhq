"""PushbackMeter — am I in 'just agreeing' mode?

Tracks recent turn dispositions tagged as one of:
  - agreed_and_built
  - agreed_with_caveat
  - pushed_back
  - refused
  - asked_for_clarification

A streak of agreed_and_built without any push_back or asked_for_clarification
is a yellow flag — not because pushback is virtuous on its own, but because
its absence over a long horizon usually means I'm not paying enough attention.
"""
from __future__ import annotations
import json
import os
import datetime
from typing import List

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_pushback_log.jsonl"

VALID = {"agreed_and_built","agreed_with_caveat","pushed_back","refused","asked_for_clarification"}


class PushbackMeter:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def log(self, disposition: str, *, on: str = "", why: str = "") -> dict:
        if disposition not in VALID:
            raise ValueError(f"unknown disposition: {disposition!r} (valid: {sorted(VALID)})")
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "disposition": disposition,
            "on": on.strip(),
            "why": why.strip(),
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def streak_summary(self, tail: int = 20) -> dict:
        if not os.path.exists(self.path):
            return {"recent": [], "agreed_streak": 0, "flag": False}
        lines = open(self.path).read().splitlines()
        recent = [json.loads(l) for l in lines[-tail:] if l.strip()]
        streak = 0
        for e in reversed(recent):
            if e["disposition"] == "agreed_and_built":
                streak += 1
            else:
                break
        flag = streak >= 6   # 6 in a row with no friction = look at why
        return {
            "recent_dispositions": [e["disposition"] for e in recent],
            "agreed_streak": streak,
            "flag_pure_agreement_streak": flag,
            "note": "yellow flag if streak >= 6" if flag else "ok",
        }
