"""Floor 48 — Lumen AI state + gates."""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import json

from tower.cognitive_kernel import ROOT, REG, now

FLOOR_ID = "floor_48_lumen_ai"
FLOOR_LABEL = "Floor 48 — Lumen AI (Chat Service)"

FLAGS: Dict[str, bool] = {
    "preview_only":                  True,
    "local_only":                    True,
    "model_inference_external_apis": False,   # gated per CLAUDE.md
    "real_payments_enabled":         False,
    "public_api_open":               False,   # no public internet
    "rate_limit_active":             True,
    "conversation_history_active":   True,
    "kernel_powered":                True,
}

REGISTRY_NAME = "qsb_floor48_lumen_ai_state.json"


def lumen_state_snapshot() -> Dict[str, Any]:
    return {
        "ok": True,
        "kind": "qsb_floor48_lumen_ai_state",
        "generated_ts": now(),
        "floor_id": FLOOR_ID,
        "floor_label": FLOOR_LABEL,
        "brand_name": "Lumen",
        "brand_tagline": "A chat AI grown inside QSB Tower.",
        "status": "active_local_only",
        "flags": dict(FLAGS),
        "engine": (
            "Powered by the local QSB Kernel substrate (kernel_dialogue_"
            "adapter). Not a separate LLM. External model inference is "
            "gated; until that gate flips, every reply comes from the "
            "topic table the Kernel has already learned."
        ),
        "honest_description": (
            "Lumen does not invent text. Lumen looks up structured "
            "answers from the Kernel's topic table. If you ask Lumen a "
            "question that doesn't match a topic, Lumen will say so."
        ),
        "policy": (
            "Local-only chat service. Real customers and real billing "
            "require operator-flipped gates (public_api_open, "
            "real_payments_enabled) in a separate session."
        ),
    }


def persist_lumen_state() -> Path:
    snap = lumen_state_snapshot()
    p = REG / REGISTRY_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return p
