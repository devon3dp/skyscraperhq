"""ProviderEnv — read env vars safely, expose presence (not values)."""
from __future__ import annotations
import os
from typing import Optional


class ProviderEnv:
    """Looks up provider env vars without exposing their values."""

    GLOBAL_FLAGS = (
        "QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED",
        "QSB_MODEL_FLOOR_MAX_REQUESTS_PER_SESSION",
        "QSB_MODEL_FLOOR_MAX_TOKENS_PER_REQUEST",
        "QSB_MODEL_FLOOR_LOG_PROMPTS",
        "QSB_MODEL_FLOOR_MASK_SECRETS",
    )

    @staticmethod
    def get_key(*candidates: str) -> Optional[str]:
        for name in candidates:
            v = os.environ.get(name)
            if v:
                return v
        return None

    @staticmethod
    def get_presence(*candidates: str) -> bool:
        return ProviderEnv.get_key(*candidates) is not None

    @staticmethod
    def get_model(*candidates: str, default: Optional[str] = None) -> Optional[str]:
        for name in candidates:
            v = os.environ.get(name)
            if v:
                return v
        return default

    @staticmethod
    def is_external_calls_enabled() -> bool:
        return os.environ.get("QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED", "0") == "1"

    @staticmethod
    def is_provider_enabled(*candidates: str) -> bool:
        for name in candidates:
            if os.environ.get(name) == "1":
                return True
        return False

    @staticmethod
    def max_requests_per_session() -> int:
        try:
            return int(os.environ.get("QSB_MODEL_FLOOR_MAX_REQUESTS_PER_SESSION", "5"))
        except ValueError:
            return 5

    @staticmethod
    def max_tokens_per_request() -> int:
        try:
            return int(os.environ.get("QSB_MODEL_FLOOR_MAX_TOKENS_PER_REQUEST", "1000"))
        except ValueError:
            return 1000

    @staticmethod
    def should_log_prompts() -> bool:
        return os.environ.get("QSB_MODEL_FLOOR_LOG_PROMPTS", "0") == "1"

    @staticmethod
    def should_mask_secrets() -> bool:
        return os.environ.get("QSB_MODEL_FLOOR_MASK_SECRETS", "1") == "1"

    @staticmethod
    def mask_key(value: Optional[str]) -> str:
        """Returns 'sk-XXX...{last4}' or '(absent)'."""
        if not value:
            return "(absent)"
        if len(value) <= 4:
            return "***"
        return f"{value[:3]}XXX...{value[-4:]}"
