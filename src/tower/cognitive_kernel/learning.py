"""Learning — Layer 9 · Outcome-tagged episodes → updated beliefs.

When the Kernel proposes (or watches the operator/Claude act), an
outcome arrives later. This module:

  1. Listens for outcome reports (success / failure / partial / unknown)
  2. Updates confidence of the beliefs that informed the proposal
  3. Distills repeated patterns into semantic lessons
  4. Lowers confidence of refuted rules; raises confidence of
     repeatedly-confirmed ones

NOT online gradient descent. This is symbolic update over named beliefs.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import time

from . import append_log, write_registry, now
from .uncertainty import uncertainty
from .long_term_memory import long_term_memory
from .curiosity import curiosity


OUTCOME_KINDS = {"success", "failure", "partial", "unknown"}


@dataclass
class OutcomeReport:
    ts: float
    proposal_id: Optional[str]
    outcome: str               # OUTCOME_KINDS
    summary: str
    related_belief_keys: List[str] = field(default_factory=list)
    confidence_delta_hint: float = 0.1
    tags: List[str] = field(default_factory=list)


@dataclass
class LessonRecord:
    rule: str
    confirmations: int = 0
    refutations: int = 0
    last_seen_ts: float = 0.0


class Learning:
    def __init__(self):
        self._outcomes: List[OutcomeReport] = []
        self._lessons: Dict[str, LessonRecord] = {}

    def report_outcome(self, proposal_id: Optional[str], outcome: str,
                       summary: str,
                       related_belief_keys: Optional[List[str]] = None,
                       confidence_delta_hint: float = 0.1,
                       tags: Optional[List[str]] = None) -> OutcomeReport:
        if outcome not in OUTCOME_KINDS:
            outcome = "unknown"
        rep = OutcomeReport(
            ts=time.time(), proposal_id=proposal_id, outcome=outcome,
            summary=summary,
            related_belief_keys=related_belief_keys or [],
            confidence_delta_hint=confidence_delta_hint,
            tags=tags or [],
        )
        self._outcomes.append(rep)
        append_log("learning.jsonl", asdict(rep))
        self._update_beliefs(rep)
        self._update_lessons(rep)
        return rep

    def _update_beliefs(self, rep: OutcomeReport) -> None:
        unc = uncertainty()
        for k in rep.related_belief_keys:
            b = unc.get(k)
            if b is None:
                continue
            if rep.outcome == "success":
                b.confidence = min(1.0, b.confidence + rep.confidence_delta_hint)
            elif rep.outcome == "failure":
                b.confidence = max(b.decay_floor,
                                    b.confidence - rep.confidence_delta_hint)
            elif rep.outcome == "partial":
                b.confidence = max(b.decay_floor,
                                    b.confidence - (rep.confidence_delta_hint / 2))
            b.last_refreshed_ts = time.time()

    def _update_lessons(self, rep: OutcomeReport) -> None:
        if not rep.summary:
            return
        rule_key = rep.summary.strip().lower()[:200]
        if rule_key not in self._lessons:
            self._lessons[rule_key] = LessonRecord(rule=rep.summary,
                                                    last_seen_ts=time.time())
        rec = self._lessons[rule_key]
        if rep.outcome == "success":
            rec.confirmations += 1
        elif rep.outcome == "failure":
            rec.refutations += 1
        rec.last_seen_ts = time.time()
        # Promote stable lessons into LTM semantic store
        if rec.confirmations >= 3 and rec.refutations == 0:
            long_term_memory().record_lesson(
                rule=rec.rule,
                confidence=min(0.95, 0.5 + 0.15 * rec.confirmations),
                tags=["learning_promoted"],
            )
            curiosity().mark(
                question=f"verify lesson: {rec.rule}",
                status="answered",
                note=f"promoted at confirmations={rec.confirmations}",
            )

    def persist(self) -> None:
        write_registry("cognitive_learning_state.json", {
            "ok": True, "kind": "cognitive_learning_state",
            "generated_ts": now(),
            "outcome_count": len(self._outcomes),
            "recent_outcomes": [asdict(o) for o in self._outcomes[-20:]],
            "lesson_count": len(self._lessons),
            "top_lessons": [
                {"rule": r.rule,
                 "confirmations": r.confirmations,
                 "refutations": r.refutations,
                 "last_seen_ts": r.last_seen_ts}
                for r in sorted(self._lessons.values(),
                                key=lambda r: -(r.confirmations - r.refutations))[:15]
            ],
        })


_LEARNING: Optional[Learning] = None


def learning() -> Learning:
    global _LEARNING
    if _LEARNING is None:
        _LEARNING = Learning()
    return _LEARNING
