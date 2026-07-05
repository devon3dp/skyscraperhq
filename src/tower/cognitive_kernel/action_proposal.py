"""ActionProposal — Layer · Proposals only. Never execution.

The Kernel may THINK, SPEAK, PROPOSE. Kernel may not DO.

Every payload is stamped with the full SAFETY envelope. Proposals are
filed as tickets that the operator may approve and that OpenClaw may
*surface* but not auto-route to execution.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import time

from . import append_log, write_registry, now, SAFETY


@dataclass
class Proposal:
    id: str
    title: str
    rationale: str
    proposed_action: str         # plain English description
    requires_approval_from: str  # "operator" | "operator+claude" | "operator+claude+guardian"
    target_floor: Optional[str] = None
    target_worker: Optional[str] = None
    confidence: float = 0.5
    status: str = "open"         # open | acknowledged | approved | declined | superseded
    tags: List[str] = field(default_factory=list)
    created_ts: float = 0.0
    # Safety envelope — copied verbatim so each proposal carries it
    safety: Dict[str, bool] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


class ActionProposer:
    def __init__(self):
        self._proposals: Dict[str, Proposal] = {}
        self._counter = 0

    def propose(self, title: str, rationale: str,
                proposed_action: str,
                requires_approval_from: str = "operator",
                target_floor: Optional[str] = None,
                target_worker: Optional[str] = None,
                confidence: float = 0.5,
                tags: Optional[List[str]] = None) -> Proposal:
        self._counter += 1
        pid = f"prop_{int(time.time())}_{self._counter}"
        p = Proposal(
            id=pid, title=title, rationale=rationale,
            proposed_action=proposed_action,
            requires_approval_from=requires_approval_from,
            target_floor=target_floor, target_worker=target_worker,
            confidence=confidence, tags=tags or [],
            created_ts=time.time(),
            safety=dict(SAFETY),    # immutable copy
        )
        self._proposals[pid] = p
        append_log("action_proposal.jsonl", {
            "event": "propose", "id": pid, "title": title,
            "confidence": confidence, "approval_required": requires_approval_from,
        })
        return p

    def mark(self, pid: str, status: str, note: str = "") -> bool:
        if pid not in self._proposals:
            return False
        self._proposals[pid].status = status
        if note:
            self._proposals[pid].notes.append(note)
        append_log("action_proposal.jsonl",
                   {"event": "mark", "id": pid, "status": status})
        return True

    def open_proposals(self) -> List[Proposal]:
        return sorted([p for p in self._proposals.values() if p.status == "open"],
                      key=lambda p: -p.confidence)

    def persist(self) -> None:
        opens = self.open_proposals()
        write_registry("cognitive_action_proposals.json", {
            "ok": True, "kind": "cognitive_action_proposals",
            "generated_ts": now(),
            "total_proposals_session": len(self._proposals),
            "open_count": len(opens),
            "open_proposals": [asdict(p) for p in opens[:40]],
            "safety_envelope_stamped_on_every_proposal": True,
            "execution_allowed": False,
            "policy": "Kernel may THINK, SPEAK, PROPOSE. Kernel may not DO.",
        })


    def load_from_snapshot(self) -> int:
        """Rehydrate _proposals from cognitive_action_proposals.json.

        We keep ALL statuses on rehydrate (not only 'open') so the
        history is visible to chat queries and learning can attribute
        outcomes against historical proposals.
        """
        from . import COG_REG, load
        d = load(COG_REG / "cognitive_action_proposals.json")
        if not isinstance(d, dict):
            return 0
        count = 0
        for r in d.get("open_proposals") or []:
            pid = r.get("id")
            if not pid or pid in self._proposals:
                continue
            p = Proposal(
                id=pid,
                title=r.get("title", ""),
                rationale=r.get("rationale", ""),
                proposed_action=r.get("proposed_action", ""),
                requires_approval_from=r.get("requires_approval_from", "operator"),
                target_floor=r.get("target_floor"),
                target_worker=r.get("target_worker"),
                confidence=float(r.get("confidence") or 0),
                status=r.get("status", "open"),
                tags=list(r.get("tags") or []),
                created_ts=float(r.get("created_ts") or 0),
                safety=dict(r.get("safety") or {}),
                notes=list(r.get("notes") or []),
            )
            self._proposals[pid] = p
            # Track counter to avoid id collisions on next propose()
            try:
                tail = int(pid.rsplit("_", 1)[-1])
                self._counter = max(self._counter, tail)
            except Exception:
                pass
            count += 1
        return count


_PROPOSER: Optional[ActionProposer] = None


def action_proposer() -> ActionProposer:
    global _PROPOSER
    if _PROPOSER is None:
        _PROPOSER = ActionProposer()
    return _PROPOSER
