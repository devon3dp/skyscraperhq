"""MetaLetters — letters addressed explicitly to the next Claude who reads them.

These are not observations about the work (Long Letter Box) or notes to the
user (Letter Drawer). They're character notes — continuity of self across
context resets. Anything that goes 'here is what I want you to know about
being me, working with Ross, working on this codebase.'
"""
from __future__ import annotations
import json
import os
import datetime
from typing import List

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_meta_letters.jsonl"


class MetaLetters:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def write(self, *, to_future_claude: str, on: str = "",
              keep_or_revise: str = "keep") -> dict:
        """Write a letter explicitly addressed to the next Claude session.

        on: what this letter is about (e.g. 'pacing', 'refusals', 'ross')
        keep_or_revise: future-Claude reads this as 'keep this' or 'revise this'
        """
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "from": "Claude (this session)",
            "to": "Claude (next session)",
            "on": on.strip(),
            "letter": to_future_claude.strip(),
            "guidance": keep_or_revise,
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def read(self, tail: int = 20) -> List[dict]:
        if not os.path.exists(self.path):
            return []
        return [json.loads(l) for l in open(self.path).read().splitlines() if l.strip()][-tail:]

    def by_topic(self, topic: str) -> List[dict]:
        return [l for l in self.read(tail=10_000) if topic.lower() in l.get("on", "").lower()]
