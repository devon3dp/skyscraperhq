"""FreeImageCatalog — Curated catalog of commercial-use-safe image sources.

Stores ONLY metadata. Never fetches binaries. Never publishes. The
listing-draft pipeline produces draft listings that the operator must
explicitly approve before any image is downloaded or any product goes
live.

License pre-flight is enforced: a source flagged commercial_ok=False
cannot enter the listing pipeline at all.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import time

from . import write_registry, append_log, now


@dataclass
class ImageSource:
    name: str
    homepage: str
    license_name: str
    commercial_ok: bool
    attribution_required: bool
    share_alike_required: bool
    derivative_works_ok: bool
    notes: str = ""


SOURCES: List[ImageSource] = [
    ImageSource(
        name="Unsplash",
        homepage="https://unsplash.com",
        license_name="Unsplash License",
        commercial_ok=True, attribution_required=False,
        share_alike_required=False, derivative_works_ok=True,
        notes="Cannot sell unaltered photos on a stock platform; "
              "derivative + transformed products fine.",
    ),
    ImageSource(
        name="Pexels",
        homepage="https://pexels.com",
        license_name="Pexels License",
        commercial_ok=True, attribution_required=False,
        share_alike_required=False, derivative_works_ok=True,
        notes="No identifiable people in commercial promo without consent.",
    ),
    ImageSource(
        name="Pixabay",
        homepage="https://pixabay.com",
        license_name="Pixabay Content License",
        commercial_ok=True, attribution_required=False,
        share_alike_required=False, derivative_works_ok=True,
        notes="Some images have model/property releases; check per image.",
    ),
    ImageSource(
        name="NASA Image Library",
        homepage="https://images.nasa.gov",
        license_name="US Public Domain (mostly)",
        commercial_ok=True, attribution_required=False,
        share_alike_required=False, derivative_works_ok=True,
        notes="Some images include third-party content (e.g., partners); "
              "check per asset.",
    ),
    ImageSource(
        name="Wikimedia Commons (CC0 subset)",
        homepage="https://commons.wikimedia.org",
        license_name="CC0 1.0",
        commercial_ok=True, attribution_required=False,
        share_alike_required=False, derivative_works_ok=True,
        notes="ONLY the CC0 subset. CC-BY-SA images require attribution "
              "AND share-alike — DO NOT use for non-attributing products.",
    ),
    ImageSource(
        name="Smithsonian Open Access",
        homepage="https://www.si.edu/openaccess",
        license_name="CC0 1.0",
        commercial_ok=True, attribution_required=False,
        share_alike_required=False, derivative_works_ok=True,
    ),
    ImageSource(
        name="Library of Congress (public domain)",
        homepage="https://www.loc.gov/free-to-use",
        license_name="US Public Domain",
        commercial_ok=True, attribution_required=False,
        share_alike_required=False, derivative_works_ok=True,
        notes="Limit to clearly-marked free-to-use collections.",
    ),
    ImageSource(
        name="Rijksmuseum",
        homepage="https://www.rijksmuseum.nl/en/rijksstudio",
        license_name="CC0 1.0 (for many high-res scans)",
        commercial_ok=True, attribution_required=False,
        share_alike_required=False, derivative_works_ok=True,
    ),
    ImageSource(
        name="The Met Museum Open Access",
        homepage="https://www.metmuseum.org/art/collection/search",
        license_name="CC0 1.0",
        commercial_ok=True, attribution_required=False,
        share_alike_required=False, derivative_works_ok=True,
        notes="Look for the 'Open Access' tag — not all works qualify.",
    ),
]


# Derivative-product templates each source image can become.
DERIVATIVE_PRODUCTS = [
    {"sku_suffix": "PRINT",   "category": "art_print",
     "title_template": "{source_title} — Art Print",
     "base_cost": 4.50, "suggested_price": 18.0,
     "transformation": "crop + posterize + paper print",
     "notional_demand_monthly": 25},
    {"sku_suffix": "STKR",    "category": "sticker_pack",
     "title_template": "{source_title} — Sticker Pack",
     "base_cost": 1.20, "suggested_price": 6.0,
     "transformation": "cut-out variants",
     "notional_demand_monthly": 70},
    {"sku_suffix": "MUG",     "category": "physical_mug",
     "title_template": "{source_title} — Mug",
     "base_cost": 6.50, "suggested_price": 18.0,
     "transformation": "centered + bleed",
     "notional_demand_monthly": 15},
    {"sku_suffix": "CASE",    "category": "phone_case",
     "title_template": "{source_title} — Phone Case",
     "base_cost": 7.0, "suggested_price": 22.0,
     "transformation": "vertical crop",
     "notional_demand_monthly": 12},
    {"sku_suffix": "DIGI",    "category": "digital_download",
     "title_template": "{source_title} — Digital Download Bundle",
     "base_cost": 0.0, "suggested_price": 9.0,
     "transformation": "multi-format download (4K, A4, 16:9)",
     "notional_demand_monthly": 20},
]


@dataclass
class DraftListing:
    draft_id: str
    sku: str
    source_name: str
    source_license: str
    commercial_ok: bool
    title: str
    category: str
    base_cost: float
    suggested_price: float
    transformation: str
    notional_demand_monthly: int
    projected_revenue: float
    projected_profit: float
    status: str = "draft_from_free_image"
    notes: str = ""


def projection(template: dict) -> Dict[str, float]:
    rev = template["suggested_price"] * template["notional_demand_monthly"]
    profit = ((template["suggested_price"] - template["base_cost"])
              * template["notional_demand_monthly"])
    return {"rev": round(rev, 2), "profit": round(profit, 2)}


def synthesize_drafts(source_name: str,
                       source_title: str = "Open Source Image") -> List[DraftListing]:
    src = next((s for s in SOURCES if s.name == source_name), None)
    if not src:
        return []
    if not src.commercial_ok:
        append_log("free_image_catalog.jsonl", {
            "event": "draft_refused_no_commercial",
            "source": source_name,
        })
        return []
    out: List[DraftListing] = []
    base_sku = ("QSB-FI-" + "".join(c for c in source_name.upper() if c.isalnum())[:5])
    for tpl in DERIVATIVE_PRODUCTS:
        proj = projection(tpl)
        d = DraftListing(
            draft_id=f"draft_{int(time.time()*1000)}_{tpl['sku_suffix']}",
            sku=f"{base_sku}-{tpl['sku_suffix']}",
            source_name=source_name,
            source_license=src.license_name,
            commercial_ok=src.commercial_ok,
            title=tpl["title_template"].format(source_title=source_title),
            category=tpl["category"],
            base_cost=tpl["base_cost"],
            suggested_price=tpl["suggested_price"],
            transformation=tpl["transformation"],
            notional_demand_monthly=tpl["notional_demand_monthly"],
            projected_revenue=proj["rev"],
            projected_profit=proj["profit"],
            notes=("Operator must explicitly approve BOTH fetching the "
                    "source image AND publishing the listing. No "
                    "auto-fetch. No auto-publish."),
        )
        out.append(d)
    return out


def snapshot() -> Dict[str, Any]:
    # Build a sample synthesis for each commercially-OK source (one
    # representative source-title placeholder) so the operator sees the
    # full possible draft set.
    drafts: List[DraftListing] = []
    for s in SOURCES:
        if not s.commercial_ok: continue
        drafts.extend(synthesize_drafts(s.name,
                                         source_title=f"{s.name} sample"))
    total_proj_rev = sum(d.projected_revenue for d in drafts)
    total_proj_profit = sum(d.projected_profit for d in drafts)
    return {
        "ok": True,
        "kind": "cognitive_free_image_catalog",
        "generated_ts": now(),
        "policy": ("Sources + draft listings. No image fetched. No "
                    "listing published. Operator approves BOTH gates."),
        "external_api_calls_enabled": False,
        "live_listings_publishing_enabled": False,
        "source_count": len(SOURCES),
        "commercial_safe_source_count": sum(1 for s in SOURCES if s.commercial_ok),
        "derivative_product_template_count": len(DERIVATIVE_PRODUCTS),
        "draft_listing_count": len(drafts),
        "projected_monthly_revenue_per_source_full_synth":
            round(total_proj_rev / max(1, sum(1 for s in SOURCES if s.commercial_ok)), 2),
        "projected_monthly_revenue_full_synth": round(total_proj_rev, 2),
        "projected_monthly_profit_full_synth": round(total_proj_profit, 2),
        "sources": [asdict(s) for s in SOURCES],
        "derivative_templates": DERIVATIVE_PRODUCTS,
        "draft_sample": [asdict(d) for d in drafts[:20]],
    }


def persist() -> Dict[str, Any]:
    snap = snapshot()
    write_registry("cognitive_free_image_catalog.json", snap)
    return snap
