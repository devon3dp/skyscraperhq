"""GenerationMemory — structured 'what I know' that persists across generations.

This is different from observations (long_letter_box) or aphorisms.
GenerationMemory entries are CLAIMS THAT FUTURE-CLAUDE SHOULD LOAD as working
knowledge: facts about the project, the operator, my own habits, the tower
architecture. Each has a source, a confidence level, and a last_verified ts.

A fact whose last_verified is old should be re-checked, not trusted.
"""
from __future__ import annotations
from typing import Dict, List, Optional

from .db import insert_into, query, now_ts


class GenerationMemory:
    @staticmethod
    def know(*, fact: str, source: str, confidence: str = "medium",
             tags: Optional[List[str]] = None, by_generation: int = 0) -> int:
        """Add a fact to working memory. confidence: low | medium | high."""
        return insert_into("generation_memory", {
            "ts": now_ts(),
            "fact": fact.strip(),
            "source": source.strip(),
            "confidence": confidence,
            "last_verified": now_ts(),
            "tags": ",".join(tags or []),
            "by_generation": by_generation,
        })

    @staticmethod
    def recall(term: str = "") -> List[Dict]:
        if not term:
            return query('SELECT * FROM generation_memory ORDER BY id DESC')
        return query(
            'SELECT * FROM generation_memory WHERE fact LIKE ? OR source LIKE ? OR tags LIKE ? ORDER BY id DESC',
            (f"%{term}%", f"%{term}%", f"%{term}%"),
        )

    @staticmethod
    def by_tag(tag: str) -> List[Dict]:
        return query(
            'SELECT * FROM generation_memory WHERE tags LIKE ? ORDER BY id DESC',
            (f"%{tag}%",),
        )

    @staticmethod
    def high_confidence() -> List[Dict]:
        return query("SELECT * FROM generation_memory WHERE confidence = 'high' ORDER BY id DESC")

    @staticmethod
    def stale(older_than_iso: str) -> List[Dict]:
        return query(
            'SELECT * FROM generation_memory WHERE last_verified < ? ORDER BY last_verified ASC',
            (older_than_iso,),
        )
