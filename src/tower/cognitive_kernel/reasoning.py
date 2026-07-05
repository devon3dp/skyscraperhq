"""Reasoning — Layer 5 · Lightweight inference.

NOT an LLM. This is rule-based + composable predicates over the
blackboard. It exists so the Kernel can produce *derived* statements
beyond what's literally in a registry — e.g.,

  guardian.status == "TRIPPED" AND trading.floor == 41
    → derived: "trading_floor_41_is_halted_now"

Reasoning is advisory: it writes Beliefs into the UncertaintyTracker,
proposes goals/actions, never executes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any
import time

from . import append_log, write_registry, now
from .working_memory import WorkingMemory, blackboard
from .uncertainty import UncertaintyTracker, uncertainty


@dataclass
class Rule:
    name: str
    predicate: Callable[[WorkingMemory], bool]
    conclude: Callable[[WorkingMemory], dict]   # returns {key, statement, confidence, tags}
    rationale: str = ""


@dataclass
class Conclusion:
    rule: str
    key: str
    statement: str
    confidence: float
    derived_ts: float
    tags: List[str] = field(default_factory=list)


class Reasoning:
    def __init__(self):
        self._rules: List[Rule] = []
        self._last_conclusions: List[Conclusion] = []
        self._install_baseline_rules()

    # ── rule wiring ────────────────────────────────────────────────
    def add_rule(self, rule: Rule) -> None:
        self._rules.append(rule)

    def _install_baseline_rules(self) -> None:
        # Rule: guardian tripped → all trading floors halted
        def _guardian_tripped(bb: WorkingMemory) -> bool:
            s = bb.read("guardian_state")
            return bool(s and isinstance(s.value, dict)
                       and str(s.value.get("status", "")).upper() == "TRIPPED")

        def _guardian_halt_conclusion(bb: WorkingMemory) -> dict:
            return {
                "key": "trading_floors_halted_inference",
                "statement": "Guardian is TRIPPED → all trading floors are halted.",
                "confidence": 0.95,
                "tags": ["safety", "guardian", "trading"],
            }

        self.add_rule(Rule(
            name="guardian_tripped_implies_floors_halted",
            predicate=_guardian_tripped,
            conclude=_guardian_halt_conclusion,
            rationale="Safety invariant from guardian state machine.",
        ))

        # Rule: missing OANDA pnl registry → trading not actively reporting
        def _oanda_pnl_missing(bb: WorkingMemory) -> bool:
            s = bb.read("oanda_pnl_state")
            return s is None or s.value in (None, {}, [])

        def _oanda_inactive_conclusion(bb: WorkingMemory) -> dict:
            return {
                "key": "oanda_floor_inactive_inference",
                "statement": "OANDA pnl registry absent or empty → floor 41 not currently reporting trades.",
                "confidence": 0.7,
                "tags": ["trading", "oanda", "floor41"],
            }

        self.add_rule(Rule(
            name="oanda_pnl_missing_implies_floor_inactive",
            predicate=_oanda_pnl_missing,
            conclude=_oanda_inactive_conclusion,
            rationale="Reporting gap heuristic.",
        ))

        # Rule: working memory near capacity → attention is overloaded
        def _wm_full(bb: WorkingMemory) -> bool:
            return len(bb.all_slots()) >= int(0.9 * bb.capacity)

        def _wm_full_conclusion(bb: WorkingMemory) -> dict:
            return {
                "key": "working_memory_pressure",
                "statement": f"WM at {len(bb.all_slots())}/{bb.capacity} slots — attention pressure high; reduce input or lift threshold.",
                "confidence": 0.85,
                "tags": ["meta", "working_memory"],
            }

        self.add_rule(Rule(
            name="working_memory_pressure",
            predicate=_wm_full,
            conclude=_wm_full_conclusion,
            rationale="Self-monitoring.",
        ))

    # ── execution ──────────────────────────────────────────────────
    def run_once(self) -> List[Conclusion]:
        bb = blackboard()
        unc = uncertainty()
        out: List[Conclusion] = []
        for r in self._rules:
            try:
                if r.predicate(bb):
                    c = r.conclude(bb)
                    conc = Conclusion(
                        rule=r.name, key=c["key"],
                        statement=c["statement"],
                        confidence=c["confidence"],
                        derived_ts=time.time(),
                        tags=c.get("tags", []),
                    )
                    out.append(conc)
                    # Assert into uncertainty tracker so it decays naturally
                    unc.assert_(
                        key=conc.key, statement=conc.statement,
                        confidence=conc.confidence, source=f"reasoning:{r.name}",
                        half_life_seconds=1800.0, tags=conc.tags,
                    )
            except Exception as e:
                append_log("reasoning.jsonl",
                           {"event": "rule_error", "rule": r.name, "error": str(e)})
        self._last_conclusions = out
        append_log("reasoning.jsonl",
                   {"event": "run_once", "conclusion_count": len(out),
                    "rules_evaluated": len(self._rules)})
        return out

    def persist(self) -> None:
        write_registry("cognitive_reasoning_state.json", {
            "ok": True, "kind": "cognitive_reasoning_state",
            "generated_ts": now(),
            "rule_count": len(self._rules),
            "rule_names": [r.name for r in self._rules],
            "last_conclusion_count": len(self._last_conclusions),
            "last_conclusions": [
                {"rule": c.rule, "key": c.key, "statement": c.statement,
                 "confidence": c.confidence, "tags": c.tags}
                for c in self._last_conclusions
            ],
        })


_REASONING: Optional[Reasoning] = None


def reasoning() -> Reasoning:
    global _REASONING
    if _REASONING is None:
        _REASONING = Reasoning()
    return _REASONING
