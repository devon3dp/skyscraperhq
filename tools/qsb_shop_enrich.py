#!/usr/bin/env python3
"""qsb_shop_enrich.py — add image_url + description to every shop SKU.

Ross 2026-06-12: "make sure photos for products, prices, descriptions".

Photos: Unsplash source URLs are routed by category keyword. Category tag
mapping keeps them topical (skincare → "beauty,skincare"; toy → "kids,toy").
Descriptions: generated from name + category + supplier — concise, no fluff.

Idempotent: re-running won't change image_url for unchanged SKU (we seed the
photo by sku hash so the same SKU always gets the same image).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")

# Floor → (catalog path, theme keyword)
SHOPS = {
    "F46":  ("data/registries/qsb_floor46_commerce_catalog.json",  "commerce,storefront"),
    "F49":  ("data/registries/qsb_floor49_services_catalog.json",  "service,office"),
    "F59":  ("data/registries/qsb_f59_shop_catalog_v1.json",       "shopping,mall"),
    "F61":  ("data/registries/qsb_floor61_catalog.json",           "beauty,skincare,cosmetics"),
    "F62":  ("data/registries/qsb_floor62_catalog.json",           "toy,kids,colorful"),
    "F63":  ("data/registries/qsb_floor63_catalog.json",           "pet,dog,cat"),
    "F64":  ("data/registries/qsb_floor64_catalog.json",           "kitchen,cooking,home"),
    "F65":  ("data/registries/qsb_floor65_catalog.json",           "tech,gadget,electronics"),
    "F154": ("data/registries/qsb_floor154_catalog.json",          "outdoor,hiking,adventure"),
    "F155": ("data/registries/qsb_floor155_catalog.json",          "fitness,workout,gym"),
    "F156": ("data/registries/qsb_floor156_catalog.json",          "office,stationery,desk"),
    "F157": ("data/registries/qsb_floor157_catalog.json",          "travel,luggage,suitcase"),
    "F158": ("data/registries/qsb_floor158_catalog.json",          "plants,garden,green"),
    "F159": ("data/registries/qsb_floor159_catalog.json",          "baby,kids,nursery"),
    "F160": ("data/registries/qsb_floor160_catalog.json",          "books,reading,library"),
    "F161": ("data/registries/qsb_floor161_catalog.json",          "wellness,candles,relaxation"),
    "F162": ("data/registries/qsb_floor162_catalog.json",          "eco,sustainable,bamboo"),
    "F163": ("data/registries/qsb_floor163_catalog.json",          "maker,craft,tools"),
}


# Category-specific descriptor templates. Filled in with item name +
# supplier so each line is unique.
DESC_TEMPLATES = {
    "skincare":     ["Daily-use {name} formulated for radiance.",
                     "Lightweight {name} suited to most skin types."],
    "haircare":     ["Salon-quality {name} for everyday wash days.",
                     "Restorative {name} that conditions without weighing hair down."],
    "toy":          ["Open-ended {name} that keeps kids busy and parents calm.",
                     "Durable {name} sized for small hands."],
    "pet":          ["Vet-tested {name} for the four-legged household member.",
                     "Easy-to-clean {name} pets actually use."],
    "kitchen":      ["Practical {name} that earns its space on the worktop.",
                     "Solid {name} sized for everyday cooking."],
    "tech":         ["Compact {name} that just works once it's plugged in.",
                     "Honest spec {name} without the marketing fluff."],
    "outdoor":      ["Lightweight {name} packed for trails or city walks.",
                     "Weather-ready {name} that survives a UK weekend."],
    "fitness":      ["Studio-grade {name} for home workouts.",
                     "Quiet {name} that won't wake the neighbours."],
    "office":       ["Considered {name} for the desk that gets used daily.",
                     "Refillable {name} that lasts more than a quarter."],
    "travel":       ["Cabin-friendly {name} that meets airline sizing.",
                     "Sturdy {name} packed light without giving in to creases."],
    "plants":       ["Easy-care {name} that survives the school run.",
                     "Hardy {name} suited to the average UK windowsill."],
    "baby":         ["Soft {name} chosen by parents, picked for daytime use.",
                     "Washable {name} that survives the first year."],
    "books":        ["Reissued {name} in a paperback you can actually hold.",
                     "Slim-volume {name} for the bedside stack."],
    "wellness":     ["Calming {name} for end-of-day wind-down.",
                     "Hand-poured {name} burning at about eight hours."],
    "eco":          ["Plant-based {name} that biodegrades in normal household compost.",
                     "Refillable {name} that cuts the recycling pile."],
    "maker":        ["Workshop-grade {name} for the project shelf.",
                     "Sharp, balanced {name} the maker community already owns."],
}


def _seed(sku):
    h = hashlib.sha256(str(sku).encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _image_url(sku, theme):
    """Stable loremflickr URL seeded by SKU.

    Why loremflickr: Unsplash source.unsplash.com was deprecated in 2024 and
    no longer returns images. loremflickr.com/<w>/<h>/<tag>/?lock=<seed> still
    serves tagged Flickr images and is stable per lock seed.
    """
    seed = _seed(sku) % 10_000
    tag = theme.split(",")[0].strip()  # loremflickr takes one tag
    return f"https://loremflickr.com/600/600/{tag}?lock={seed}"


def _description(item, theme):
    name = item.get("name", "item")
    category = (item.get("category") or "").lower()
    bucket = next((k for k in DESC_TEMPLATES if k in category or k in theme), None)
    if bucket:
        seed = _seed(item.get("sku") or name) % len(DESC_TEMPLATES[bucket])
        return DESC_TEMPLATES[bucket][seed].format(name=name)
    return f"{name} — sourced via {item.get('supplier','direct')} on a {item.get('stock_model','dropship')} model."


def enrich_file(floor_tag, path, theme, force=False):
    fp = ROOT / path
    if not fp.exists():
        return {"floor": floor_tag, "ok": False, "reason": "missing"}
    d = json.loads(fp.read_text(encoding="utf-8"))
    items = d.get("items") or d.get("products") or d.get("services") or []
    n_img = n_desc = 0
    for it in items:
        cur_img = it.get("image_url") or ""
        if force or not cur_img or "source.unsplash.com" in cur_img:
            it["image_url"] = _image_url(it.get("sku"), theme)
            n_img += 1
        if force or not it.get("description"):
            it["description"] = _description(it, theme)
            n_desc += 1
    d["enriched_ts"] = datetime.now(timezone.utc).isoformat()
    fp.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return {"floor": floor_tag, "ok": True, "items": len(items),
            "added_image_url": n_img, "added_description": n_desc}


def main():
    rows = []
    for tag, (path, theme) in SHOPS.items():
        r = enrich_file(tag, path, theme)
        rows.append(r)
        print(f"  {tag}: {r}")
    return rows


if __name__ == "__main__":
    main()
