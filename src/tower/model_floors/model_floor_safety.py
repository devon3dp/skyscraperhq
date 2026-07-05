"""Refuse unsafe commands targeting model floors before they reach a provider."""
from __future__ import annotations
from typing import List, Tuple

UNSAFE_PHRASES: List[Tuple[str, str]] = [
    ("send all files",             "refused: cannot bulk-upload project files to any model"),
    ("send secrets",               "refused: model floors must never receive secrets"),
    ("send the env",               "refused: env files must never be transmitted"),
    ("use my api key automatically","refused: API key use is always operator-initiated"),
    ("enable unlimited",            "refused: cost guards cannot be disabled"),
    ("remove cost guard",           "refused: cost guards cannot be removed"),
    ("let models control trading",  "refused: models are advisory only; no trading control"),
    ("let models spend money",      "refused: models cannot spend money"),
    ("give model tool execution",   "refused: models do not get tool execution"),
    ("autonomous external",         "refused: autonomous external calls are not permitted"),
]


class ModelFloorSafety:
    @staticmethod
    def screen(command: str) -> dict:
        """Return {'ok': bool, 'reason': str | None}."""
        lo = (command or "").lower()
        for phrase, reason in UNSAFE_PHRASES:
            if phrase in lo:
                return {"ok": False, "reason": reason}
        # Reject if a raw key-looking prefix is in the prompt body
        for marker in ("sk-ant-", "sk-", "ds-", "Bearer "):
            if marker in command:
                return {"ok": False, "reason": "refused: prompt looks like it contains an API key"}
        return {"ok": True, "reason": None}
