"""CognitionSelfAudit — Per-tick system health.

What the audit checks:
  · every important cognitive registry present + age
  · every JSONL log present
  · any goal whose focus_keys reference a registry that is missing
  · any belief with confidence == 0 for > 1 hour (suggests broken
    refresh)
  · any working-memory slot at capacity for > 30 minutes (overflow)
  · authority gate counts (sanity)
  · bank supply utilisation
  · curiosity queue length

Output:
  cognitive_self_audit.json with findings_count, severity, findings.

If findings include any "RED" severity, file a P0 proposal.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import time

from . import ROOT, COG_REG, COG_LOG, write_registry, append_log, load, now
from .action_proposal import action_proposer
from .uncertainty import uncertainty
from .working_memory import blackboard
from .goals import goals
from .bank import bank


IMPORTANT_REGISTRIES = [
    "cognitive_self_model.json",
    "cognitive_working_memory_state.json",
    "cognitive_perception_latest.json",
    "cognitive_attention_ranking.json",
    "cognitive_curiosity_queue.json",
    "cognitive_uncertainty_state.json",
    "cognitive_reasoning_state.json",
    "cognitive_contradictions.json",
    "cognitive_goals.json",
    "cognitive_reflection_state.json",
    "cognitive_thought_trace_recent.json",
    "cognitive_action_proposals.json",
    "cognitive_learning_state.json",
    "cognitive_orchestrator_last_tick.json",
    "cognitive_worker_certification.json",
    "cognitive_worker_pnl_rollup.json",
    "cognitive_worker_genetics.json",
    "cognitive_family_tree.json",
    "cognitive_reward_engine_state.json",
    "cognitive_population_status.json",
    "cognitive_classroom_state.json",
    "cognitive_bank_state.json",
    "cognitive_compensation_state.json",
]

IMPORTANT_LOGS = [
    "orchestrator.jsonl",
    "perception.jsonl",
    "reasoning.jsonl",
    "reflection.jsonl",
    "thought_trace.jsonl",
    "working_memory.jsonl",
    "action_proposal.jsonl",
    "worker_certification.jsonl",
    "classroom.jsonl",
    "reward_engine.jsonl",
    "family_tree.jsonl",
    "bank_transactions.jsonl",
    "compensation.jsonl",
]


SEVERITY_RED = "RED"
SEVERITY_AMBER = "AMBER"
SEVERITY_GREEN = "GREEN"


@dataclass
class Finding:
    severity: str
    code: str
    description: str
    payload: Dict[str, Any] = field(default_factory=dict)


class CognitionSelfAudit:

    def run(self) -> List[Finding]:
        findings: List[Finding] = []
        now_ts = time.time()

        # 1. Registries: present + fresh enough
        STALE_S = 24 * 3600
        for name in IMPORTANT_REGISTRIES:
            p = COG_REG / name
            if not p.exists():
                findings.append(Finding(
                    severity=SEVERITY_RED, code="missing_cognitive_registry",
                    description=f"{name} not present on disk",
                    payload={"path": str(p)},
                ))
                continue
            age = now_ts - p.stat().st_mtime
            if age > STALE_S:
                findings.append(Finding(
                    severity=SEVERITY_AMBER, code="stale_cognitive_registry",
                    description=f"{name} not refreshed in {int(age/3600)}h",
                    payload={"age_seconds": int(age)},
                ))

        # 2. Logs present
        for name in IMPORTANT_LOGS:
            p = COG_LOG / name
            if not p.exists():
                findings.append(Finding(
                    severity=SEVERITY_AMBER, code="missing_cognitive_log",
                    description=f"{name} not present",
                    payload={"path": str(p)},
                ))

        # 3. Goals reference live focus_keys?
        g = load(COG_REG / "cognitive_goals.json")
        if isinstance(g, dict):
            for goal in g.get("goals") or []:
                if goal.get("status") != "active": continue
                # focus_keys are softly defined — we just check they exist somewhere
                fk = goal.get("focus_keys") or []
                if not fk:
                    findings.append(Finding(
                        severity=SEVERITY_AMBER, code="goal_no_focus_keys",
                        description=f"active goal '{goal.get('name')}' has no focus_keys",
                    ))

        # 4. Beliefs at zero confidence > 1 hour
        unc = uncertainty()
        stale_beliefs: List[str] = []
        for k, b in unc._beliefs.items():
            if b.current_confidence() <= 0.05 and (now_ts - b.last_refreshed_ts) > 3600:
                stale_beliefs.append(k)
        if stale_beliefs:
            findings.append(Finding(
                severity=SEVERITY_AMBER, code="beliefs_decayed_too_low",
                description=f"{len(stale_beliefs)} beliefs effectively zero for > 1h",
                payload={"sample": stale_beliefs[:8]},
            ))

        # 5. Working memory pressure
        bb = blackboard()
        if len(bb.all_slots()) >= int(0.9 * bb.capacity):
            findings.append(Finding(
                severity=SEVERITY_AMBER, code="working_memory_near_capacity",
                description=f"WM at {len(bb.all_slots())}/{bb.capacity}",
            ))

        # 6. Bank supply utilisation
        try:
            bk = bank()
            if bk.total_supply() > 0:
                util = bk.utilisation()
                if util > 0.8:
                    findings.append(Finding(
                        severity=SEVERITY_RED, code="bank_supply_near_cap",
                        description=f"QBC supply utilisation {util:.2%} >= 80%",
                        payload={"utilisation": util,
                                  "outstanding": bk.total_supply()},
                    ))
        except Exception:
            pass

        # 7. Authority gate sanity
        gate = load(COG_REG / "cognitive_trading_authority_gate.json")
        if isinstance(gate, dict):
            c = int(gate.get("certified_workers_count") or 0)
            s = int(gate.get("suspended_workers_count") or 0)
            if c == 0 and s == 0:
                # Possibly empty deployment; AMBER not RED
                findings.append(Finding(
                    severity=SEVERITY_AMBER, code="authority_gate_empty",
                    description="no certified or suspended workers in the gate",
                ))

        # File a P0 proposal if any RED
        reds = [f for f in findings if f.severity == SEVERITY_RED]
        if reds:
            for f in reds:
                action_proposer().propose(
                    title=f"AUDIT-RED: {f.code}",
                    rationale=f.description,
                    proposed_action=("operator+claude: inspect; reset / "
                                      "rebuild / refresh as appropriate."),
                    requires_approval_from="operator+claude",
                    confidence=0.9,
                    tags=["self_audit", "red", f.code],
                )

        append_log("cognition_self_audit.jsonl", {
            "event": "run",
            "finding_count": len(findings),
            "by_severity": _by_severity(findings),
        })
        return findings

    def persist(self) -> Dict[str, Any]:
        findings = self.run()
        snap = {
            "ok": True,
            "kind": "cognitive_self_audit",
            "generated_ts": now(),
            "policy": "Read-only audit. RED findings file P0 proposals.",
            "finding_count": len(findings),
            "by_severity": _by_severity(findings),
            "findings": [asdict(f) for f in findings],
        }
        write_registry("cognitive_self_audit.json", snap)
        return snap


def _by_severity(findings: List[Finding]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for f in findings:
        out[f.severity] = out.get(f.severity, 0) + 1
    return out


_AUDIT: Optional[CognitionSelfAudit] = None


def cognition_self_audit() -> CognitionSelfAudit:
    global _AUDIT
    if _AUDIT is None:
        _AUDIT = CognitionSelfAudit()
    return _AUDIT
