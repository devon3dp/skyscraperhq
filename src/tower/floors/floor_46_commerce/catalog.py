"""Sandbox product catalog for Floor 46.

A hand-curated set of plausible Etsy-style listings used to:
  · drive the pricing advisor
  · seed the listing-draft reviewer worker role
  · let the dashboard show a real-looking catalog without touching Etsy

These are FAKE products. Nothing is published anywhere.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any
import json

from tower.cognitive_kernel import REG, now
import json as _json


@dataclass
class SandboxProduct:
    sku: str
    title: str
    category: str
    cost_to_produce: float       # estimated direct unit cost
    suggested_price: float       # current draft sell price
    avg_market_price: float      # informational anchor (also sandboxed)
    estimated_demand_monthly: int
    tags: List[str] = field(default_factory=list)
    status: str = "draft"        # draft | review | ready_for_review | held
    notes: str = ""

    def margin_percent(self) -> float:
        if self.suggested_price <= 0:
            return 0.0
        return round((self.suggested_price - self.cost_to_produce)
                     / self.suggested_price * 100.0, 2)

    def vs_market(self) -> float:
        if self.avg_market_price <= 0:
            return 0.0
        return round((self.suggested_price - self.avg_market_price)
                     / self.avg_market_price * 100.0, 2)


# Curated sandbox catalogue — kept deliberately small + clearly fake.
SANDBOX_PRODUCTS: List[SandboxProduct] = [
    SandboxProduct(
        sku="QSB-PRINT-001",
        title="QSB Tower Skyscraper Art Print (Sandbox)",
        category="art_print",
        cost_to_produce=4.50,
        suggested_price=18.00,
        avg_market_price=22.00,
        estimated_demand_monthly=35,
        tags=["wall_art", "architecture", "skyscraper"],
        notes="Anchor product — depicts the QSB Tower; high-margin print.",
    ),
    SandboxProduct(
        sku="QSB-STICKER-002",
        title="Floor 41 OANDA Practice Trader Sticker Pack (Sandbox)",
        category="sticker_pack",
        cost_to_produce=1.20,
        suggested_price=6.00,
        avg_market_price=7.50,
        estimated_demand_monthly=80,
        tags=["sticker", "fx", "trading", "novelty"],
        notes="Cheap impulse buy; supports basket-size lift on the print.",
    ),
    SandboxProduct(
        sku="QSB-DIGI-003",
        title="OpenClaw Routing Notebook Template (Digital, Sandbox)",
        category="digital_template",
        cost_to_produce=0.00,
        suggested_price=9.00,
        avg_market_price=11.00,
        estimated_demand_monthly=20,
        tags=["digital", "notion", "template", "routing"],
        notes="Zero unit cost; 100% margin once delivered.",
    ),
    SandboxProduct(
        sku="QSB-PAT-004",
        title="ML/RL Lab Lab-Notebook PDF Bundle (Sandbox)",
        category="digital_bundle",
        cost_to_produce=0.00,
        suggested_price=24.00,
        avg_market_price=28.00,
        estimated_demand_monthly=15,
        tags=["digital", "ml", "rl", "bundle"],
        notes="High-margin, low-volume; targets the data-science buyer.",
    ),
    SandboxProduct(
        sku="QSB-MUG-005",
        title="Penthouse Kernel 4.5 Coffee Mug (Sandbox)",
        category="physical_mug",
        cost_to_produce=6.50,
        suggested_price=18.00,
        avg_market_price=20.00,
        estimated_demand_monthly=18,
        tags=["mug", "novelty", "kernel"],
        notes="Lower margin; requires print-on-demand partner — NOT wired.",
    ),
    SandboxProduct(
        sku="QSB-TEE-006",
        title="\"I Survived Floor 25 Recruitment\" T-shirt (Sandbox)",
        category="physical_apparel",
        cost_to_produce=9.00,
        suggested_price=24.00,
        avg_market_price=27.00,
        estimated_demand_monthly=12,
        tags=["apparel", "novelty", "recruitment"],
        notes="Apparel margins typical; lowest priority for an MVP launch.",
    ),
]


def catalog_snapshot() -> Dict[str, Any]:
    rows = []
    for p in SANDBOX_PRODUCTS:
        d = asdict(p)
        d["margin_percent"] = p.margin_percent()
        d["vs_market_percent"] = p.vs_market()
        rows.append(d)
    return {
        "ok": True,
        "kind": "qsb_floor46_commerce_catalog",
        "generated_ts": now(),
        "policy": "Sandbox catalogue. No listings published. No marketplace contact.",
        "product_count": len(rows),
        "category_breakdown": _category_breakdown(rows),
        "products": rows,
    }


def _category_breakdown(rows: List[dict]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        cat = r.get("category", "unknown")
        out[cat] = out.get(cat, 0) + 1
    return out


def persist_catalog():
    """Write the catalog registry to data/registries (main floor namespace)."""
    snap = catalog_snapshot()
    p = REG / "qsb_floor46_commerce_catalog.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(snap, indent=2), encoding="utf-8")
    return snap
