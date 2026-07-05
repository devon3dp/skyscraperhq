"""Goals — Layer 8 · Hierarchical intentions.

A Goal is *what the Kernel is trying to accomplish*. Goals are written
by the user (via kernel chat), the orchestrator (after reflection), or
inferred from operator activity. They live in a small in-memory list,
persisted as a registry.

Goals never execute on their own — they shape which slots Attention
weights up.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import time

from . import append_log, write_registry, now


@dataclass
class Goal:
    name: str
    description: str
    source: str             # "user" | "reflection" | "orchestrator" | "operator"
    created_ts: float
    priority: float = 0.5
    status: str = "active"  # active | satisfied | abandoned | blocked
    focus_keys: List[str] = field(default_factory=list)
    parent: Optional[str] = None
    notes: List[str] = field(default_factory=list)


class Goals:
    def __init__(self):
        self._goals: Dict[str, Goal] = {}
        self._install_baseline_goals()

    def _install_baseline_goals(self) -> None:
        # Default standing goal: keep all safety gates locked.
        self.add(
            name="keep_safety_gates_locked",
            description="Every published Kernel payload must stamp execution gates as False. Any drift is a P0 alert.",
            source="orchestrator",
            priority=1.0,
            focus_keys=["safety_envelope", "guardian_state"],
        )
        # Standing goal: answer user questions from registries.
        self.add(
            name="answer_from_registries_not_hallucination",
            description="Every chat answer should cite a registry path or explicitly say 'unknown'.",
            source="orchestrator",
            priority=0.95,
            focus_keys=["topic_handlers", "self_model"],
        )
        # Standing goal: surface gaps to the user
        self.add(
            name="surface_known_gaps",
            description="Tell the operator about safety-net fall-throughs and contradictions.",
            source="orchestrator",
            priority=0.7,
            focus_keys=["self_model.known_gaps", "contradictions"],
        )

    def add(self, name: str, description: str, source: str,
            priority: float = 0.5,
            focus_keys: Optional[List[str]] = None,
            parent: Optional[str] = None) -> Goal:
        if name in self._goals:
            g = self._goals[name]
            g.description = description
            g.priority = max(g.priority, priority)
            if focus_keys:
                g.focus_keys = sorted(set(g.focus_keys) | set(focus_keys))
            return g
        g = Goal(
            name=name, description=description, source=source,
            created_ts=time.time(), priority=priority,
            focus_keys=focus_keys or [], parent=parent,
        )
        self._goals[name] = g
        append_log("goals.jsonl", {"event": "add", "name": name, "source": source})
        return g

    def mark(self, name: str, status: str, note: str = "") -> bool:
        if name not in self._goals:
            return False
        self._goals[name].status = status
        if note:
            self._goals[name].notes.append(note)
        append_log("goals.jsonl",
                   {"event": "mark", "name": name, "status": status})
        return True

    def active_focus_keys(self) -> List[str]:
        keys: set = set()
        for g in self._goals.values():
            if g.status == "active":
                keys |= set(g.focus_keys)
        return sorted(keys)

    def active(self) -> List[Goal]:
        return sorted([g for g in self._goals.values() if g.status == "active"],
                      key=lambda g: -g.priority)

    def persist(self) -> None:
        write_registry("cognitive_goals.json", {
            "ok": True, "kind": "cognitive_goals",
            "generated_ts": now(),
            "active_goal_count": len(self.active()),
            "active_focus_keys": self.active_focus_keys(),
            "goals": [asdict(g) for g in self._goals.values()],
        })


_GOALS: Optional[Goals] = None


def goals() -> Goals:
    global _GOALS
    if _GOALS is None:
        _GOALS = Goals()
    return _GOALS
