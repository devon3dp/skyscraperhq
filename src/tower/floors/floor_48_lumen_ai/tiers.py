"""Lumen AI pricing tiers (advisory).

Three tiers. Prices in USD. Internal cost tracked in QBC. No money
moves; tiers are surfaced on the public landing page so the operator
can shape the future real-payment phase against actual pricing intent.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List, Any
import json

from tower.cognitive_kernel import REG, now


@dataclass
class Tier:
    sku: str
    name: str
    price_usd_per_month: float
    monthly_message_quota: int
    rate_limit_per_minute: int
    features: List[str]


PRICING_TIERS: List[Tier] = [
    Tier(
        sku="LUMEN-FREE",
        name="Lumen Free",
        price_usd_per_month=0.0,
        monthly_message_quota=100,
        rate_limit_per_minute=4,
        features=[
            "100 messages / month",
            "4 messages / minute rate limit",
            "Topic-table answers only",
            "Community support",
        ],
    ),
    Tier(
        sku="LUMEN-PRO",
        name="Lumen Pro",
        price_usd_per_month=19.0,
        monthly_message_quota=5_000,
        rate_limit_per_minute=30,
        features=[
            "5,000 messages / month",
            "30 messages / minute rate limit",
            "Full topic table + structured replies",
            "Per-conversation history retained 90 days",
            "Email support",
        ],
    ),
    Tier(
        sku="LUMEN-BUSINESS",
        name="Lumen Business",
        price_usd_per_month=99.0,
        monthly_message_quota=50_000,
        rate_limit_per_minute=120,
        features=[
            "50,000 messages / month",
            "120 messages / minute rate limit",
            "Bring-your-own-registry topics",
            "Priority queue",
            "SLA support",
        ],
    ),
]


def tiers_snapshot() -> Dict[str, Any]:
    return {
        "ok": True,
        "kind": "qsb_floor48_lumen_pricing",
        "generated_ts": now(),
        "policy": ("Advisory pricing. Real billing requires operator "
                    "gate flip + real-money phase."),
        "tier_count": len(PRICING_TIERS),
        "tiers": [asdict(t) for t in PRICING_TIERS],
    }


def persist_tiers() -> Dict[str, Any]:
    snap = tiers_snapshot()
    p = REG / "qsb_floor48_lumen_pricing.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap
