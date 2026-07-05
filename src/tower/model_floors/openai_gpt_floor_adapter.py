"""OpenAI / GPT floor adapter — scaffold only. Never calls an external API
unless BOTH locks are open AND the user manually invokes it."""
from __future__ import annotations
from typing import Any, Dict

from .provider_base import ProviderBase, ProviderStatus


class OpenAIGPTFloorAdapter(ProviderBase):
    provider_name = "OpenAI GPT"
    floor_id = "F48"
    env_key_names = ("QSB_OPENAI_API_KEY", "OPENAI_API_KEY")
    env_enabled_names = ("QSB_OPENAI_ENABLED",)
    env_model_names = ("QSB_OPENAI_MODEL",)
    default_model = None              # do not hardcode a model assumption

    def _do_ask(self, prompt: str, status: ProviderStatus) -> Dict[str, Any]:
        # This is the manually-invoked safe path. Even here we deliberately
        # describe what WOULD happen rather than performing the call, because
        # this scaffold ships without a vetted HTTP client. The user explicitly
        # enables a real bridge by wiring it themselves.
        return {
            "ok": True,
            "provider": self.provider_name,
            "would_call_endpoint": "https://api.openai.com/v1/chat/completions",
            "model_resolved_from_env": self.model_name(),
            "prompt_length": len(prompt),
            "external_call_made": False,
            "note": "Scaffold path — real HTTP call deliberately not implemented here. Wire your own vetted client when ready.",
        }
