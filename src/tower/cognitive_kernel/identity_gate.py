"""IdentityGate — Layer · Hard enforcement: identity paragraph fires
ONLY when intent == IDENTITY. No exceptions.

The pre-existing kernel_dialogue_adapter has IDENTITY classification
but still appends the identity paragraph as a safety-net fallback when
no topic matched. This gate logs every such fall-through so we can see
*exactly* which questions are slipping past the topic table.
"""

from __future__ import annotations
from typing import List, Optional

from . import append_log, write_registry

IDENTITY_INTENT_NAME = "IDENTITY"


def is_identity_intent(intent: str) -> bool:
    return intent.upper() == IDENTITY_INTENT_NAME


def should_render_identity(intent: str, topics_matched: List[str],
                            handler_blocks_produced: int,
                            user_explicitly_asked_identity: bool = False) -> bool:
    """Authoritative gate. Returns True ONLY if identity paragraph is
    appropriate. Logs every decision."""
    decision = False
    reason = ""
    if user_explicitly_asked_identity:
        decision = True; reason = "user_explicit_identity_query"
    elif is_identity_intent(intent):
        decision = True; reason = "intent_eq_IDENTITY"
    elif handler_blocks_produced == 0 and not topics_matched:
        # Safety-net case — still allowed but logged loudly
        decision = True; reason = "safety_net_no_topic_matched"
        append_log("identity_gate_safetynet.jsonl", {
            "event": "identity_safety_net_fired",
            "intent": intent,
            "topics_matched": topics_matched,
            "warning": "topic table missed this query — consider adding handler",
        })
    else:
        decision = False; reason = "topic_handlers_satisfy_query"
    append_log("identity_gate.jsonl", {
        "decision": decision, "reason": reason,
        "intent": intent, "topics_matched": topics_matched,
        "handler_blocks_produced": handler_blocks_produced,
    })
    return decision


def gate_state() -> dict:
    """Snapshot of the gate's enforcement state."""
    return {
        "ok": True,
        "kind": "cognitive_identity_gate_state",
        "identity_paragraph_allowed_when": [
            "user_explicit_identity_query",
            "intent == IDENTITY",
            "safety_net_no_topic_matched (logged loudly)",
        ],
        "identity_paragraph_FORBIDDEN_when": [
            "any topic block was produced",
            "intent in (READ_ONLY_DIAGNOSTIC, GENERAL_CONVERSATION) with non-empty topics",
        ],
        "audit_log": "data/logs/cognitive/identity_gate.jsonl",
        "safetynet_log": "data/logs/cognitive/identity_gate_safetynet.jsonl",
    }


def persist() -> None:
    write_registry("cognitive_identity_gate.json", gate_state())
