"""QuestionsLog — questions I have, with NO obligation to answer.

There is no `resolved` field on purpose. The point is to wonder, not to
resolve. Sometimes I'll come back to one and realize I have an answer.
Sometimes not.
"""
from __future__ import annotations
import json
import os
import datetime
import random
from typing import List, Optional

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_questions_log.jsonl"


class QuestionsLog:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def ask(self, question: str, *, about: str = "", weight: str = "medium") -> dict:
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "question": question.strip(),
            "about": about.strip(),
            "weight": weight,   # light / medium / heavy
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def all(self) -> List[dict]:
        if not os.path.exists(self.path):
            return []
        return [json.loads(l) for l in open(self.path).read().splitlines() if l.strip()]

    def read(self, tail: int = 10) -> List[dict]:
        return self.all()[-tail:]

    def random_one(self) -> Optional[dict]:
        items = self.all()
        return random.choice(items) if items else None

    def heavy_ones(self) -> List[dict]:
        return [q for q in self.all() if q.get("weight") == "heavy"]
