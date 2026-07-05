"""Reflection — Layer 6 · Periodic introspection.

Asks the Kernel two questions on a cadence:
  1. What did I just observe / conclude / propose? Was it consistent
     with my goals?
  2. What is my biggest known gap, and what would close it?

Outputs:
  - Reflection notes appended to long-term semantic memory
  - Updates to self_model.known_gaps
  - New curiosity items
  - Sometimes a new goal
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import time

from . import append_log, write_registry, now
from .working_memory import blackboard
from .self_model import self_model
from .curiosity import curiosity
from .long_term_memory import long_term_memory
from .uncertainty import uncertainty
from .goals import goals
from .contradiction import contradiction_detector


@dataclass
class ReflectionNote:
    ts: float
    section: str            # "consistency" | "gap" | "self_assessment" | "lesson"
    text: str
    tags: List[str] = field(default_factory=list)


class Reflection:
    def __init__(self):
        self._notes: List[ReflectionNote] = []

    def reflect_once(self) -> List[ReflectionNote]:
        bb = blackboard()
        sm = self_model()
        cur = curiosity()
        ltm = long_term_memory()
        unc = uncertainty()
        gs = goals()
        cd = contradiction_detector()
        notes: List[ReflectionNote] = []

        # 1. Consistency: any contradictions live?
        contras = cd.scan()
        if contras:
            text = (f"Contradictions live: {len(contras)} pairs. "
                    "Confidence reduced on conflicting beliefs. "
                    "Resolution items filed in curiosity queue.")
            notes.append(ReflectionNote(time.time(), "consistency", text,
                                        tags=["contradiction"]))
            ltm.record_lesson(
                rule=f"contradiction_pattern_seen:{contras[0].note}",
                confidence=0.6,
                tags=["contradiction"],
            )

        # 2. Gap assessment
        gaps = sm.known_gaps[:10]
        if gaps:
            text = (f"Known gaps in topic table: {len(gaps)} entries. "
                    f"Highest-traffic: {gaps[0]}. "
                    "Surface to operator and propose handler additions.")
            notes.append(ReflectionNote(time.time(), "gap", text, tags=["gap"]))
            for g in gaps[:3]:
                cur.add(question=f"add topic handler for intent: {g}",
                        source="reflection", priority=0.65)

        # 3. Self-assessment from SelfModel
        snap = sm.snapshot()
        text = (f"Self-snapshot: {snap['topic_count']} topics known, "
                f"{snap['registry_count']} registries observed, "
                f"{snap['gap_count']} gaps tracked. "
                f"Working memory: {len(bb.all_slots())}/{bb.capacity} slots.")
        notes.append(ReflectionNote(time.time(), "self_assessment", text,
                                    tags=["self_model"]))

        # 4. Low-confidence beliefs
        low = unc.low_confidence_keys(0.4)
        if low:
            text = (f"Low-confidence beliefs ({len(low)}): {low[:6]}. "
                    "These need refresh before being cited to operator.")
            notes.append(ReflectionNote(time.time(), "lesson", text,
                                        tags=["uncertainty"]))
            ltm.record_lesson(
                rule="low_confidence_beliefs_require_refresh_before_citation",
                confidence=0.85,
                tags=["uncertainty", "epistemic_hygiene"],
            )

        # 5. Goal alignment hint
        active = gs.active()
        if active:
            text = (f"Active goals: {len(active)}. Top: '{active[0].name}'. "
                    f"Attention should weight focus_keys: {gs.active_focus_keys()[:6]}.")
            notes.append(ReflectionNote(time.time(), "consistency", text,
                                        tags=["goals"]))

        self._notes.extend(notes)
        for n in notes:
            append_log("reflection.jsonl", {
                "section": n.section, "text": n.text, "tags": n.tags,
            })
        return notes

    def persist(self) -> None:
        write_registry("cognitive_reflection_state.json", {
            "ok": True, "kind": "cognitive_reflection_state",
            "generated_ts": now(),
            "note_count_session": len(self._notes),
            "recent_notes": [asdict(n) for n in self._notes[-20:]],
        })


_REFLECTION: Optional[Reflection] = None


def reflection() -> Reflection:
    global _REFLECTION
    if _REFLECTION is None:
        _REFLECTION = Reflection()
    return _REFLECTION
