"""Route an 'ask <model> ...' intent to the matching floor adapter."""
from __future__ import annotations
from typing import Any, Dict

from .claude_floor_adapter import ClaudeFloorAdapter
from .openai_gpt_floor_adapter import OpenAIGPTFloorAdapter
from .deepseek_floor_adapter import DeepSeekFloorAdapter
from .model_floor_safety import ModelFloorSafety
from .model_floor_cost_guard import ModelFloorCostGuard


class ModelFloorRouter:
    def __init__(self) -> None:
        self.claude = ClaudeFloorAdapter()
        self.gpt = OpenAIGPTFloorAdapter()
        self.deepseek = DeepSeekFloorAdapter()
        self.guard = ModelFloorCostGuard()

    def route(self, target: str, prompt: str) -> Dict[str, Any]:
        safety = ModelFloorSafety.screen(prompt)
        if not safety["ok"]:
            return {"ok": False, "blocked_by_safety": safety["reason"]}
        t = (target or "").lower()
        if t in ("claude", "f47"):
            return self.claude.ask(prompt)
        if t in ("gpt", "chatgpt", "openai", "f48"):
            gate = self.guard.check_and_increment("gpt")
            if not gate["ok"]:
                return {"ok": False, "blocked_by_cost_guard": gate["reason"]}
            return self.gpt.ask(prompt)
        if t in ("deepseek", "ds", "f49"):
            gate = self.guard.check_and_increment("deepseek")
            if not gate["ok"]:
                return {"ok": False, "blocked_by_cost_guard": gate["reason"]}
            return self.deepseek.ask(prompt)
        return {"ok": False, "reason": f"unknown model floor target: {target}"}

    def all_status(self) -> Dict[str, Any]:
        return {
            "claude":   self.claude.status().to_dict(),
            "gpt":      self.gpt.status().to_dict(),
            "deepseek": self.deepseek.status().to_dict(),
            "cost_guard_snapshot": self.guard.snapshot(),
        }
