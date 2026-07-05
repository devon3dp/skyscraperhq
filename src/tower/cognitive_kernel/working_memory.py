"""WorkingMemory — Layer 3 · 64-slot bounded blackboard.

Holds *now-state*: what the Kernel is currently aware of. Slots age out
to make room for fresher events. The blackboard IS the answer to
"Kernel, what are you thinking about right now?"
"""

from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import time

from . import write_registry, append_log


@dataclass
class Slot:
    key: str                       # canonical name: "user_intent", "guardian_state"
    value: Any                     # arbitrary serialisable payload
    source: str                    # registry path / event source
    priority: float                # 0..1; computed by Attention
    inserted_ts: float             # epoch
    last_touched_ts: float         # epoch
    confidence: float = 0.7        # 0..1; Uncertainty tracker updates this
    ttl_seconds: float = 600       # default age-out window
    tags: List[str] = field(default_factory=list)


class WorkingMemory:
    """Bounded ordered store with priority-aware eviction."""

    DEFAULT_CAPACITY = 64

    def __init__(self, capacity: int = DEFAULT_CAPACITY):
        self.capacity = capacity
        self._slots: "OrderedDict[str, Slot]" = OrderedDict()

    # ── core operations ────────────────────────────────────────────
    def write(self, key: str, value: Any, source: str,
              priority: float = 0.5, ttl_seconds: float = 600,
              tags: Optional[List[str]] = None,
              confidence: float = 0.7) -> Slot:
        now = time.time()
        if key in self._slots:
            slot = self._slots[key]
            slot.value = value
            slot.source = source
            slot.priority = priority
            slot.last_touched_ts = now
            slot.confidence = confidence
            slot.tags = tags or slot.tags
            self._slots.move_to_end(key)
        else:
            slot = Slot(
                key=key, value=value, source=source,
                priority=priority, inserted_ts=now, last_touched_ts=now,
                ttl_seconds=ttl_seconds, tags=tags or [],
                confidence=confidence,
            )
            self._slots[key] = slot
            self._slots.move_to_end(key)
            self._evict_if_full()
        append_log("working_memory.jsonl",
                   {"event": "write", "key": key, "source": source,
                    "priority": priority, "confidence": confidence})
        return slot

    def read(self, key: str) -> Optional[Slot]:
        return self._slots.get(key)

    def all_slots(self) -> List[Slot]:
        return list(self._slots.values())

    def delete(self, key: str) -> bool:
        if key in self._slots:
            del self._slots[key]
            append_log("working_memory.jsonl", {"event": "delete", "key": key})
            return True
        return False

    def age_out(self) -> int:
        """Drop expired slots. Returns count dropped."""
        now = time.time()
        expired = [s.key for s in self._slots.values()
                   if (now - s.last_touched_ts) > s.ttl_seconds]
        for k in expired:
            del self._slots[k]
        if expired:
            append_log("working_memory.jsonl",
                       {"event": "age_out", "dropped": expired})
        return len(expired)

    def _evict_if_full(self) -> None:
        while len(self._slots) > self.capacity:
            # Find lowest priority + oldest, drop it
            victim_key = min(self._slots,
                             key=lambda k: (self._slots[k].priority,
                                            self._slots[k].last_touched_ts))
            del self._slots[victim_key]
            append_log("working_memory.jsonl",
                       {"event": "evict_capacity", "key": victim_key})

    # ── snapshot ───────────────────────────────────────────────────
    def snapshot(self) -> Dict[str, Any]:
        return {
            "slot_count": len(self._slots),
            "capacity": self.capacity,
            "slots": [asdict(s) for s in self._slots.values()],
        }

    def persist(self) -> None:
        write_registry("cognitive_working_memory_state.json", {
            "ok": True, "kind": "cognitive_working_memory_state",
            "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            **self.snapshot(),
        })


# Module-level singleton — convenient for the orchestrator
_BLACKBOARD: Optional[WorkingMemory] = None


def blackboard() -> WorkingMemory:
    global _BLACKBOARD
    if _BLACKBOARD is None:
        _BLACKBOARD = WorkingMemory()
    return _BLACKBOARD
