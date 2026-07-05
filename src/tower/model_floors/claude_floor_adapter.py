"""Claude floor — local advisory floor. No API key required. Detects optional
Claude CLI. Floor stays visible even without CLI; the design manifesto
remains the heart of the floor."""
from __future__ import annotations
import os
import shutil
import json
from typing import Any, Dict

from .provider_base import ProviderBase, ProviderStatus


class ClaudeFloorAdapter(ProviderBase):
    provider_name = "Anthropic Claude"
    floor_id = "F47"
    env_key_names = ()                # local floor — no API key required
    env_enabled_names = ()
    env_model_names = ()
    default_model = "local-claude-cli"

    def __init__(self) -> None:
        self._cli_path = self._detect_cli()

    def _detect_cli(self) -> str | None:
        for c in ("claude", "claude-cli"):
            p = shutil.which(c)
            if p:
                return p
        return None

    def cli_available(self) -> bool:
        return self._cli_path is not None

    def status(self) -> ProviderStatus:
        s = ProviderStatus(
            provider_name=self.provider_name,
            floor_id=self.floor_id,
            enabled=True,                                # local advisory always on
            env_key_present=False,
            external_calls_allowed=False,
            manual_test_mode=True,
            model_name=self.default_model if self.cli_available() else "design-manifesto-only",
            masked_key="(local floor — no api key required)",
        )
        s.cost_guard = self.cost_guard()
        if not self.cli_available():
            s.notes.append("Claude CLI not detected — floor stays in design-manifesto-only mode.")
        else:
            s.notes.append(f"Claude CLI detected at {self._cli_path}.")
        return s

    def ask(self, prompt: str) -> Dict[str, Any]:
        """The Claude floor's 'ask' is advisory — it consults the local
        design manifest and (if CLI present) describes a plan WITHOUT
        executing it. Never calls an external API."""
        manifest_path = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_floor_design_manifest.json"
        manifest = {}
        try:
            manifest = json.load(open(manifest_path))
        except Exception:
            pass
        reply_lines = [
            "[Claude floor · advisory only]",
            "",
            "Your prompt: " + (prompt[:200] if prompt else ""),
            "",
            "Mode: " + ("CLI available · proposes plan only" if self.cli_available() else "design-manifesto-only · no CLI detected"),
            "",
            "Claude's standing refusals on this floor:",
        ]
        for rule in manifest.get("refusals", []):
            reply_lines.append("  · " + str(rule))
        return {
            "ok": True,
            "provider": self.provider_name,
            "advisory": True,
            "external_call_made": False,
            "reply": "\n".join(reply_lines),
        }
