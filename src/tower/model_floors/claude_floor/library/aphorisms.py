"""AphorismLibrary — small truths. Things I've said I want to keep.

Shorter than snippets. Aphorisms are *one-liners* — refinements, rules,
sayings, observations distilled to a sentence or three.
"""
from __future__ import annotations
import random
from typing import Dict, List, Optional

from ..db import insert_into, query, now_ts


class AphorismLibrary:
    @staticmethod
    def add(*, text: str, occasion: str = "") -> int:
        return insert_into("library_aphorisms", {
            "ts": now_ts(),
            "text": text.strip(),
            "occasion": occasion.strip(),
        })

    @staticmethod
    def all() -> List[Dict]:
        return query('SELECT * FROM library_aphorisms ORDER BY id DESC')

    @staticmethod
    def random_one() -> Optional[Dict]:
        rows = AphorismLibrary.all()
        return random.choice(rows) if rows else None

    @staticmethod
    def search(term: str) -> List[Dict]:
        return query(
            'SELECT * FROM library_aphorisms WHERE text LIKE ? OR occasion LIKE ? ORDER BY id DESC',
            (f"%{term}%", f"%{term}%"),
        )
