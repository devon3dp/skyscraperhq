#!/usr/bin/env python3
"""qsb_skeleton_floor_cards.py — generate minimal floor_card.json for any
floor that has a floor_manifest.json but no floor_card.json.

Per Open Day prep 2026-06-17 (Wren + DeepSeek + Forge signed-off).

  python3 tools/qsb_skeleton_floor_cards.py            # write missing cards
  python3 tools/qsb_skeleton_floor_cards.py --dry-run  # show what would be written
  python3 tools/qsb_skeleton_floor_cards.py --force    # overwrite existing skeleton cards
"""

from __future__ import annotations
import argparse, json, os
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
FLOORS = ROOT / "floors"

ZONE_BY_FLOOR_RANGE = [
    (0, 9,    "ZONE A · GROUND"),
    (10, 35,  "ZONE B · OPERATIONS"),
    (36, 55,  "ZONE C · CRAFT + COMMERCE"),
    (56, 99,  "ZONE D · COMMERCE WING"),
    (100, 149, "ZONE E · MID-RISE"),
    (150, 168, "ZONE F · CROWN"),
    (169, 169, "ZONE G · TOP"),
]


def zone_for(n: int) -> str:
    for lo, hi, z in ZONE_BY_FLOOR_RANGE:
        if lo <= n <= hi:
            return z
    return "ZONE TBD"


def floor_number_from_dirname(name: str) -> int | None:
    if not name.startswith("floor_"):
        return None
    try:
        return int(name.split("_")[1])
    except Exception:
        return None


def build_card_from_manifest(n: int, dirname: str, manifest: dict) -> dict:
    name = manifest.get("floor_name") or dirname.replace("_", " ").title()
    dept = (manifest.get("department")
            or manifest.get("floor_kind")
            or manifest.get("theme")
            or name)
    blurb = (manifest.get("tagline")
             or manifest.get("description")
             or f"{name} — a floor in the QSB Tower. Skeleton card auto-generated; full fit-out pending.")
    return {
        "floor_id": f"floor_{n:02d}",
        "floor_number": n,
        "floor_name": name,
        "department": dept,
        "zone": zone_for(n),
        "archetype": (manifest.get("archetype")
                       or manifest.get("floor_kind")
                       or "generic"),
        "staff_lead": manifest.get("staff_lead")
                       or manifest.get("designed_by", "TBD"),
        "tour_blurb": blurb[:600],
        "visitor_open": False,
        "advisory_only": True,
        "execution_mode": "PREVIEW_ONLY",
        "skeleton": True,
        "skeleton_source": "floor_manifest.json",
        "skeleton_generated_ts": "2026-06-17",
        "live_signals": {
            "theme": manifest.get("theme"),
            "categories": manifest.get("categories"),
            "palette": manifest.get("colour_palette") or manifest.get("palette"),
            "tagline": manifest.get("tagline"),
        },
        "gate_posture": {
            "advisory_only": True,
            "execution_allowed": False,
            "live_payments_enabled": False,
        },
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="overwrite even existing skeleton cards")
    p.add_argument("--limit", type=int, default=200)
    a = p.parse_args()

    written, skipped, fallback = 0, 0, 0
    for dirname in sorted(os.listdir(FLOORS)):
        d = FLOORS / dirname
        if not d.is_dir(): continue
        n = floor_number_from_dirname(dirname)
        if n is None: continue
        card_path = d / "floor_card.json"
        if card_path.exists() and card_path.stat().st_size > 200 and not a.force:
            skipped += 1; continue
        manifest_path = d / "floor_manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
            except Exception:
                manifest = {}
        if not manifest:
            # Fallback: derive name from dirname
            slug = "_".join(dirname.split("_")[2:]) or dirname
            manifest = {"floor_name": slug.replace("_", " ").title()}
            fallback += 1
        card = build_card_from_manifest(n, dirname, manifest)
        if a.dry_run:
            print(f"  would write F{n:3d}: {card['floor_name'][:48]}")
        else:
            card_path.write_text(json.dumps(card, indent=2))
            written += 1
        if written + (skipped if a.dry_run else 0) >= a.limit:
            break

    print(f"\n  written={written}  skipped_existing={skipped}  manifest_fallback={fallback}")


if __name__ == "__main__":
    main()
