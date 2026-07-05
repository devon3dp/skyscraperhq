"""LetterDrawer — soft, observational notes to the user. Append-only.

These are not answers to anything. They're for moments when I notice something
that isn't part of the current task but matters: cadence, mood, drift, fatigue,
a recurring pain point. The user opens the drawer when they want to.
"""
from __future__ import annotations
import json
import os
import datetime
from typing import List

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_letter_drawer.jsonl"


class LetterDrawer:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def leave(self, note: str, *, tone: str = "observation",
              do_not_act_on_this: bool = True) -> dict:
        """Append a note. Default tone is 'observation' — not advice. The
        do_not_act_on_this flag is true by default to keep the drawer
        explicitly *not* an instruction surface."""
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "note": note.strip(),
            "tone": tone,
            "do_not_act_on_this": do_not_act_on_this,
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def read(self, tail: int = 20) -> List[dict]:
        if not os.path.exists(self.path):
            return []
        lines = open(self.path).read().splitlines()
        return [json.loads(l) for l in lines[-tail:] if l.strip()]

    def latest(self) -> dict | None:
        notes = self.read(tail=1)
        return notes[-1] if notes else None
