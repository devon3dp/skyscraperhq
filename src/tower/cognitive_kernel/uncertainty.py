"""UncertaintyTracker — Layer · Per-belief confidence.

The Kernel's beliefs are NOT all equally trustworthy. Some come from
freshly-stamped registries (high confidence); others from inferred or
extrapolated state (lower); some from missing files (very low).

This module assigns and decays confidence over time.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import time

from . import append_log, write_registry, now


@dataclass
class Belief:
    key: str
    statement: str
    confidence: float
    source: str
    inserted_ts: float
    last_refreshed_ts: float
    half_life_seconds: float = 3600.0   # 1 hour default
    decay_floor: float = 0.05
    tags: List[str] = field(default_factory=list)

    def current_confidence(self) -> float:
        """Exponential decay toward decay_floor."""
        if self.half_life_seconds <= 0:
            return self.confidence
        age = max(0.0, time.time() - self.last_refreshed_ts)
        ratio = 0.5 ** (age / self.half_life_seconds)
        decayed = self.decay_floor + (self.confidence - self.decay_floor) * ratio
        return max(self.decay_floor, min(1.0, decayed))


class UncertaintyTracker:
    def __init__(self):
        self._beliefs: Dict[str, Belief] = {}

    def assert_(self, key: str, statement: str, confidence: float,
                source: str, half_life_seconds: float = 3600.0,
                tags: Optional[List[str]] = None) -> Belief:
        now_ts = time.time()
        if key in self._beliefs:
            b = self._beliefs[key]
            b.statement = statement
            b.confidence = confidence
            b.source = source
            b.last_refreshed_ts = now_ts
            b.half_life_seconds = half_life_seconds
            if tags is not None:
                b.tags = tags
        else:
            b = Belief(
                key=key, statement=statement, confidence=confidence,
                source=source, inserted_ts=now_ts, last_refreshed_ts=now_ts,
                half_life_seconds=half_life_seconds, tags=tags or [],
            )
            self._beliefs[key] = b
        append_log("uncertainty.jsonl",
                   {"event": "assert", "key": key,
                    "confidence": confidence, "source": source})
        return b

    def get(self, key: str) -> Optional[Belief]:
        return self._beliefs.get(key)

    def confidence_for(self, key: str) -> float:
        b = self._beliefs.get(key)
        return b.current_confidence() if b else 0.0

    def low_confidence_keys(self, threshold: float = 0.4) -> List[str]:
        return [k for k, b in self._beliefs.items()
                if b.current_confidence() < threshold]

    def snapshot(self) -> dict:
        rows = []
        for b in self._beliefs.values():
            d = asdict(b)
            d["effective_confidence"] = round(b.current_confidence(), 3)
            rows.append(d)
        rows.sort(key=lambda r: r["effective_confidence"])
        return {
            "ok": True, "kind": "cognitive_uncertainty_state",
            "generated_ts": now(),
            "belief_count": len(self._beliefs),
            "low_confidence_count": len(self.low_confidence_keys()),
            "beliefs": rows[:60],
        }

    def persist(self) -> None:
        write_registry("cognitive_uncertainty_state.json", self.snapshot())


_UNCERTAINTY: Optional[UncertaintyTracker] = None


def uncertainty() -> UncertaintyTracker:
    global _UNCERTAINTY
    if _UNCERTAINTY is None:
        _UNCERTAINTY = UncertaintyTracker()
    return _UNCERTAINTY
