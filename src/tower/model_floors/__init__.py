"""QSB Three Model Embassy Floors — Claude / GPT / DeepSeek.

All adapters are advisory by default. External provider calls require BOTH the
provider-specific *_ENABLED=1 env var AND the global
QSB_MODEL_FLOOR_EXTERNAL_CALLS_ENABLED=1.
"""
from .provider_base import ProviderBase, ProviderStatus
from .provider_env import ProviderEnv
from .claude_floor_adapter import ClaudeFloorAdapter
from .openai_gpt_floor_adapter import OpenAIGPTFloorAdapter
from .deepseek_floor_adapter import DeepSeekFloorAdapter
from .model_floor_router import ModelFloorRouter
from .model_floor_safety import ModelFloorSafety
from .model_floor_cost_guard import ModelFloorCostGuard
from .model_floor_reporter import ModelFloorReporter

__all__ = [
    "ProviderBase", "ProviderStatus", "ProviderEnv",
    "ClaudeFloorAdapter", "OpenAIGPTFloorAdapter", "DeepSeekFloorAdapter",
    "ModelFloorRouter", "ModelFloorSafety", "ModelFloorCostGuard",
    "ModelFloorReporter",
]
