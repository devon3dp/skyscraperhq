#!/usr/bin/env python3
"""qsb_f149_seed_extend.py — extend F149 Greenline Seed Centre catalog
with N additional real-strain SKUs in the same schema past-Wren used
2026-06-13. ADDS items, doesn't replace.

Schema match: {sku, name, breeder, strain_type, genetics_note, category,
department, supplier, flowering_weeks, thc_pct, list_price_usd}

  python3 tools/qsb_f149_seed_extend.py --n 10
"""

from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
CAT  = ROOT / "data/registries/qsb_floor149_seed_centre_catalog.json"


def consult(n: int, existing_names: list[str]) -> dict:
    avoid = "; ".join(existing_names[:30])
    prompt = (
        f"You are stocking the F149 Greenline Seed Centre + Horticulture "
        f"floor in a virtual skyscraper. Produce a JSON array of EXACTLY "
        f"{n} REAL cannabis seed SKUs that ARE NOT in this avoid-list: "
        f"{avoid}. Each item: {{sku (G-NNN format), name (real strain), "
        f"breeder (real breeder: Barneys Farm / Royal Queen Seeds / "
        f"Sensi Seeds / Seedsman / Dutch Passion / Humboldt / DNA Genetics "
        f"/ Greenhouse Seed Co / Dinafem / Paradise / Mr Nice / Serious "
        f"/ Big Buddha / Cali Connection / TGA Subcool), strain_type "
        f"(feminized / autoflower / regular / CBD), genetics_note "
        f"(parent cross in plain text), category (Feminized / Autoflower / "
        f"Regular / CBD / Mix Pack), department (one of: bestsellers / "
        f"sativa / indica / hybrid / cbd / autoflower / classics / "
        f"new_arrivals), supplier (one of: Barneys Farm / Royal Queen "
        f"Seeds / Seedsman / Sensi Seeds / Humboldt Seed Org), "
        f"flowering_weeks (number 6-12), thc_pct (number 0-30), "
        f"list_price_usd (number .99). NO MARKDOWN, just the JSON array."
    )
    r = subprocess.run(
        ["python3", str(ROOT / "tools/qsb_consult_external.py"),
         "--provider", "openai", "--model", "gpt-4o-mini",
         "--reason", "f149_seed_extend",
         "--max-tokens", "1800", "--prompt", prompt],
        capture_output=True, text=True, timeout=90, cwd=str(ROOT))
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or "")[-200:]}
    out = r.stdout
    parts = out.split("━" * 56)
    body = parts[2].strip() if len(parts) >= 4 else out.strip()
    if body.startswith("```"):
        body = body.split("```", 2)[1]
        if body.startswith("json\n"): body = body[5:]
        body = body.rsplit("```", 1)[0].strip()
    try:
        items = json.loads(body)
        return {"ok": True, "items": items}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "raw": body[:300]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=10)
    a = p.parse_args()
    d = json.loads(CAT.read_text())
    existing = d.get("items") or d.get("catalog") or []
    existing_names = [it.get("name", "") for it in existing]
    print(f"  existing: {len(existing)} items")
    c = consult(a.n, existing_names)
    if not c.get("ok"):
        print(f"  FAIL: {c.get('error')}"); return 1
    fresh = c["items"]
    # Stamp the additions
    extended = list(existing) + list(fresh)
    d["items"] = extended
    d["item_count"] = len(extended)
    d.setdefault("extended_at", []).append(
        {"ts": "2026-06-17", "added": len(fresh),
         "method": "openai_gpt-4o-mini_consult"})
    CAT.write_text(json.dumps(d, indent=2))
    print(f"  added: {len(fresh)} → total: {len(extended)}")
    return 0


if __name__ == "__main__":
    main()
