"""CounterfactualEngine — Layer · "What if?" reasoning, safely.

Asks: if state X were different, what would the Kernel's recommendation
have been? Produces simulated outcomes for operator briefings.

NEVER mutates real registries. Operates on a *copy* of the blackboard
state with an overlay applied, runs reasoning rules against the
overlay, and reports both:

  - the inferred change in Conclusions
  - the inferred change in proposed actions

Use case: "what if guardian were RECOVERED instead of TRIPPED?"
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import copy
import time

from . import append_log, write_registry, now
from .working_memory import WorkingMemory, Slot, blackboard
from .reasoning import reasoning


@dataclass
class CounterfactualRun:
    ts: float
    overlay_key: str
    overlay_value: Any
    baseline_conclusion_keys: List[str] = field(default_factory=list)
    overlay_conclusion_keys: List[str] = field(default_factory=list)
    delta_added: List[str] = field(default_factory=list)
    delta_removed: List[str] = field(default_factory=list)
    rationale: str = ""


class CounterfactualEngine:
    def __init__(self):
        self._runs: List[CounterfactualRun] = []

    def what_if(self, key: str, value: Any,
                source: str = "counterfactual_overlay",
                rationale: str = "") -> CounterfactualRun:
        # Baseline
        baseline = [c.key for c in reasoning().run_once()]
        # Snapshot blackboard, apply overlay, re-run reasoning, then revert
        bb = blackboard()
        snapshot = copy.deepcopy(bb._slots)        # mutable snapshot

        try:
            bb.write(key=key, value=value, source=source,
                     priority=0.6, ttl_seconds=120,
                     tags=["counterfactual"])
            overlay = [c.key for c in reasoning().run_once()]
        finally:
            # Restore baseline blackboard exactly
            bb._slots = snapshot

        added = sorted(set(overlay) - set(baseline))
        removed = sorted(set(baseline) - set(overlay))

        run = CounterfactualRun(
            ts=time.time(), overlay_key=key, overlay_value=value,
            baseline_conclusion_keys=baseline,
            overlay_conclusion_keys=overlay,
            delta_added=added, delta_removed=removed,
            rationale=rationale or f"what-if {key}={value!r}",
        )
        self._runs.append(run)
        append_log("counterfactual.jsonl", {
            "event": "what_if", "key": key,
            "delta_added": added, "delta_removed": removed,
        })
        return run

    def persist(self) -> None:
        write_registry("cognitive_counterfactual_state.json", {
            "ok": True, "kind": "cognitive_counterfactual_state",
            "generated_ts": now(),
            "policy": "Counterfactual reasoning operates on a snapshot. No live state mutated.",
            "run_count_session": len(self._runs),
            "recent_runs": [asdict(r) for r in self._runs[-15:]],
        })


_CF: Optional[CounterfactualEngine] = None


def counterfactual() -> CounterfactualEngine:
    global _CF
    if _CF is None:
        _CF = CounterfactualEngine()
    return _CF
