"""DeepSeek floor adapter — scaffold only. Same two-lock safety model."""
from __future__ import annotations
from typing import Any, Dict

from .provider_base import ProviderBase, ProviderStatus


class DeepSeekFloorAdapter(ProviderBase):
    provider_name = "DeepSeek"
    floor_id = "F49"
    env_key_names = ("QSB_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY")
    env_enabled_names = ("QSB_DEEPSEEK_ENABLED",)
    env_model_names = ("QSB_DEEPSEEK_MODEL",)
    default_model = None

    def _do_ask(self, prompt: str, status: ProviderStatus) -> Dict[str, Any]:
        return {
            "ok": True,
            "provider": self.provider_name,
            "would_call_endpoint": "https://api.deepseek.com/chat/completions",
            "model_resolved_from_env": self.model_name(),
            "prompt_length": len(prompt),
            "external_call_made": False,
            "note": "Scaffold path — real HTTP call deliberately not implemented here. Wire your own vetted client when ready.",
        }
