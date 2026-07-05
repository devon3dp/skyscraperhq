"""Floor 46 state + gates.

Every published registry stamps FLAGS verbatim so a downstream reader
can trust that nothing has gone live just because a floor module loaded.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import json
import time

from tower.cognitive_kernel import ROOT, REG, write_registry, append_log, now

FLOOR_ID = "floor_46_commerce"
FLOOR_LABEL = "Floor 46 — Commerce Wing (Etsy Preview-Only)"

# Gates. Every one is False. The operator may flip
# live_listings_publishing_enabled later; nothing in this module flips
# anything itself.
FLAGS: Dict[str, bool] = {
    "live_listings_publishing_enabled": False,
    "payments_enabled":                 False,
    "external_api_calls_enabled":       False,
    "etsy_oauth_enabled":               False,
    "etsy_real_marketplace_contact":    False,
    "openclaw_real_tool_execution_enabled": False,
    "autonomous_dispatch_enabled":      False,
    "preview_only":                     True,
    "sandbox_catalog_active":           True,
}

REGISTRY_NAME = "qsb_floor46_commerce_state.json"
LOG_NAME = "qsb_floor46_commerce.jsonl"


def floor_state_snapshot() -> Dict[str, Any]:
    return {
        "ok": True,
        "kind": "qsb_floor46_commerce_state",
        "generated_ts": now(),
        "floor_id": FLOOR_ID,
        "floor_label": FLOOR_LABEL,
        "status": "active_preview_only",
        "flags": dict(FLAGS),
        "worker_roles": [
            "catalog_curator",
            "product_photographer",
            "copywriter",
            "pricing_analyst",
            "listing_draft_reviewer",
        ],
        "data_paths": {
            "registry": str(REG / REGISTRY_NAME),
            "log":      str(ROOT / "data/logs" / LOG_NAME),
        },
        "policy": (
            "Preview only. No marketplace contact. No payments. No public "
            "listings. Operator must explicitly flip "
            "live_listings_publishing_enabled to publish a real listing — "
            "even then, publishing remains a separate Claude phase, not an "
            "automatic side effect."
        ),
    }


def persist_floor_state() -> Path:
    snap = floor_state_snapshot()
    p = REG / REGISTRY_NAME
    p.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return p


def tick() -> Dict[str, Any]:
    """One advisory cycle. Logs a heartbeat; never reaches any network."""
    snap = floor_state_snapshot()
    persist_floor_state()
    append_log_path = ROOT / "data/logs" / LOG_NAME
    append_log_path.parent.mkdir(parents=True, exist_ok=True)
    with append_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "event": "floor46_tick",
            "ts": now(),
            "flags": dict(FLAGS),
        }) + "\n")
    return snap
