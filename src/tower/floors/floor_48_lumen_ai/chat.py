"""Lumen AI chat surface.

Routes a user message through the Kernel topic table. Maintains a
per-conversation rolling history.

Honest behaviour:
  · Lumen calls kernel_dialogue_adapter to match topics + format a
    block. If a topic matches, the reply is the structured block.
  · If NO topic matches, Lumen falls back to a deterministic, honest
    "I don't know about that yet" response — it does NOT invent text
    from a model.
  · The reply always stamps the safety envelope.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import json
import time
import uuid
from pathlib import Path

from tower.cognitive_kernel import REG, write_registry, append_log, now, SAFETY


REGISTRY_NAME = "qsb_floor48_lumen_conversations.json"
MAX_HISTORY_TURNS = 50          # per conversation
MAX_CONVERSATIONS = 200         # cap to keep registry small


@dataclass
class ChatTurn:
    role: str           # 'user' | 'lumen'
    content: str
    ts: float
    matched_topics: List[str] = field(default_factory=list)
    fallback_reason: Optional[str] = None


@dataclass
class Conversation:
    conversation_id: str
    started_ts: float
    last_ts: float
    turns: List[ChatTurn] = field(default_factory=list)
    user_label: str = "guest"


_CONVERSATIONS: Dict[str, Conversation] = {}


def _new_conversation_id() -> str:
    return f"conv_{int(time.time())}_{uuid.uuid4().hex[:6]}"


def _ensure_conversation(conversation_id: Optional[str]) -> Conversation:
    if conversation_id and conversation_id in _CONVERSATIONS:
        return _CONVERSATIONS[conversation_id]
    cid = conversation_id or _new_conversation_id()
    conv = Conversation(conversation_id=cid,
                         started_ts=time.time(),
                         last_ts=time.time())
    _CONVERSATIONS[cid] = conv
    # Enforce cap by dropping the oldest
    if len(_CONVERSATIONS) > MAX_CONVERSATIONS:
        oldest = sorted(_CONVERSATIONS.values(),
                         key=lambda c: c.started_ts)
        for c in oldest[:len(_CONVERSATIONS) - MAX_CONVERSATIONS]:
            _CONVERSATIONS.pop(c.conversation_id, None)
    return conv


def _route_through_kernel(message: str) -> Dict[str, Any]:
    """Call the existing kernel dialogue adapter; return a structured
    response with matched topics + the formatted text block."""
    try:
        from tower import kernel_dialogue_adapter as kda
    except Exception as e:
        return {"matched_topics": [], "block": None,
                "fallback_reason": f"dialogue_adapter_unavailable: {e}"}
    topics = kda._wants_eqsb_topic(message) if hasattr(kda, "_wants_eqsb_topic") else []
    if not topics:
        return {"matched_topics": [],
                "block": None,
                "fallback_reason": "no_topic_matched"}
    block = kda._format_eqsb_block(topics) if hasattr(kda, "_format_eqsb_block") else None
    return {"matched_topics": topics, "block": block,
            "fallback_reason": None}


def _fallback_text(message: str) -> str:
    msg_lower = (message or "").strip().lower()
    if any(g in msg_lower for g in ("hello", "hi ", "hey", "yo", "g'day")):
        return ("Hi — I'm Lumen, the QSB Tower's local chat AI. I answer "
                "from a topic table the Kernel has learned. Ask me about "
                "the bank, family tree, profit plan, free images, "
                "certified workers, or the morning briefing.")
    if msg_lower in ("?", "help"):
        return ("Try one of these: 'show me the family tree', 'who is "
                "profitable', 'tower briefing', 'open an etsy store', "
                "'pay rates', 'what cognitive layers do you have'.")
    return (
        "I don't have a topic for that yet — Lumen is honest about its "
        "limits. I can answer about: bank balances, certifications, "
        "family tree, profit analytics, free-image catalog, curriculum, "
        "self-audit, worker PnL, candidate floors. Try one of those, or "
        "ask 'help' for examples."
    )


def chat_completion(message: str,
                      conversation_id: Optional[str] = None,
                      user_label: str = "guest") -> Dict[str, Any]:
    conv = _ensure_conversation(conversation_id)
    if user_label and conv.user_label == "guest":
        conv.user_label = user_label
    # Append user turn
    conv.turns.append(ChatTurn(role="user", content=message,
                                ts=time.time()))
    # Route through Kernel
    routed = _route_through_kernel(message)
    reply_text: str
    if routed.get("block"):
        # Keep reply concise — show first ~800 chars; leave the full
        # block in matched_topics if the front-end wants more.
        reply_text = routed["block"][:1200]
        if len(routed["block"]) > 1200:
            reply_text += "\n\n[truncated for chat — full block available via kernel chat in dashboard]"
    else:
        reply_text = _fallback_text(message)
    # Append lumen turn
    conv.turns.append(ChatTurn(role="lumen", content=reply_text,
                                ts=time.time(),
                                matched_topics=routed.get("matched_topics") or [],
                                fallback_reason=routed.get("fallback_reason")))
    # Trim history
    if len(conv.turns) > MAX_HISTORY_TURNS:
        conv.turns = conv.turns[-MAX_HISTORY_TURNS:]
    conv.last_ts = time.time()
    append_log("lumen_ai.jsonl", {
        "event": "chat",
        "conversation_id": conv.conversation_id,
        "user_label": conv.user_label,
        "message_len": len(message),
        "matched_topics": routed.get("matched_topics") or [],
        "fallback_reason": routed.get("fallback_reason"),
    })
    persist_conversations()
    return {
        "ok": True,
        "conversation_id": conv.conversation_id,
        "reply": reply_text,
        "matched_topics": routed.get("matched_topics") or [],
        "fallback_reason": routed.get("fallback_reason"),
        "safety_envelope": dict(SAFETY),
        "policy": ("Lumen is powered by the local Kernel. No external "
                    "model inference. No real billing."),
    }


def conversation_history(conversation_id: str) -> Optional[List[Dict[str, Any]]]:
    conv = _CONVERSATIONS.get(conversation_id)
    if not conv:
        return None
    return [asdict(t) for t in conv.turns]


def conversations_snapshot() -> Dict[str, Any]:
    return {
        "ok": True,
        "kind": "qsb_floor48_lumen_conversations",
        "generated_ts": now(),
        "policy": "Per-conversation rolling history. Local only.",
        "conversation_count": len(_CONVERSATIONS),
        "max_history_turns": MAX_HISTORY_TURNS,
        "conversations": [
            {"conversation_id": c.conversation_id,
              "started_ts": c.started_ts,
              "last_ts": c.last_ts,
              "user_label": c.user_label,
              "turn_count": len(c.turns),
              "last_turn_excerpt": (c.turns[-1].content[:160] if c.turns else None),
              "turns": [asdict(t) for t in c.turns[-12:]]}
            for c in sorted(_CONVERSATIONS.values(),
                              key=lambda c: -c.last_ts)[:50]
        ],
    }


def persist_conversations() -> Dict[str, Any]:
    snap = conversations_snapshot()
    p = REG / REGISTRY_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap


def load_conversations() -> int:
    p = REG / REGISTRY_NAME
    if not p.exists():
        return 0
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0
    count = 0
    for r in d.get("conversations") or []:
        cid = r.get("conversation_id")
        if not cid or cid in _CONVERSATIONS:
            continue
        conv = Conversation(
            conversation_id=cid,
            started_ts=float(r.get("started_ts") or 0),
            last_ts=float(r.get("last_ts") or 0),
            user_label=r.get("user_label", "guest"),
            turns=[ChatTurn(
                role=t.get("role", "user"),
                content=t.get("content", ""),
                ts=float(t.get("ts") or 0),
                matched_topics=list(t.get("matched_topics") or []),
                fallback_reason=t.get("fallback_reason"),
            ) for t in (r.get("turns") or [])]
        )
        _CONVERSATIONS[cid] = conv
        count += 1
    return count
