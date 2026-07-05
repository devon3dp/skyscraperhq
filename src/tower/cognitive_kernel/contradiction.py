"""ContradictionDetector — Layer · Cross-source consistency check.

The Kernel pulls from many registries that may disagree. This module
catches:
  - Two registries asserting incompatible status
  - A reasoning conclusion contradicting a registry fact
  - A semantic lesson contradicted by recent episodes

Detected contradictions become curiosity items (to be resolved) and
lower the confidence of all conflicting beliefs.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
import time

from . import append_log, write_registry, now
from .uncertainty import uncertainty
from .curiosity import curiosity


@dataclass
class Contradiction:
    detected_ts: float
    a_key: str
    a_statement: str
    a_source: str
    b_key: str
    b_statement: str
    b_source: str
    severity: float
    note: str = ""


# Pre-declared incompatibility pairs. Keys reference Beliefs in the
# UncertaintyTracker. Each tuple is (statement_signature_a, statement_signature_b)
INCOMPATIBLE_PAIRS: List[Tuple[str, str]] = [
    ("guardian_tripped",        "trading_active_unconstrained"),
    ("guardian_recovered",      "all_floors_halted"),
    ("real_money_enabled",      "execution_gates_locked"),
    ("autonomous_dispatch_on",  "kernel_advisory_only"),
]


class ContradictionDetector:
    def __init__(self):
        self._found: List[Contradiction] = []

    def scan(self) -> List[Contradiction]:
        unc = uncertainty()
        cur = curiosity()
        found_now: List[Contradiction] = []
        beliefs = list(unc._beliefs.values())
        # Pairwise check — small N so quadratic is fine
        for i, a in enumerate(beliefs):
            a_sig = self._signature(a.statement)
            for b in beliefs[i + 1:]:
                b_sig = self._signature(b.statement)
                if self._is_incompatible(a_sig, b_sig):
                    c = Contradiction(
                        detected_ts=time.time(),
                        a_key=a.key, a_statement=a.statement, a_source=a.source,
                        b_key=b.key, b_statement=b.statement, b_source=b.source,
                        severity=0.7,
                        note=f"signatures: {a_sig} ⟂ {b_sig}",
                    )
                    found_now.append(c)
                    # Drop confidence of both
                    a.confidence = max(a.decay_floor, a.confidence * 0.6)
                    b.confidence = max(b.decay_floor, b.confidence * 0.6)
                    # File a curiosity item to resolve
                    cur.add(
                        question=f"resolve contradiction: {a.key} vs {b.key}",
                        source="contradiction_detector",
                        priority=0.8,
                    )
                    append_log("contradiction.jsonl",
                               {"event": "found",
                                "a_key": a.key, "b_key": b.key,
                                "severity": c.severity})
        self._found = found_now
        return found_now

    @staticmethod
    def _signature(statement: str) -> str:
        s = statement.lower()
        if "guardian" in s and "tripped" in s: return "guardian_tripped"
        if "guardian" in s and "recovered" in s: return "guardian_recovered"
        if "trading" in s and "active" in s and "unconstrained" in s: return "trading_active_unconstrained"
        if "all floors" in s and "halt" in s: return "all_floors_halted"
        if "real money" in s and ("enabled" in s or "live" in s): return "real_money_enabled"
        if "execution" in s and ("locked" in s or "gates" in s): return "execution_gates_locked"
        if "autonomous" in s and "dispatch" in s and "enabled" in s: return "autonomous_dispatch_on"
        if "advisory" in s and "only" in s: return "kernel_advisory_only"
        return "neutral"

    @staticmethod
    def _is_incompatible(a: str, b: str) -> bool:
        for x, y in INCOMPATIBLE_PAIRS:
            if {a, b} == {x, y}:
                return True
        return False

    def persist(self) -> None:
        write_registry("cognitive_contradictions.json", {
            "ok": True, "kind": "cognitive_contradictions",
            "generated_ts": now(),
            "contradiction_count": len(self._found),
            "contradictions": [asdict(c) for c in self._found],
            "incompatible_pair_definitions": INCOMPATIBLE_PAIRS,
        })


_CONTRADICTION: Optional[ContradictionDetector] = None


def contradiction_detector() -> ContradictionDetector:
    global _CONTRADICTION
    if _CONTRADICTION is None:
        _CONTRADICTION = ContradictionDetector()
    return _CONTRADICTION
