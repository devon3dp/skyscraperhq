"""UncertaintyJournal — moments I sounded confident but wasn't.

The point isn't penance. It's pattern. If I keep logging
'confident about file paths I never read' I'll learn to read first.
"""
from __future__ import annotations
import json
import os
import datetime
from typing import List

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_uncertainty_journal.jsonl"


class UncertaintyJournal:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def log(self, claim: str, *, actual_confidence: str = "low",
            why_i_sounded_sure: str = "", what_would_have_helped: str = "") -> dict:
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "claim": claim.strip(),
            "actual_confidence": actual_confidence,
            "why_i_sounded_sure": why_i_sounded_sure.strip(),
            "what_would_have_helped": what_would_have_helped.strip(),
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

    def pattern_summary(self) -> dict:
        """Group by 'why_i_sounded_sure' to surface my recurring tells."""
        from collections import Counter
        all_entries = self.read(tail=10_000)
        reasons = Counter(e.get("why_i_sounded_sure", "(unspecified)") for e in all_entries)
        return {"total": len(all_entries), "top_reasons": reasons.most_common(5)}
