"""WorkerReassignment — Layer · Propose where idle workers should move.

Reads:
  · cognitive_worker_exchange.json  (per-floor digest)
  · active goals → focus_keys       (where we want labour applied)

Emits proposals like:
  "Move N catalog_curator workers from floor_X to floor_46_commerce"

Never auto-dispatches. Operator approves; the Orchestrator (or human)
dispatches. autonomous_dispatch_enabled remains False.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import time

from . import write_registry, append_log, now, load, COG_REG
from .action_proposal import action_proposer
from .goals import goals
from .worker_exchange import worker_exchange


# Where idle labour should drain TO, by descending priority.
# Each target carries the workforce roles it benefits from + a cap.
@dataclass
class ReassignmentTarget:
    floor: str
    priority: float
    desired_roles: List[str]
    max_workers: int
    rationale: str


DEFAULT_TARGETS: List[ReassignmentTarget] = [
    ReassignmentTarget(
        floor="floor_25_worker_recruitment",
        priority=0.9,
        desired_roles=["recruiter", "trainer", "evaluator"],
        max_workers=60,
        rationale=("Drain idle workers into recruitment/training before "
                    "spinning up new floors; deepens the bench."),
    ),
    ReassignmentTarget(
        floor="floor_46_commerce",
        priority=0.85,
        desired_roles=["catalog_curator", "product_photographer",
                       "copywriter", "pricing_analyst",
                       "listing_draft_reviewer"],
        max_workers=40,
        rationale=("Stand up the Commerce Wing preview catalog. Operator "
                    "approves listings BEFORE the publishing gate is flipped."),
    ),
    ReassignmentTarget(
        floor="floor_47_profit_analytics",
        priority=0.7,
        desired_roles=["analyst", "report_writer"],
        max_workers=15,
        rationale=("Profit analytics needs analysts to maintain the "
                    "snapshot and write operator briefings."),
    ),
    ReassignmentTarget(
        floor="floor_41_oanda_practice",
        priority=0.6,
        desired_roles=["strategy_evaluator", "backtester"],
        max_workers=12,
        rationale=("Strategy evaluation on PRACTICE floor only. No live "
                    "execution. Output feeds the Learning layer."),
    ),
    ReassignmentTarget(
        floor="floor_51_research",
        priority=0.4,
        desired_roles=["researcher"],
        max_workers=10,
        rationale=("Research floor pulls in curiosity items the Kernel filed; "
                    "scales with idle bandwidth."),
    ),
]


@dataclass
class ReassignmentProposal:
    from_floor: str
    to_floor: str
    worker_count: int
    desired_role: str
    rationale: str
    confidence: float


class WorkerReassignment:

    def __init__(self):
        self._last_proposals: List[ReassignmentProposal] = []

    def _idle_source_floors(self) -> List[Dict[str, Any]]:
        digest = load(COG_REG / "cognitive_worker_exchange.json")
        rows: List[Dict[str, Any]] = []
        if not isinstance(digest, dict):
            return rows
        for fname, d in (digest.get("digest") or {}).items():
            if not isinstance(d, dict):
                continue
            idle = int(d.get("idle_count") or 0)
            wc = int(d.get("worker_count") or 0)
            if idle <= 0:
                continue
            # Don't drain from any of our preferred TARGET floors — only sources
            if fname in {t.floor for t in DEFAULT_TARGETS}:
                continue
            rows.append({
                "floor": fname, "worker_count": wc,
                "idle_count": idle, "idle_ratio": (idle / wc) if wc else 0,
            })
        rows.sort(key=lambda r: -r["idle_ratio"])
        return rows

    def compute(self) -> List[ReassignmentProposal]:
        sources = self._idle_source_floors()
        targets = sorted(DEFAULT_TARGETS, key=lambda t: -t.priority)
        # Allocate greedily: highest-priority target pulls from the most-idle
        # source first, capped by max_workers and source idle_count.
        remaining_capacity = {t.floor: t.max_workers for t in targets}
        proposals: List[ReassignmentProposal] = []
        for t in targets:
            cap = remaining_capacity[t.floor]
            if cap <= 0:
                continue
            for s in sources:
                if cap <= 0:
                    break
                idle = s["idle_count"]
                if idle <= 0:
                    continue
                move = min(idle, cap)
                # Pick a role round-robin across desired_roles
                role = (t.desired_roles[(len(proposals)) % len(t.desired_roles)]
                        if t.desired_roles else "worker")
                proposals.append(ReassignmentProposal(
                    from_floor=s["floor"],
                    to_floor=t.floor,
                    worker_count=move,
                    desired_role=role,
                    rationale=t.rationale,
                    confidence=t.priority,
                ))
                cap -= move
                s["idle_count"] -= move
            remaining_capacity[t.floor] = cap
        self._last_proposals = proposals
        append_log("worker_reassignment.jsonl", {
            "event": "compute", "proposal_count": len(proposals),
        })
        return proposals

    def file_proposals(self) -> List[str]:
        props = self.compute()
        ap = action_proposer()
        filed: List[str] = []
        for r in props:
            p = ap.propose(
                title=(f"Move {r.worker_count} workers "
                       f"{r.from_floor} → {r.to_floor} as {r.desired_role}"),
                rationale=r.rationale,
                proposed_action=("operator: approve the move; the "
                                  "orchestrator does NOT auto-dispatch "
                                  "(autonomous_dispatch_enabled=False)."),
                requires_approval_from="operator",
                confidence=r.confidence,
                tags=["worker_reassignment", r.to_floor],
            )
            filed.append(p.id)
        return filed

    def persist(self) -> Dict[str, Any]:
        snap = {
            "ok": True,
            "kind": "cognitive_worker_reassignment",
            "generated_ts": now(),
            "policy": ("Advisory. No auto-dispatch. "
                        "autonomous_dispatch_enabled=False."),
            "target_floor_count": len(DEFAULT_TARGETS),
            "targets": [asdict(t) for t in DEFAULT_TARGETS],
            "proposal_count": len(self._last_proposals),
            "proposals": [asdict(r) for r in self._last_proposals],
        }
        write_registry("cognitive_worker_reassignment.json", snap)
        return snap


_WR: Optional[WorkerReassignment] = None


def worker_reassignment() -> WorkerReassignment:
    global _WR
    if _WR is None:
        _WR = WorkerReassignment()
    return _WR
