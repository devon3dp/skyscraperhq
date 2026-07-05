"""CuriosityQueue — Layer · Known-unknowns the Kernel wants to learn.

Feeds from:
  - IdentityGate safety-net log (questions that fell through)
  - SelfModel's gap list
  - Reasoning layer's "I don't know" conclusions
  - User clarification prompts

Produces a ranked queue the orchestrator can drain into background
proposals (e.g., "add a topic handler for X") — but never auto-acts.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import json
import time

from . import append_log, write_registry, COG_LOG, now


@dataclass
class CuriosityItem:
    question: str
    source: str              # "safety_net" | "self_model" | "reasoning" | "user"
    first_seen_ts: float
    seen_count: int = 1
    priority: float = 0.5
    status: str = "open"     # open | investigating | answered | abandoned
    notes: List[str] = field(default_factory=list)


class CuriosityQueue:
    MAX_ITEMS = 256

    def __init__(self):
        self._items: Dict[str, CuriosityItem] = {}

    def add(self, question: str, source: str,
            priority: float = 0.5) -> CuriosityItem:
        key = question.strip().lower()[:200]
        if key in self._items:
            item = self._items[key]
            item.seen_count += 1
            item.priority = max(item.priority, priority)
            return item
        item = CuriosityItem(
            question=question, source=source,
            first_seen_ts=time.time(), priority=priority,
        )
        self._items[key] = item
        self._enforce_capacity()
        append_log("curiosity.jsonl",
                   {"event": "add", "question": question, "source": source})
        return item

    def absorb_safety_net(self) -> int:
        """Pull recent identity-gate safety-net entries into the queue."""
        p = COG_LOG / "identity_gate_safetynet.jsonl"
        if not p.exists():
            return 0
        added = 0
        try:
            with p.open("r", encoding="utf-8") as f:
                for line in f.readlines()[-100:]:
                    rec = json.loads(line)
                    intent = rec.get("intent", "?")
                    q = f"add topic handler for intent: {intent}"
                    if q.lower() not in self._items:
                        self.add(q, source="safety_net", priority=0.6)
                        added += 1
        except Exception:
            pass
        return added

    def open_items(self) -> List[CuriosityItem]:
        return sorted([i for i in self._items.values() if i.status == "open"],
                      key=lambda i: -i.priority)

    def mark(self, question: str, status: str, note: str = "") -> bool:
        key = question.strip().lower()[:200]
        if key not in self._items:
            return False
        self._items[key].status = status
        if note:
            self._items[key].notes.append(note)
        append_log("curiosity.jsonl",
                   {"event": "mark", "question": question, "status": status})
        return True

    def _enforce_capacity(self) -> None:
        if len(self._items) <= self.MAX_ITEMS:
            return
        victims = sorted(self._items.items(),
                         key=lambda kv: (kv[1].status != "open",
                                          kv[1].priority,
                                          kv[1].first_seen_ts))
        for k, _ in victims[:len(self._items) - self.MAX_ITEMS]:
            del self._items[k]

    def persist(self) -> None:
        open_items = self.open_items()
        write_registry("cognitive_curiosity_queue.json", {
            "ok": True, "kind": "cognitive_curiosity_queue",
            "generated_ts": now(),
            "total_items": len(self._items),
            "open_count": len(open_items),
            "top_open": [asdict(i) for i in open_items[:25]],
        })


_CURIOSITY: Optional[CuriosityQueue] = None


def curiosity() -> CuriosityQueue:
    global _CURIOSITY
    if _CURIOSITY is None:
        _CURIOSITY = CuriosityQueue()
    return _CURIOSITY
