"""Tower Studio services catalog + pricing engine.

Prices are advisory. USD is what customers would see on the public
website; QBC is the internal company unit used by the compensation
engine to pay workers.

Conversion rate is advisory — operator may adjust. NOT a real FX rate.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import json

from tower.cognitive_kernel import REG, now


# Advisory only. Operator may adjust.
QBC_PER_USD_ADVISORY = 1.0


@dataclass
class ServicePackage:
    sku: str
    name: str
    category: str
    short_description: str
    long_description: str
    deliverables: List[str]
    typical_turnaround_days: int
    price_usd: float
    workers_required: List[str]


SERVICES_CATALOG: List[ServicePackage] = [
    ServicePackage(
        sku="TS-LP-STARTER",
        name="Landing Page (Starter)",
        category="landing_page_design",
        short_description="One-page site that converts.",
        long_description=(
            "A single-page marketing site built around one conversion goal "
            "— newsletter signup, free trial, or a single product pitch. "
            "Includes hero, three feature blocks, social proof, and a "
            "call-to-action footer. Mobile-first. Loads under 1 second."
        ),
        deliverables=["responsive HTML/CSS site", "favicon",
                       "1 hero illustration (SVG)",
                       "deploy-ready static bundle"],
        typical_turnaround_days=5,
        price_usd=950.00,
        workers_required=["frontend_developer", "graphics_designer",
                           "copywriter"],
    ),
    ServicePackage(
        sku="TS-LP-PREMIUM",
        name="Landing Page (Premium, A/B tested)",
        category="landing_page_design",
        short_description="Two-variant landing page with conversion tracking.",
        long_description=(
            "Two variants of the landing page. Built-in conversion event "
            "logging (no third-party trackers). One round of revisions per "
            "variant. Delivered with a one-week post-launch read-out."
        ),
        deliverables=["A and B variants", "event logging snippet",
                       "post-launch read-out at day 7"],
        typical_turnaround_days=10,
        price_usd=2400.00,
        workers_required=["frontend_developer", "graphics_designer",
                           "copywriter", "qa_reviewer"],
    ),
    ServicePackage(
        sku="TS-MP-MARKETING",
        name="Multi-Page Marketing Site",
        category="multi_page_marketing_site",
        short_description="Home + 4 pages + contact form, fully editable.",
        long_description=(
            "Home, About, Services, Case Studies, Contact. CMS-free; "
            "content lives in plain markdown so any non-technical "
            "operator can edit. One round of copy revisions. Includes "
            "favicon + apple-touch icons + sitemap.xml."
        ),
        deliverables=["5 pages", "contact form backend",
                       "sitemap.xml", "favicons + opengraph"],
        typical_turnaround_days=14,
        price_usd=4200.00,
        workers_required=["frontend_developer", "graphics_designer",
                           "copywriter", "project_manager"],
    ),
    ServicePackage(
        sku="TS-ECOM-STARTER",
        name="Ecommerce Starter (Square-integrated)",
        category="ecommerce_starter",
        short_description="Online store with up to 25 SKUs and Square checkout.",
        long_description=(
            "Catalog page, product detail page, cart, Square checkout. "
            "Inventory in a simple JSON file (operator-editable). Shipping "
            "calculator with 2 tiers. Order confirmation email template. "
            "Square gates flipped only after the operator wires real "
            "Square credentials in a separate session."
        ),
        deliverables=["storefront", "product DB scaffold",
                       "Square integration scaffold (gate-locked)",
                       "order email templates"],
        typical_turnaround_days=21,
        price_usd=6800.00,
        workers_required=["frontend_developer", "backend_developer",
                           "graphics_designer", "copywriter",
                           "qa_reviewer", "project_manager"],
    ),
    ServicePackage(
        sku="TS-BRAND-KIT",
        name="Brand Identity Kit",
        category="brand_identity_kit",
        short_description="Logo, palette, typography, brand guide.",
        long_description=(
            "Three logo concepts (SVG); chosen logo finalised. Colour "
            "palette with hex + RGB + accessibility checks. Typography "
            "pair (heading + body). One-page brand guide PDF. All assets "
            "delivered as editable SVG and PDF."
        ),
        deliverables=["3 logo concepts (SVG)",
                       "final logo (SVG + PNG)",
                       "palette + type guide PDF",
                       "social media banner templates"],
        typical_turnaround_days=12,
        price_usd=2200.00,
        workers_required=["graphics_designer", "principal_designer"],
    ),
    ServicePackage(
        sku="TS-WP-HANDOFF",
        name="WordPress Build + Operator Handoff",
        category="wordpress_handoff",
        short_description="WordPress site you can run yourself.",
        long_description=(
            "Custom theme, content migration up to 25 pages, plugin set "
            "(SEO + caching + backups), training session for the operator. "
            "We do not host — handoff includes deploy notes."
        ),
        deliverables=["custom theme", "migrated content",
                       "plugin set", "1-hour handoff session",
                       "deploy notes"],
        typical_turnaround_days=18,
        price_usd=3600.00,
        workers_required=["frontend_developer", "backend_developer",
                           "project_manager"],
    ),
    ServicePackage(
        sku="TS-MAINT-MONTHLY",
        name="Ongoing Maintenance (Monthly)",
        category="ongoing_maintenance",
        short_description="Updates, monitoring, light copy edits.",
        long_description=(
            "Monthly retainer. Plugin / dependency updates. Uptime "
            "monitoring. Up to 2 hours of copy / image edits per month. "
            "One emergency response within 24 hours."
        ),
        deliverables=["monthly update report",
                       "uptime dashboard access",
                       "2 hours of edits"],
        typical_turnaround_days=30,
        price_usd=350.00,
        workers_required=["backend_developer", "qa_reviewer"],
    ),
]


def quote_for(sku: str, extra_pages: int = 0,
                rush_factor: float = 1.0) -> Optional[Dict[str, Any]]:
    p = next((s for s in SERVICES_CATALOG if s.sku == sku), None)
    if not p:
        return None
    price = p.price_usd
    # Each extra page adds 12% to a multi-page marketing site, 18% to ecommerce
    if p.category == "multi_page_marketing_site":
        price *= (1 + 0.12 * max(0, extra_pages))
    elif p.category == "ecommerce_starter":
        price *= (1 + 0.18 * max(0, extra_pages))
    # Rush factor — 1.0 normal, 1.25 fast, 1.5 emergency
    price *= max(1.0, min(2.0, rush_factor))
    return {
        "sku": p.sku, "name": p.name,
        "base_price_usd": p.price_usd,
        "extra_pages": extra_pages,
        "rush_factor": rush_factor,
        "quoted_price_usd": round(price, 2),
        "quoted_price_qbc": round(price * QBC_PER_USD_ADVISORY, 2),
        "deliverables": list(p.deliverables),
        "typical_turnaround_days": p.typical_turnaround_days,
        "workers_required": list(p.workers_required),
        "valid_for_days": 14,
        "policy_note": ("Quote is advisory. Real payment is gated "
                        "until operator flips real_payments_enabled."),
    }


def services_snapshot() -> Dict[str, Any]:
    return {
        "ok": True,
        "kind": "qsb_floor49_services_catalog",
        "generated_ts": now(),
        "company_name": "Tower Studio",
        "qbc_per_usd_advisory": QBC_PER_USD_ADVISORY,
        "service_count": len(SERVICES_CATALOG),
        "services": [asdict(s) for s in SERVICES_CATALOG],
        "policy": ("Catalog is advisory. Real bookings require a "
                    "separate phase that flips real_payments_enabled."),
    }


def persist_services() -> Dict[str, Any]:
    snap = services_snapshot()
    p = REG / "qsb_floor49_services_catalog.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap
