"""OpenClawCognitiveSupervisor — Layer · Read-only supervisor over the
OpenClaw routing surface.

OpenClaw is the routing & ticketing layer above floors. From the
Kernel's perspective it is:

  - A *source* of perception events (tickets, route choices)
  - A *target* of proposals (file tickets, never execute)
  - Strictly READ_ONLY and ADVISORY here; real execution stays gated.

This module wraps the OpenClaw registries with a cognitive lens:
  - watches qsb_openclaw_route.json, qsb_openclaw_tickets.json
  - infers when OpenClaw is congested / stalled / contradictory
  - files proposals when a sensible re-route would help
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import time

from . import append_log, write_registry, now, load, REG
from .uncertainty import uncertainty
from .action_proposal import action_proposer
from .working_memory import blackboard


@dataclass
class OpenClawObservation:
    ts: float
    route_present: bool
    tickets_present: bool
    open_ticket_count: int
    congestion_score: float       # 0..1
    notes: List[str] = field(default_factory=list)


class OpenClawCognitiveSupervisor:
    HIGH_CONGESTION = 0.7

    def __init__(self):
        self._observations: List[OpenClawObservation] = []

    def observe(self) -> OpenClawObservation:
        route = load(REG / "qsb_openclaw_route.json")
        tickets = load(REG / "qsb_openclaw_tickets.json")
        open_count = 0
        notes: List[str] = []

        if isinstance(tickets, dict):
            t_list = tickets.get("tickets", [])
            if isinstance(t_list, list):
                open_count = sum(
                    1 for t in t_list
                    if isinstance(t, dict)
                    and str(t.get("status", "open")).lower() in ("open", "pending", "queued")
                )
        elif isinstance(tickets, list):
            open_count = sum(
                1 for t in tickets
                if isinstance(t, dict)
                and str(t.get("status", "open")).lower() in ("open", "pending", "queued")
            )

        # Heuristic congestion: 0 tickets = idle, 1-3 = green, 4-7 = amber, 8+ = red
        if open_count == 0:
            congestion = 0.0; notes.append("openclaw_idle")
        elif open_count <= 3:
            congestion = 0.3
        elif open_count <= 7:
            congestion = 0.6; notes.append("openclaw_warming")
        else:
            congestion = 0.9; notes.append("openclaw_congested")

        obs = OpenClawObservation(
            ts=time.time(),
            route_present=bool(route),
            tickets_present=bool(tickets),
            open_ticket_count=open_count,
            congestion_score=congestion,
            notes=notes,
        )
        self._observations.append(obs)

        # Mirror into working memory
        blackboard().write(
            key="openclaw_state",
            value={"open_ticket_count": open_count,
                   "congestion_score": congestion,
                   "notes": notes},
            source="qsb_openclaw_tickets.json",
            priority=0.55 + 0.4 * congestion,
            ttl_seconds=900,
            tags=["openclaw", "routing"],
        )
        # Confidence belief
        uncertainty().assert_(
            key="openclaw_congestion_level",
            statement=f"OpenClaw congestion ~{congestion:.2f}, {open_count} open tickets.",
            confidence=0.8 if obs.tickets_present else 0.3,
            source="openclaw_supervisor",
            half_life_seconds=900.0,
            tags=["openclaw"],
        )

        # If congested, file an advisory proposal — never auto-route.
        if congestion >= self.HIGH_CONGESTION:
            action_proposer().propose(
                title="OpenClaw congestion — operator review of routing",
                rationale=(f"open_ticket_count={open_count}, "
                           f"congestion_score={congestion:.2f}. "
                           "Suggest operator inspect routing fairness and "
                           "ticket aging before approving new external work."),
                proposed_action="operator inspect qsb_openclaw_tickets.json; consider deferring lowest-priority queued tickets",
                requires_approval_from="operator",
                confidence=0.7,
                tags=["openclaw", "advisory", "routing"],
            )
            append_log("openclaw_supervisor.jsonl",
                       {"event": "congestion_proposal_filed",
                        "open_ticket_count": open_count,
                        "congestion_score": congestion})

        return obs

    def persist(self) -> None:
        last = self._observations[-1] if self._observations else None
        write_registry("cognitive_openclaw_supervisor.json", {
            "ok": True, "kind": "cognitive_openclaw_supervisor",
            "generated_ts": now(),
            "policy": "READ_ONLY supervisory layer. No execution authority.",
            "last_observation": asdict(last) if last else None,
            "observation_count_session": len(self._observations),
        })


_OPENCLAW: Optional[OpenClawCognitiveSupervisor] = None


def openclaw_supervisor() -> OpenClawCognitiveSupervisor:
    global _OPENCLAW
    if _OPENCLAW is None:
        _OPENCLAW = OpenClawCognitiveSupervisor()
    return _OPENCLAW
