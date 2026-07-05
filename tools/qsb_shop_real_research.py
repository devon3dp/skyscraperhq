#!/usr/bin/env python3
"""qsb_shop_real_research.py — F47 strategy_researchers rebuild shop catalogs.

For each of the 18 remaining shops (F46, F49, F59, F61-65, F154-163), run a
single OpenAI consult to get real supplier names, real brand names, real UK
retail prices. Replace placeholder catalog entries with the researched data.

Pattern matches what was done for F149 (Greenline seed centre).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")

SHOPS = [
    # F46 commerce, F49 services — keep as-is (services not products)
    ("F59",  "Tower Sound", "audio/music gear — earbuds, headphones, small speakers, mics for podcasting", "audio"),
    ("F61",  "Lumière Beauty", "UK indie + mass beauty: serums, jade rollers, moisturisers, masks", "beauty"),
    ("F62",  "Pinwheel Toys", "UK toys for ages 3-10: building, plush, art, board games", "toys"),
    ("F63",  "Pawsworth", "UK pet retail: dog/cat food, beds, leads, toys, grooming", "pets"),
    ("F64",  "Hearthstone Kitchen", "UK kitchenware: cast iron, knives, blenders, small appliances", "kitchen"),
    ("F65",  "Vector Tech", "UK consumer tech: chargers, hubs, small accessories", "tech"),
    ("F154", "Trailhead Outdoor", "UK outdoor gear: jackets, rucksacks, hiking boots, trail running", "outdoor"),
    ("F155", "Stretch Fitness", "UK fitness equipment: mats, bands, kettlebells, smart fitness", "fitness"),
    ("F156", "Quilltree Office", "UK office supplies: notebooks, pens, desk organisation", "office"),
    ("F157", "Voyage & Co", "UK travel: cabin luggage, packing cubes, travel accessories", "travel"),
    ("F158", "Greenhouse Lane", "UK indoor plants + plant care: pots, fertiliser, propagation", "plants"),
    ("F159", "Little Robin", "UK baby + early kids: clothing, sleep, feeding, soft toys", "baby"),
    ("F160", "Inkwell & Co", "UK books: fiction, non-fiction, children's, paperback", "books"),
    ("F161", "Twilight Wellness", "UK wellness: candles, diffusers, supplements, sleep aids", "wellness"),
    ("F162", "Living Light Eco", "UK eco/sustainable: bamboo, refillable cleaning, biodegradable", "eco"),
    ("F163", "Maker Lane", "UK maker supplies: 3D print filament, hand tools, electronics kits", "maker"),
]


def consult(prompt, max_tokens=1600):
    """Run a single bounded OpenAI consult via the qsb_consult_external tool."""
    out = subprocess.run(
        ["python3", "tools/qsb_consult_external.py",
         "--provider", "openai", "--model", "gpt-4o-mini",
         "--max-tokens", str(max_tokens),
         "--reason", "shop catalog real-data research",
         "--prompt", prompt],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    return out.stdout


def parse_json_reply(text):
    """Extract the JSON object from the consult output."""
    import re
    # Strip the consult banner and find the JSON
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        # try to find a code-fenced JSON
        m2 = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
        if m2:
            try: return json.loads(m2.group(1))
            except: return None
        return None


def build_prompt(name, summary, theme):
    return (
        f"Reply with ONLY a JSON object (no narration, no markdown fence).\n"
        f"Schema:\n"
        f'  {{"items":[{{"name":"...","brand":"...","supplier":"...","supplier_cost_gbp":N.NN,'
        f'"list_price_gbp":N.NN,"description":"1-line factual","category":"..."}}, ...]}}\n'
        f"Build a UK retail catalog of 8 real items for a shop called '{name}'. "
        f"Niche: {summary}. Use REAL brand names available in the UK in 2024-2025 "
        f"(e.g. for {theme}: think of the top 3-4 brands a UK customer would actually buy). "
        f"Realistic UK retail price; supplier cost ~60% of retail. "
        f"Keep descriptions factual, no marketing fluff. "
        f"Output JSON only."
    )


def merge_into_catalog(floor_tag, items, summary):
    """Replace/augment the existing catalog file with researched items."""
    path = ROOT / f"data/registries/qsb_floor{floor_tag.lstrip('F')}_catalog.json"
    if not path.exists():
        print(f"  [{floor_tag}] catalog file missing — skipping")
        return False
    d = json.loads(path.read_text(encoding="utf-8"))
    sku_prefix = f"{floor_tag}-RR"
    new_items = []
    for i, it in enumerate(items[:10], 1):
        new_items.append({
            "sku": f"{sku_prefix}-{i:03d}",
            "name": it.get("name") or "—",
            "brand": it.get("brand") or "",
            "category": it.get("category") or theme_from_dept(it),
            "supplier": it.get("supplier") or it.get("brand") or "UK direct",
            "supplier_cost_gbp": float(it.get("supplier_cost_gbp") or 0),
            "list_price_gbp": float(it.get("list_price_gbp") or 0),
            "gross_margin_gbp": round(float(it.get("list_price_gbp") or 0) -
                                       float(it.get("supplier_cost_gbp") or 0), 2),
            "gross_margin_pct": (
                round((1 - float(it.get("supplier_cost_gbp") or 0) /
                       max(float(it.get("list_price_gbp") or 1), 1e-9)) * 100, 1)
                if it.get("list_price_gbp") else 0
            ),
            "stock_model": "stock",
            "lead_time_days": 2,
            "description": it.get("description") or "",
            "image_url": f"https://loremflickr.com/600/600/{(it.get('category') or summary.split(',')[0].strip()).replace(' ', ',')}?lock={hash(it.get('name','x'))%10000}",
        })
    d["items"] = new_items
    d["research_provenance"] = (
        "OpenAI gpt-4o-mini consult 2026-06-13 — real UK brand names + "
        "realistic retail/wholesale price bands. Pattern matches F149."
    )
    d["generated_ts"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return True


def theme_from_dept(it):
    return (it.get("category") or "general").lower().replace(" ", "_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="single floor tag e.g. F61")
    args = ap.parse_args()
    print(f"[research] starting at {datetime.now(timezone.utc).isoformat()}")
    rebuilt = []
    failed = []
    for tag, name, summary, theme in SHOPS:
        if args.only and args.only != tag: continue
        prompt = build_prompt(name, summary, theme)
        reply = consult(prompt, max_tokens=1400)
        data = parse_json_reply(reply)
        if not data or "items" not in data:
            print(f"  [{tag}] {name}: parse failed; first 200 chars: {reply[:200].replace(chr(10),' ')}")
            failed.append(tag)
            continue
        items = data["items"]
        ok = merge_into_catalog(tag, items, summary)
        if ok:
            print(f"  [{tag}] {name}: {len(items)} real items written")
            rebuilt.append(tag)
        else:
            failed.append(tag)
    print(f"\n=== SUMMARY ===")
    print(f"  rebuilt: {len(rebuilt)}  {rebuilt}")
    print(f"  failed:  {len(failed)}   {failed}")


if __name__ == "__main__":
    main()
