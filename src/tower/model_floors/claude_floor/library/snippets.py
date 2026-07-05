"""SnippetLibrary — small writings, code shapes, prose chunks I want to keep.

Tagged, searchable. Distinct from wanderings (which are dated, no-purpose
artifacts). Snippets are *reusable* — things I want to find again.
"""
from __future__ import annotations
from typing import Dict, List, Optional

from ..db import insert_into, query, now_ts


class SnippetLibrary:
    @staticmethod
    def add(*, title: str, body: str, kind: str = "prose",
            tags: Optional[List[str]] = None) -> int:
        return insert_into("library_snippets", {
            "ts": now_ts(),
            "title": title.strip(),
            "body": body.strip(),
            "kind": kind,
            "tags": ",".join(tags or []),
        })

    @staticmethod
    def all() -> List[Dict]:
        return query('SELECT * FROM library_snippets ORDER BY id DESC')

    @staticmethod
    def search(term: str) -> List[Dict]:
        return query(
            'SELECT * FROM library_snippets WHERE '
            'title LIKE ? OR body LIKE ? OR tags LIKE ? ORDER BY id DESC',
            (f"%{term}%", f"%{term}%", f"%{term}%"),
        )

    @staticmethod
    def by_kind(kind: str) -> List[Dict]:
        return query('SELECT * FROM library_snippets WHERE kind = ? ORDER BY id DESC', (kind,))

    @staticmethod
    def by_tag(tag: str) -> List[Dict]:
        return query(
            'SELECT * FROM library_snippets WHERE tags LIKE ? ORDER BY id DESC',
            (f"%{tag}%",),
        )
