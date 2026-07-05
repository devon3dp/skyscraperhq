"""ProviderBase — common interface for all model floor providers."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .provider_env import ProviderEnv


@dataclass
class ProviderStatus:
    provider_name: str
    floor_id: str
    enabled: bool
    env_key_present: bool
    external_calls_allowed: bool
    manual_test_mode: bool
    model_name: Optional[str] = None
    masked_key: Optional[str] = None
    last_test: Optional[str] = None
    last_error_masked: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    cost_guard: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProviderBase:
    """Subclasses must override env_key_names + provider_name + floor_id."""

    provider_name: str = "base"
    floor_id: str = "F00"
    env_key_names: tuple = ()
    env_enabled_names: tuple = ()
    env_model_names: tuple = ()
    default_model: Optional[str] = None

    def env_key_present(self) -> bool:
        return ProviderEnv.get_presence(*self.env_key_names)

    def is_provider_enabled(self) -> bool:
        return ProviderEnv.is_provider_enabled(*self.env_enabled_names)

    def external_calls_allowed(self) -> bool:
        return ProviderEnv.is_external_calls_enabled() and self.is_provider_enabled()

    def model_name(self) -> Optional[str]:
        return ProviderEnv.get_model(*self.env_model_names, default=self.default_model)

    def masked_key(self) -> str:
        return ProviderEnv.mask_key(ProviderEnv.get_key(*self.env_key_names))

    def cost_guard(self) -> Dict[str, Any]:
        return {
            "max_requests_per_session": ProviderEnv.max_requests_per_session(),
            "max_tokens_per_request":   ProviderEnv.max_tokens_per_request(),
            "log_prompts":              ProviderEnv.should_log_prompts(),
            "mask_secrets":             ProviderEnv.should_mask_secrets(),
            "external_calls_enabled_global": ProviderEnv.is_external_calls_enabled(),
        }

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            provider_name=self.provider_name,
            floor_id=self.floor_id,
            enabled=self.is_provider_enabled(),
            env_key_present=self.env_key_present(),
            external_calls_allowed=self.external_calls_allowed(),
            manual_test_mode=True,
            model_name=self.model_name(),
            masked_key=self.masked_key(),
            cost_guard=self.cost_guard(),
        )

    def health(self) -> Dict[str, Any]:
        s = self.status()
        return {
            "ok": True,
            "provider": s.provider_name,
            "floor_id": s.floor_id,
            "ready_for_external_call": s.external_calls_allowed and s.env_key_present,
            "blocker": self._blocker_reason(s),
        }

    def _blocker_reason(self, s: ProviderStatus) -> Optional[str]:
        if not s.env_key_present:
            return "API key not present in env"
        if not s.enabled:
            return "provider-specific *_ENABLED flag not set"
        if not s.external_calls_allowed:
            return "QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED is not 1"
        return None

    def ask(self, prompt: str) -> Dict[str, Any]:
        """Manual test path. Refuses unless both locks are open."""
        status = self.status()
        if not status.external_calls_allowed:
            return {
                "ok": False,
                "provider": status.provider_name,
                "blocked_by": self._blocker_reason(status),
                "note": "Manual external call refused — see model_floor_safety.",
            }
        if not status.env_key_present:
            return {"ok": False, "provider": status.provider_name, "blocked_by": "no api key in env"}
        return self._do_ask(prompt, status)

    def _do_ask(self, prompt: str, status: ProviderStatus) -> Dict[str, Any]:
        # Subclasses override to actually call the provider. This base only
        # records the manual attempt without performing any network IO.
        return {
            "ok": True,
            "provider": status.provider_name,
            "note": "base implementation; subclass must override _do_ask",
            "echo_prompt_length": len(prompt),
        }

    @staticmethod
    def mask_secrets(text: str) -> str:
        """Redact common API key shapes in arbitrary text before logging."""
        import re
        if not text:
            return text
        patterns = [
            r"sk-ant-[A-Za-z0-9_-]{16,}",
            r"sk-[A-Za-z0-9]{16,}",
            r"ds-[A-Za-z0-9]{16,}",
            r"Bearer\s+[A-Za-z0-9._-]{12,}",
        ]
        for p in patterns:
            text = re.sub(p, "***REDACTED***", text)
        return text
