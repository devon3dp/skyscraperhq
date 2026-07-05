"""SelfUpgradeProposer — Layer · The Kernel proposing its own evolution.

The Kernel knows its honest_self_assessment, its known_gaps, its
low-confidence beliefs, its open curiosity items, its contradictions,
and the recent reflection notes. This module reads all of that and
files concrete upgrade proposals through the action_proposer.

It NEVER edits code, NEVER edits registries outside the cognitive
namespace, NEVER calls external providers. It only THINKS and
PROPOSES; the operator (and Claude) carry out the actual upgrade
on approval.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import time

from . import append_log, write_registry, now, SAFETY
from .self_model import self_model
from .curiosity import curiosity
from .uncertainty import uncertainty
from .reflection import reflection
from .contradiction import contradiction_detector
from .action_proposal import action_proposer
from .long_term_memory import long_term_memory


class SelfUpgradeProposer:

    def propose_upgrades(self) -> List[dict]:
        sm = self_model()
        cur = curiosity()
        unc = uncertainty()
        cd = contradiction_detector()
        ap = action_proposer()
        ltm = long_term_memory()

        # Make sure we have fresh state to reason from
        sm.refresh_all()
        snap = sm.snapshot()

        proposals: List[dict] = []

        # 1. Gaps → handler proposals
        for gap in (snap.get("known_gaps") or [])[:6]:
            p = ap.propose(
                title=f"Add cognitive topic handler for intent: {gap}",
                rationale=(
                    f"SelfModel records intent '{gap}' as a known gap "
                    "(identity-gate safety-net fired). The kernel chat is "
                    "answering this with the identity paragraph instead of "
                    "a structured topic block. Operator should add a topic "
                    "block to kernel_dialogue_adapter._EQSB_TOPICS + a "
                    "matching handler in _format_eqsb_block."
                ),
                proposed_action=(
                    f"edit src/tower/kernel_dialogue_adapter.py: "
                    f"add ('{gap.lower()}_handler', (...triggers...)) to "
                    f"_EQSB_TOPICS and a handler block reading the relevant "
                    f"registry."
                ),
                requires_approval_from="operator+claude",
                confidence=0.7,
                tags=["self_upgrade", "topic_table_gap"],
            )
            proposals.append({"id": p.id, "title": p.title,
                              "confidence": p.confidence,
                              "approval": p.requires_approval_from,
                              "kind": "topic_table_gap"})

        # 2. Low-confidence beliefs → refresh proposals
        low = unc.low_confidence_keys(0.4)
        if low:
            p = ap.propose(
                title=f"Refresh stale beliefs ({len(low)} below confidence 0.4)",
                rationale=(
                    f"UncertaintyTracker shows {len(low)} beliefs with "
                    f"effective confidence < 0.4 (decayed past usable). "
                    f"Sample keys: {low[:5]}. Reasoning is making decisions "
                    "from stale evidence; refresh source registries or "
                    "demote the belief."
                ),
                proposed_action=(
                    "operator: re-run the originating layer's observe() / "
                    "tick() and confirm the registry it cites was just "
                    "written; optionally raise the half_life_seconds for "
                    "slower-changing beliefs."
                ),
                requires_approval_from="operator",
                confidence=0.65,
                tags=["self_upgrade", "stale_beliefs"],
            )
            proposals.append({"id": p.id, "title": p.title,
                              "confidence": p.confidence,
                              "approval": p.requires_approval_from,
                              "kind": "stale_beliefs"})

        # 3. Open curiosity items → field-investigation proposals
        opens = cur.open_items()
        if opens:
            highest = opens[0]
            p = ap.propose(
                title=f"Investigate top curiosity item: {highest.question[:80]}",
                rationale=(
                    f"CuriosityQueue surfaced {len(opens)} open items. "
                    f"Highest priority ({highest.priority:.2f}, seen "
                    f"{highest.seen_count}×, source={highest.source}): "
                    f"'{highest.question}'."
                ),
                proposed_action=(
                    "operator: triage the curiosity item; either close as "
                    "abandoned, add a handler, or convert into a project "
                    "task. Mark via curiosity().mark(question, status)."
                ),
                requires_approval_from="operator",
                confidence=0.6,
                tags=["self_upgrade", "curiosity"],
            )
            proposals.append({"id": p.id, "title": p.title,
                              "confidence": p.confidence,
                              "approval": p.requires_approval_from,
                              "kind": "curiosity"})

        # 4. Contradictions → resolution proposals
        contras = cd.scan()
        if contras:
            c0 = contras[0]
            p = ap.propose(
                title=f"Resolve cross-source contradiction: {c0.a_key} vs {c0.b_key}",
                rationale=(
                    f"ContradictionDetector flagged {len(contras)} "
                    "incompatible belief pair(s). First: "
                    f"'{c0.a_statement}' (source={c0.a_source}) vs "
                    f"'{c0.b_statement}' (source={c0.b_source}). "
                    "Both source registries cannot be simultaneously "
                    "correct."
                ),
                proposed_action=(
                    "operator: inspect both source registries, drop "
                    "confidence on the wrong one, and consider whether "
                    "the incompatible-pair definition itself is correct."
                ),
                requires_approval_from="operator+claude",
                confidence=0.75,
                tags=["self_upgrade", "contradiction"],
            )
            proposals.append({"id": p.id, "title": p.title,
                              "confidence": p.confidence,
                              "approval": p.requires_approval_from,
                              "kind": "contradiction"})

        # 5. Structural / capability upgrades — what the Kernel itself
        #    can identify as missing from its own architecture.
        structural = [
            {
                "title": "Add vector-backed retrieval to LongTermMemory",
                "rationale": (
                    "Current LongTermMemory uses JSONL append-logs and "
                    "grep-style retrieval. Recall by semantic similarity "
                    "would let Reflection cite past lessons that share "
                    "intent but not literal tokens."
                ),
                "action": (
                    "operator+claude: install sentence-transformers in a "
                    "side venv, embed semantic lessons + episodes on write, "
                    "expose long_term_memory().retrieve_similar(query, k). "
                    "Keep gates locked; no external API calls."
                ),
                "approval": "operator+claude",
                "confidence": 0.65,
                "kind": "structural_upgrade",
            },
            {
                "title": "Add Perception inotify backend (replace polling)",
                "rationale": (
                    "Perception currently polls mtimes each tick — robust "
                    "but lossy if multiple writes land between ticks. "
                    "inotify would let perception emit per-write events "
                    "and feed Attention with finer-grained novelty."
                ),
                "action": (
                    "operator+claude: add `pyinotify` or `watchdog` to the "
                    "main venv; wrap perception().tick() with a coalescing "
                    "queue that drains since-last-tick events."
                ),
                "approval": "operator+claude",
                "confidence": 0.6,
                "kind": "structural_upgrade",
            },
            {
                "title": "Add Reasoning rule editor surface in kernel chat",
                "rationale": (
                    "Reasoning rules are hard-coded in reasoning.py. "
                    "Operator should be able to add a rule (predicate + "
                    "conclusion) via chat for a one-off observation, then "
                    "decide later whether to promote it to code."
                ),
                "action": (
                    "operator+claude: add 'add reasoning rule …' chat "
                    "intent → writes a JSON rule to cognitive_rules.json "
                    "which Reasoning loads on each tick. Code-promoted "
                    "rules still take precedence."
                ),
                "approval": "operator+claude",
                "confidence": 0.55,
                "kind": "structural_upgrade",
            },
            {
                "title": "Add ThoughtTrace replay viewer to dashboard",
                "rationale": (
                    "ThoughtTrace persists per-tick narration but only the "
                    "kernel chat shows it. A dashboard tile that scrolls "
                    "the latest N thoughts would let the operator watch "
                    "cognition in real time."
                ),
                "action": (
                    "operator+claude: add /api/cognitive/thought_trace "
                    "dashboard endpoint reading cognitive_thought_trace_"
                    "recent.json + a small tile component."
                ),
                "approval": "operator+claude",
                "confidence": 0.7,
                "kind": "structural_upgrade",
            },
            {
                "title": "Add Goal-decomposition layer (parent → subgoals)",
                "rationale": (
                    "Goals are currently flat. A parent goal like "
                    "'reduce stale beliefs' should decompose into "
                    "concrete subgoals ('refresh guardian state', "
                    "'refresh OANDA pnl', …) so Attention can weight "
                    "individual focus_keys."
                ),
                "action": (
                    "operator+claude: extend goals.py with goals().add_"
                    "subgoal(parent_name, …) and persist a tree view "
                    "into cognitive_goals.json."
                ),
                "approval": "operator+claude",
                "confidence": 0.55,
                "kind": "structural_upgrade",
            },
            {
                "title": "Add Learning outcome-listener for OpenClaw tickets",
                "rationale": (
                    "Learning.report_outcome() is currently called "
                    "manually. When an OpenClaw ticket closes "
                    "(success/failure), the related action_proposal "
                    "beliefs should update automatically."
                ),
                "action": (
                    "operator+claude: extend openclaw_supervisor.observe() "
                    "to diff ticket statuses across ticks and call "
                    "learning().report_outcome() for newly-closed tickets."
                ),
                "approval": "operator+claude",
                "confidence": 0.6,
                "kind": "structural_upgrade",
            },
        ]
        for spec in structural:
            p = ap.propose(
                title=spec["title"],
                rationale=spec["rationale"],
                proposed_action=spec["action"],
                requires_approval_from=spec["approval"],
                confidence=spec["confidence"],
                tags=["self_upgrade", "structural", spec["kind"]],
            )
            proposals.append({"id": p.id, "title": p.title,
                              "confidence": p.confidence,
                              "approval": p.requires_approval_from,
                              "kind": spec["kind"]})

        # Record as an episode
        ltm.record_episode(
            kind="self_upgrade_round",
            summary=f"Filed {len(proposals)} upgrade proposals via SelfUpgradeProposer.",
            tags=["self_upgrade"],
            payload={"counts_by_kind": _count_by_kind(proposals)},
        )

        append_log("self_upgrade.jsonl",
                   {"event": "round", "proposal_count": len(proposals),
                    "counts_by_kind": _count_by_kind(proposals)})

        write_registry("cognitive_self_upgrade_round.json", {
            "ok": True, "kind": "cognitive_self_upgrade_round",
            "generated_ts": now(),
            "policy": "Advisory only. Kernel proposes; operator approves; Claude implements.",
            "safety_envelope": dict(SAFETY),
            "proposal_count": len(proposals),
            "proposals": proposals,
        })
        return proposals


def _count_by_kind(props: List[dict]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for p in props:
        k = p.get("kind", "?")
        out[k] = out.get(k, 0) + 1
    return out


_PROPOSER: Optional[SelfUpgradeProposer] = None


def self_upgrade_proposer() -> SelfUpgradeProposer:
    global _PROPOSER
    if _PROPOSER is None:
        _PROPOSER = SelfUpgradeProposer()
    return _PROPOSER
