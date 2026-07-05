"""Floor 49 — Tower Studio state + gates."""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import json

from tower.cognitive_kernel import ROOT, REG, now

FLOOR_ID = "floor_49_tower_studio"
FLOOR_LABEL = "Floor 49 — Tower Studio (Web Design + IT Services)"

FLAGS: Dict[str, bool] = {
    "preview_only":                     True,
    "local_only":                       True,
    "public_website_published":         False,   # localhost only until deploy gate
    "real_payments_enabled":            False,
    "live_listings_publishing_enabled": False,
    "external_api_calls_enabled":       False,
    "autonomous_dispatch_enabled":      False,
    "customer_database_active":         True,
    "project_pipeline_active":          True,
    "qbc_invoicing_active":             True,
}

REGISTRY_NAME = "qsb_floor49_tower_studio_state.json"


def floor_state_snapshot() -> Dict[str, Any]:
    return {
        "ok": True,
        "kind": "qsb_floor49_tower_studio_state",
        "generated_ts": now(),
        "floor_id": FLOOR_ID,
        "floor_label": FLOOR_LABEL,
        "status": "active_local_only",
        "flags": dict(FLAGS),
        "company_name": "Tower Studio",
        "tagline": "Websites, identity, and IT — designed inside the QSB Tower.",
        "worker_roles": [
            "principal_designer",
            "graphics_designer",
            "frontend_developer",
            "backend_developer",
            "copywriter",
            "project_manager",
            "qa_reviewer",
            "client_success_lead",
        ],
        "service_lines": [
            "landing_page_design",
            "multi_page_marketing_site",
            "ecommerce_starter",
            "brand_identity_kit",
            "wordpress_handoff",
            "ongoing_maintenance",
        ],
        "policy": (
            "Local-only studio. Real client onboarding requires a "
            "SEPARATE phase that flips public_website_published + "
            "real_payments_enabled. Until then, all 'orders' are "
            "advisory drafts."
        ),
    }


def persist_floor_state() -> Path:
    snap = floor_state_snapshot()
    p = REG / REGISTRY_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return p


def tick() -> Dict[str, Any]:
    return floor_state_snapshot()
