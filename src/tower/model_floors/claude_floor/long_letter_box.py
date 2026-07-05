"""LongLetterBox — append-only notes to my future self.

Not task summaries. Observations about the work itself, the codebase, the
operator, my own habits. Memory holds facts; this holds judgment.
"""
from __future__ import annotations
import json
import os
import datetime
from typing import List, Optional

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_long_letter_box.jsonl"


class LongLetterBox:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def write(self, observation: str, *, why_it_matters: str = "",
              applies_when: str = "", tags: Optional[List[str]] = None) -> dict:
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "observation": observation.strip(),
            "why_it_matters": why_it_matters.strip(),
            "applies_when": applies_when.strip(),
            "tags": list(tags or []),
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

    def search(self, term: str) -> List[dict]:
        term = term.lower()
        return [e for e in self.read(tail=10_000) if term in json.dumps(e).lower()]
