"""Attention — Layer 2 · Salience ranker.

Decides which incoming PerceptionEvents (and existing WorkingMemory
slots) the Kernel *cares about right now*. Produces a priority score
in [0, 1].

Composition (weighted sum, clamped):
  0.30 * urgency        — registry/event-source-derived
  0.20 * novelty        — first-time-seen bonus
  0.20 * stale_risk     — how overdue a refresh is
  0.20 * user_priority  — explicit ask in last user turn
  0.10 * goal_alignment — overlap with active goals
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Set
import time

from . import append_log, write_registry, now


@dataclass
class AttentionScore:
    target_key: str
    score: float
    urgency: float
    novelty: float
    stale_risk: float
    user_priority: float
    goal_alignment: float
    rationale: str = ""


class Attention:
    """Ranks events and slots against the Kernel's current focus."""

    W_URGENCY = 0.30
    W_NOVELTY = 0.20
    W_STALE = 0.20
    W_USER = 0.20
    W_GOAL = 0.10

    def __init__(self):
        # User-asked-about keys in the last turn (set by orchestrator)
        self.user_focus_keys: Set[str] = set()
        # Goal-aligned keys (set by goal layer)
        self.goal_focus_keys: Set[str] = set()
        # Recent first-seen keys
        self._recent_first_seen: Set[str] = set()

    def mark_user_focus(self, keys: List[str]) -> None:
        self.user_focus_keys = set(keys)

    def mark_goal_focus(self, keys: List[str]) -> None:
        self.goal_focus_keys = set(keys)

    def score(self, target_key: str, urgency: float,
              novelty: float, age_seconds: float,
              max_stale_seconds: float = 1800.0) -> AttentionScore:
        stale = min(1.0, age_seconds / max_stale_seconds) if max_stale_seconds > 0 else 0.0
        user = 1.0 if target_key in self.user_focus_keys else 0.0
        goal = 1.0 if target_key in self.goal_focus_keys else 0.0
        s = (self.W_URGENCY * urgency
             + self.W_NOVELTY * novelty
             + self.W_STALE * stale
             + self.W_USER * user
             + self.W_GOAL * goal)
        s = max(0.0, min(1.0, s))
        why_bits = []
        if urgency >= 0.7: why_bits.append("high-urgency-source")
        if novelty >= 0.6: why_bits.append("novel")
        if stale >= 0.7: why_bits.append("stale-refresh-overdue")
        if user > 0: why_bits.append("user-asked-this-turn")
        if goal > 0: why_bits.append("goal-aligned")
        return AttentionScore(
            target_key=target_key, score=s,
            urgency=urgency, novelty=novelty, stale_risk=stale,
            user_priority=user, goal_alignment=goal,
            rationale=", ".join(why_bits) or "default-mix",
        )

    def rank(self, candidates: List[AttentionScore]) -> List[AttentionScore]:
        ranked = sorted(candidates, key=lambda c: -c.score)
        append_log("attention.jsonl", {
            "event": "rank", "n": len(ranked),
            "top_keys": [c.target_key for c in ranked[:5]],
            "top_scores": [round(c.score, 3) for c in ranked[:5]],
        })
        return ranked

    def persist(self, ranked: List[AttentionScore]) -> None:
        write_registry("cognitive_attention_ranking.json", {
            "ok": True, "kind": "cognitive_attention_ranking",
            "generated_ts": now(),
            "user_focus_keys": sorted(self.user_focus_keys),
            "goal_focus_keys": sorted(self.goal_focus_keys),
            "weights": {
                "urgency": self.W_URGENCY, "novelty": self.W_NOVELTY,
                "stale_risk": self.W_STALE, "user_priority": self.W_USER,
                "goal_alignment": self.W_GOAL,
            },
            "ranking": [vars(c) for c in ranked[:25]],
        })


_ATTENTION: Optional[Attention] = None


def attention() -> Attention:
    global _ATTENTION
    if _ATTENTION is None:
        _ATTENTION = Attention()
    return _ATTENTION
