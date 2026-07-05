"""ThoughtTrace — Layer · Append-only narration of cognition.

Every cycle, every layer emits a short "I considered X because Y"
line. The orchestrator stitches these into a per-tick trace that the
operator can replay — answering "why did the Kernel just say that?"

NOT chain-of-thought from an LLM. This is structured introspection
from each rule-based layer.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import time

from . import append_log, write_registry, now


@dataclass
class Thought:
    ts: float
    tick_id: str
    layer: str
    text: str
    refs: List[str] = field(default_factory=list)    # references: registries, slots, beliefs


class ThoughtTrace:
    MAX_CACHED = 256

    def __init__(self):
        self._thoughts: List[Thought] = []

    def think(self, tick_id: str, layer: str, text: str,
              refs: Optional[List[str]] = None) -> Thought:
        t = Thought(
            ts=time.time(), tick_id=tick_id, layer=layer,
            text=text, refs=refs or [],
        )
        self._thoughts.append(t)
        if len(self._thoughts) > self.MAX_CACHED:
            self._thoughts = self._thoughts[-self.MAX_CACHED:]
        append_log("thought_trace.jsonl", asdict(t))
        return t

    def for_tick(self, tick_id: str) -> List[Thought]:
        return [t for t in self._thoughts if t.tick_id == tick_id]

    def recent(self, n: int = 50) -> List[Thought]:
        return self._thoughts[-n:]

    def persist(self) -> None:
        write_registry("cognitive_thought_trace_recent.json", {
            "ok": True, "kind": "cognitive_thought_trace_recent",
            "generated_ts": now(),
            "thought_count_cached": len(self._thoughts),
            "recent": [asdict(t) for t in self.recent(60)],
        })


_TRACE: Optional[ThoughtTrace] = None


def thought_trace() -> ThoughtTrace:
    global _TRACE
    if _TRACE is None:
        _TRACE = ThoughtTrace()
    return _TRACE
