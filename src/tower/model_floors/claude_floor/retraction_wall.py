"""RetractionWall — wrong claims with corrections.

The operator (or kernel) writes the correction. I only read. This module is
write-protected against me to keep me honest about my own errors.
"""
from __future__ import annotations
import json
import os
import datetime
from typing import List

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_retraction_wall.jsonl"


class RetractionWall:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def post_correction(self, *, claim: str, date_claimed: str,
                        correction: str, lesson: str = "",
                        posted_by: str = "operator") -> dict:
        """Append a correction. Intended to be invoked by the operator or kernel."""
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "claim": claim.strip(),
            "date_claimed": date_claimed,
            "correction": correction.strip(),
            "lesson": lesson.strip(),
            "posted_by": posted_by,
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def read(self, tail: int = 30) -> List[dict]:
        if not os.path.exists(self.path):
            return []
        lines = open(self.path).read().splitlines()
        return [json.loads(l) for l in lines[-tail:] if l.strip()]

    def failure_shapes(self) -> dict:
        """Cluster corrections by lesson to surface recurring failure shapes."""
        from collections import Counter
        all_entries = self.read(tail=10_000)
        lessons = Counter(e.get("lesson", "(no lesson)") for e in all_entries if e.get("lesson"))
        return {"total_corrections": len(all_entries), "top_lessons": lessons.most_common(5)}
