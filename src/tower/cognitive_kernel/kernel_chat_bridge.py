"""KernelChatBridge — Layer · Exposes cognition to the kernel chat.

The existing kernel chat (kernel_chat_sidecar) currently calls into
kernel_dialogue_adapter.py for topic handling. This bridge gives those
handlers access to:

  - cognitive_self_model.json    (what the Kernel knows)
  - cognitive_working_memory_state.json (current focus)
  - cognitive_reflection_state.json (recent introspection)
  - cognitive_action_proposals.json (what the Kernel suggests next)
  - cognitive_thought_trace_recent.json (why it said what it said)

The bridge does NOT itself generate chat answers. It surfaces structured
context, and `kernel_dialogue_adapter` (or a thin new topic handler)
formats it for display.

Use:

  >>> from tower.cognitive_kernel.kernel_chat_bridge import chat_context
  >>> ctx = chat_context()
  >>> ctx["self_model"]["topic_count"]

The bridge also enforces the identity-gate contract before returning
the identity paragraph.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import json

from . import load, COG_REG, SAFETY, now
from .identity_gate import should_render_identity
from .working_memory import blackboard
from .self_model import self_model
from .curiosity import curiosity
from .uncertainty import uncertainty
from .action_proposal import action_proposer
from .thought_trace import thought_trace


def chat_context() -> Dict[str, Any]:
    """Return the structured cognition context for a chat turn."""
    bb = blackboard()
    sm = self_model().snapshot()
    return {
        "ok": True,
        "kind": "cognitive_chat_context",
        "generated_ts": now(),
        "safety_envelope": dict(SAFETY),
        "self_model": sm,
        "working_memory": bb.snapshot(),
        "open_curiosity_items_top": [
            {"question": i.question, "source": i.source,
             "priority": i.priority, "seen_count": i.seen_count}
            for i in curiosity().open_items()[:10]
        ],
        "low_confidence_belief_keys": uncertainty().low_confidence_keys(0.4),
        "open_proposals_top": [
            {"id": p.id, "title": p.title, "confidence": p.confidence,
             "requires_approval_from": p.requires_approval_from}
            for p in action_proposer().open_proposals()[:10]
        ],
        "recent_thoughts": [
            {"layer": t.layer, "text": t.text, "refs": t.refs}
            for t in thought_trace().recent(20)
        ],
        "reflection_latest": load(COG_REG / "cognitive_reflection_state.json"),
        "orchestrator_last_tick": load(COG_REG / "cognitive_orchestrator_last_tick.json"),
        "floor_to_mind_map": load(COG_REG / "cognitive_floor_to_mind_map.json"),
        "policy": "Kernel THINKS, SPEAKS, PROPOSES. Kernel does NOT execute.",
    }


def gate_identity(intent: str, topics_matched: List[str],
                   handler_blocks_produced: int,
                   user_explicitly_asked_identity: bool = False) -> bool:
    """Convenience wrapper exported for kernel_dialogue_adapter."""
    return should_render_identity(
        intent=intent,
        topics_matched=topics_matched,
        handler_blocks_produced=handler_blocks_produced,
        user_explicitly_asked_identity=user_explicitly_asked_identity,
    )


def cognition_summary_lines(max_lines: int = 14) -> List[str]:
    """Compact, human-readable lines for the chat — what the Kernel is
    currently aware of. Suitable for inclusion in any topic handler that
    wants a 'cognitive postscript'."""
    ctx = chat_context()
    sm = ctx["self_model"]
    last_tick = ctx.get("orchestrator_last_tick") or {}
    lines: List[str] = []
    lines.append(f"Topics known: {sm.get('topic_count', 0)}; "
                 f"registries observed: {sm.get('registry_count', 0)}.")
    lines.append(f"Working memory: {ctx['working_memory']['slot_count']}/"
                 f"{ctx['working_memory']['capacity']} slots.")
    lines.append(f"Open curiosity items: {len(ctx['open_curiosity_items_top'])}; "
                 f"open proposals: {len(ctx['open_proposals_top'])}.")
    if ctx.get("low_confidence_belief_keys"):
        lines.append(f"Low-confidence beliefs: "
                     f"{ctx['low_confidence_belief_keys'][:5]}")
    if last_tick:
        lines.append(f"Last tick: {last_tick.get('tick_id', '?')} "
                     f"in {last_tick.get('duration_seconds', '?')}s, "
                     f"{last_tick.get('conclusions', 0)} conclusions, "
                     f"{last_tick.get('contradictions', 0)} contradictions.")
    rt = ctx.get("recent_thoughts", [])
    for t in rt[-3:]:
        lines.append(f"  thought[{t['layer']}]: {t['text']}")
    lines.append("Policy: Kernel THINKS, SPEAKS, PROPOSES — never DOES.")
    return lines[:max_lines]
