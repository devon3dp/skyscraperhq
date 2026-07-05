"""LessonToBelief — Layer · Promote semantic lessons into active beliefs.

A lesson sitting in long_term_semantic.jsonl is inert. This bridge turns
high-confidence lessons into Beliefs the UncertaintyTracker carries, so
they participate in reasoning and contradiction detection.

Bridge rule (default):
  promote a SemanticMemory if confidence >= 0.75 AND it has not yet
  been promoted.

Promotions are recorded so we don't double-load.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Set
import hashlib
import time

from . import append_log, write_registry, now
from .long_term_memory import long_term_memory, SemanticMemory
from .uncertainty import uncertainty


@dataclass
class Promotion:
    rule: str
    belief_key: str
    confidence: float
    promoted_ts: float


class LessonToBelief:
    PROMOTION_THRESHOLD = 0.75

    def __init__(self):
        self._promoted_keys: Set[str] = set()
        self._promotions: List[Promotion] = []

    @staticmethod
    def _belief_key_for(rule: str) -> str:
        h = hashlib.sha256(rule.encode("utf-8")).hexdigest()[:10]
        return f"lesson_{h}"

    def promote_once(self) -> List[Promotion]:
        ltm = long_term_memory()
        unc = uncertainty()
        promoted_now: List[Promotion] = []
        lessons = ltm.load_semantic(limit=300)
        for sm in lessons:
            if sm.confidence < self.PROMOTION_THRESHOLD:
                continue
            key = self._belief_key_for(sm.rule)
            if key in self._promoted_keys:
                continue
            self._promoted_keys.add(key)
            unc.assert_(
                key=key, statement=sm.rule,
                confidence=sm.confidence,
                source="lesson_to_belief",
                half_life_seconds=7200.0,
                tags=list(sm.tags) + ["promoted_lesson"],
            )
            p = Promotion(rule=sm.rule, belief_key=key,
                          confidence=sm.confidence, promoted_ts=time.time())
            self._promotions.append(p)
            promoted_now.append(p)
            append_log("lesson_to_belief.jsonl",
                       {"event": "promote", "belief_key": key,
                        "rule": sm.rule, "confidence": sm.confidence})
        return promoted_now

    def persist(self) -> None:
        write_registry("cognitive_lesson_to_belief_state.json", {
            "ok": True, "kind": "cognitive_lesson_to_belief_state",
            "generated_ts": now(),
            "promoted_lesson_count": len(self._promoted_keys),
            "recent_promotions": [asdict(p) for p in self._promotions[-20:]],
            "promotion_threshold": self.PROMOTION_THRESHOLD,
        })


_BRIDGE: Optional[LessonToBelief] = None


def lesson_to_belief() -> LessonToBelief:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = LessonToBelief()
    return _BRIDGE
