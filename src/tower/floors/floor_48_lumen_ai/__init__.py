"""Floor 48 — Lumen AI.

A branded chat service powered by the local Kernel substrate. NOT a new
external model. NOT a wrapper over OpenAI / Anthropic / etc. (external
API calls remain gated). Lumen IS the QSB Kernel, given a face, a name,
and a public-style chat playground.

Why: the user asked for "our own chat AI like OpenAI". Building real
model inference from scratch in this session is not feasible. What we
CAN do honestly:
  · expose the existing kernel_dialogue_adapter as a chat API
  · brand the playground (`Lumen`)
  · scaffold per-conversation history + rate limit + cost-per-message
    (advisory; no real money moves)
  · stamp the safety envelope on every reply
"""

from .state import (
    FLAGS, lumen_state_snapshot, persist_lumen_state,
)
from .chat import (
    chat_completion, conversation_history,
    conversations_snapshot, persist_conversations,
)
from .tiers import (
    PRICING_TIERS, tiers_snapshot,
)

__all__ = [
    "FLAGS", "lumen_state_snapshot", "persist_lumen_state",
    "chat_completion", "conversation_history",
    "conversations_snapshot", "persist_conversations",
    "PRICING_TIERS", "tiers_snapshot",
]
