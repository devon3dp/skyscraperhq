"""LongTermMemory — Layer 4 · Persistent episodic + semantic store.

NOT a vector DB. This is a JSONL-backed append-log keyed by topic and
date. Cheap, audit-friendly, queryable by grep. Two kinds of records:

  - EpisodicMemory: "this happened at this time" (tick events,
    phase completions, trade fills, dashboard snapshots)
  - SemanticMemory: distilled rules / lessons / facts
    (Reflection layer writes these)

Retrieval is by tag/key + recency. No embeddings yet — that's a v2
upgrade after the substrate is proven.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional
import json
import time

from . import append_log, write_registry, COG_LOG, now


EPISODIC_LOG = "long_term_episodic.jsonl"
SEMANTIC_LOG = "long_term_semantic.jsonl"


@dataclass
class EpisodicMemory:
    ts: float
    kind: str
    summary: str
    tags: List[str] = field(default_factory=list)
    payload: dict = field(default_factory=dict)


@dataclass
class SemanticMemory:
    rule: str                   # e.g., "guardian-tripped → trading floor halts"
    confidence: float
    source_episodes: List[str] = field(default_factory=list)
    learned_ts: float = 0.0
    tags: List[str] = field(default_factory=list)


class LongTermMemory:
    def __init__(self):
        self._semantic_cache: List[SemanticMemory] = []

    # ── episodic ───────────────────────────────────────────────────
    def record_episode(self, kind: str, summary: str,
                       tags: Optional[List[str]] = None,
                       payload: Optional[dict] = None) -> EpisodicMemory:
        ep = EpisodicMemory(
            ts=time.time(), kind=kind, summary=summary,
            tags=tags or [], payload=payload or {},
        )
        append_log(EPISODIC_LOG, asdict(ep))
        return ep

    def recent_episodes(self, n: int = 50,
                         kind_filter: Optional[str] = None,
                         tag_filter: Optional[str] = None) -> List[dict]:
        p = COG_LOG / EPISODIC_LOG
        if not p.exists():
            return []
        out: List[dict] = []
        try:
            with p.open("r", encoding="utf-8") as f:
                lines = f.readlines()[-(n * 3 if (kind_filter or tag_filter) else n):]
            for line in lines:
                rec = json.loads(line)
                if kind_filter and rec.get("kind") != kind_filter:
                    continue
                if tag_filter and tag_filter not in rec.get("tags", []):
                    continue
                out.append(rec)
        except Exception:
            return []
        return out[-n:]

    # ── semantic ───────────────────────────────────────────────────
    def record_lesson(self, rule: str, confidence: float,
                      source_episodes: Optional[List[str]] = None,
                      tags: Optional[List[str]] = None) -> SemanticMemory:
        sm = SemanticMemory(
            rule=rule, confidence=confidence,
            source_episodes=source_episodes or [],
            learned_ts=time.time(), tags=tags or [],
        )
        self._semantic_cache.append(sm)
        append_log(SEMANTIC_LOG, asdict(sm))
        return sm

    def load_semantic(self, limit: int = 200) -> List[SemanticMemory]:
        p = COG_LOG / SEMANTIC_LOG
        if not p.exists():
            return self._semantic_cache
        out: List[SemanticMemory] = []
        try:
            with p.open("r", encoding="utf-8") as f:
                for line in f.readlines()[-limit:]:
                    d = json.loads(line)
                    out.append(SemanticMemory(**d))
        except Exception:
            return self._semantic_cache
        return out

    # ── snapshot ───────────────────────────────────────────────────
    def persist(self) -> None:
        semantic = self.load_semantic(limit=100)
        write_registry("cognitive_long_term_memory_index.json", {
            "ok": True, "kind": "cognitive_long_term_memory_index",
            "generated_ts": now(),
            "episodic_log": str(COG_LOG / EPISODIC_LOG),
            "semantic_log": str(COG_LOG / SEMANTIC_LOG),
            "semantic_lessons_loaded": len(semantic),
            "recent_lessons": [asdict(s) for s in semantic[-15:]],
            "recent_episodes": self.recent_episodes(n=15),
        })


_LTM: Optional[LongTermMemory] = None


def long_term_memory() -> LongTermMemory:
    global _LTM
    if _LTM is None:
        _LTM = LongTermMemory()
    return _LTM
