"""Track per-session request counts and enforce caps."""
from __future__ import annotations
import json
import os
from typing import Dict

from .provider_env import ProviderEnv

STATE_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_model_floor_cost_guard_state.json"


class ModelFloorCostGuard:
    def __init__(self) -> None:
        self.state: Dict[str, int] = self._load()

    def _load(self) -> Dict[str, int]:
        try:
            with open(STATE_PATH) as f:
                d = json.load(f)
                return d.get("requests_this_session", {}) or {}
        except Exception:
            return {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
            json.dump({
                "ok": True,
                "kind": "qsb_model_floor_cost_guard_state",
                "requests_this_session": self.state,
                "limits": {
                    "max_requests_per_session": ProviderEnv.max_requests_per_session(),
                    "max_tokens_per_request":   ProviderEnv.max_tokens_per_request(),
                },
            }, open(STATE_PATH, "w"), indent=2)
        except Exception:
            pass

    def check_and_increment(self, provider: str) -> dict:
        cap = ProviderEnv.max_requests_per_session()
        cur = int(self.state.get(provider, 0))
        if cur >= cap:
            return {"ok": False, "reason": f"cost guard: {cur}/{cap} requests this session"}
        self.state[provider] = cur + 1
        self._save()
        return {"ok": True, "count_after": self.state[provider], "cap": cap}

    def snapshot(self) -> dict:
        return {
            "requests_this_session": dict(self.state),
            "max_requests_per_session": ProviderEnv.max_requests_per_session(),
            "max_tokens_per_request":   ProviderEnv.max_tokens_per_request(),
            "external_calls_enabled_global": ProviderEnv.is_external_calls_enabled(),
        }
