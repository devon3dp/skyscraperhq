#!/usr/bin/env python3
"""qsb_shop_catalog_rebuild.py — rebuild the 15 shop catalogs with real
SKU data via bounded OpenAI consult (same pattern past-Wren used for
F149 Greenline Seed Centre 2026-06-13).

For each shop in web/shops/:
  - Read floors/floor_NN_<slug>/floor_manifest.json for theme/categories/palette
  - Call OpenAI with a tight prompt asking for 8-12 realistic SKUs
  - Parse JSON reply
  - Write data/registries/qsb_floorNN_catalog.json
  - Also write web/shops/<slug>/products.json for the Netlify deploy

Cost cap: refuses to run if today's OpenAI spend would exceed $1.00.

  python3 tools/qsb_shop_catalog_rebuild.py --shop little-robin   # one shop
  python3 tools/qsb_shop_catalog_rebuild.py --all                  # all 15
  python3 tools/qsb_shop_catalog_rebuild.py --all --dry-run        # show plan only
"""

from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SHOPS_DIR = ROOT / "web/shops"

SHOP_TO_FLOOR = {
    "lumiere-beauty": 61,    "pinwheel-toys": 62,    "pawsworth-pets": 63,
    "hearthstone-kitchen": 64, "vector-tech": 65,
    "trailhead-outdoor": 154, "stretch-fitness": 155, "quilltree-office": 156,
    "voyage-and-co": 157, "greenhouse-lane": 158, "little-robin": 159,
    "inkwell-and-co": 160, "twilight-wellness": 161, "living-light-eco": 162,
    "maker-lane": 163,
}


def manifest_for(slug: str) -> dict:
    floor_n = SHOP_TO_FLOOR.get(slug)
    if floor_n is None:
        return {}
    for d in (ROOT / "floors").iterdir():
        if d.is_dir() and d.name.startswith(f"floor_{floor_n}_"):
            mp = d / "floor_manifest.json"
            if mp.exists():
                try: return json.loads(mp.read_text())
                except Exception: return {}
    return {}


def consult_openai(slug: str, manifest: dict, n_skus: int = 10) -> dict:
    theme = manifest.get("theme") or slug.replace("-", " ")
    cats = manifest.get("categories") or []
    palette = manifest.get("colour_palette") or "neutral"
    tagline = manifest.get("tagline") or ""
    margin = manifest.get("target_margin_pct", 60)
    prompt = (
        f"You are stocking the {slug} shop on Floor {SHOP_TO_FLOOR.get(slug)} "
        f"of a virtual skyscraper. Theme: {theme}. "
        f"Categories: {', '.join(cats) if cats else '(open)'}. "
        f"Palette: {palette}. Tagline: {tagline}. "
        f"Target margin: {margin}%. Dropship fulfilment. "
        f"\n\nProduce a JSON array of EXACTLY {n_skus} realistic SKUs. Each "
        f"object: {{name, blurb (1 sentence), category, list_price_usd "
        f"(number, round to .99), supplier_keyword (string for searching "
        f"AliExpress / Spocket later)}}. NO MARKDOWN, NO PROSE, JUST THE "
        f"JSON ARRAY. Real brands or realistic-sounding fictional brands "
        f"are both fine. Mix price points across the {n_skus}."
    )
    tool = ROOT / "tools/qsb_consult_external.py"
    r = subprocess.run(
        ["python3", str(tool), "--provider", "openai",
         "--model", "gpt-4o-mini", "--reason", f"shop_rebuild_{slug}",
         "--max-tokens", "1400", "--prompt", prompt],
        capture_output=True, text=True, timeout=90, cwd=str(ROOT))
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or "")[-300:]}
    out = r.stdout
    parts = out.split("━" * 56)
    body = parts[2].strip() if len(parts) >= 4 else out.strip()
    # Strip a possible ```json fence
    body = body.strip()
    if body.startswith("```"):
        body = body.split("```", 2)[1]
        if body.startswith("json\n"):
            body = body[5:]
        body = body.rsplit("```", 1)[0].strip()
    try:
        items = json.loads(body)
        if not isinstance(items, list):
            return {"ok": False, "error": "not a list", "raw": body[:300]}
        return {"ok": True, "items": items, "raw_len": len(body)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "raw": body[:300]}


def write_catalog(slug: str, items: list) -> dict:
    floor_n = SHOP_TO_FLOOR[slug]
    reg_path = ROOT / "data/registries" / f"qsb_floor{floor_n}_catalog.json"
    payload = {
        "ok": True, "shop_slug": slug,
        "floor_number": floor_n,
        "items": items, "item_count": len(items),
        "rebuild_method": "openai_consult_gpt-4o-mini_2026-06-17",
        "advisory_only": True,
    }
    reg_path.write_text(json.dumps(payload, indent=2))
    # Also write web/shops/<slug>/products.json for the Netlify deploy
    products_path = SHOPS_DIR / slug / "products.json"
    products_path.parent.mkdir(parents=True, exist_ok=True)
    products_path.write_text(json.dumps({"items": items}, indent=2))
    return {"registry": str(reg_path), "products": str(products_path)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--shop", default=None)
    p.add_argument("--all", action="store_true")
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    shops = ([a.shop] if a.shop else
             list(SHOP_TO_FLOOR.keys()) if a.all else [])
    if not shops:
        print("usage: --shop <slug>  OR  --all")
        return 1
    results = []
    for slug in shops:
        manifest = manifest_for(slug)
        print(f"  {slug:<22s} → F{SHOP_TO_FLOOR[slug]}  theme={manifest.get('theme','?')[:40]}")
        if a.dry_run:
            results.append({"slug": slug, "dry_run": True}); continue
        c = consult_openai(slug, manifest, a.n)
        if not c.get("ok"):
            print(f"    FAIL: {c.get('error','?')[:160]}")
            results.append({"slug": slug, "ok": False,
                             "error": c.get("error")}); continue
        paths = write_catalog(slug, c["items"])
        print(f"    OK: {len(c['items'])} items → {paths['registry'].rsplit('/',1)[-1]}")
        results.append({"slug": slug, "ok": True, "count": len(c["items"])})
    ok_n = sum(1 for r in results if r.get("ok"))
    print(f"\n  TOTAL: {ok_n}/{len(results)} OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
