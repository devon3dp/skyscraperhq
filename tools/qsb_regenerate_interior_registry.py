#!/usr/bin/env python3
"""qsb_regenerate_interior_registry.py — fill the interior registry to F165.

Ross 2026-06-12: "some floors I can't enter". Cause: the master interior
registry only has 55 entries (F01..F55). Every floor 56-165 fell through to a
generic placeholder. This tool reads floors.json + each floor's manifest and
generates real interior entries with rooms, worker counts, departments and
templates.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
FLOORS_FILE = ROOT / "data/registries/floors.json"
REGISTRY_FILE = ROOT / "data/registries/qsb_floor_interior_master_registry.json"
MANIFEST_GLOB = ROOT / "floors"


def load_existing():
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"ok": True, "kind": "qsb_floor_interior_master_registry_v2",
            "ts": "", "floors": []}


def floor_dirs():
    return {p.name: p for p in MANIFEST_GLOB.iterdir() if p.is_dir() and p.name.startswith("floor_")}


def department_for(canonical):
    s = (canonical or "").lower()
    if "trad" in s or "exchange" in s: return "trading"
    if "finan" in s or "account" in s: return "finance"
    if "shop" in s or "store" in s or "commerce" in s: return "commerce"
    if "music" in s or "studio" in s or "sound" in s: return "music"
    if "cinema" in s or "theatre" in s: return "entertainment"
    if "librar" in s or "book" in s: return "library"
    if "wellness" in s or "pharm" in s or "medical" in s or "fitness" in s: return "wellness"
    if "kitchen" in s or "restaur" in s or "café" in s or "cafe" in s: return "hospitality"
    if "research" in s or "lab" in s: return "research"
    if "security" in s or "vault" in s or "lock" in s: return "security"
    if "council" in s or "executive" in s or "command" in s: return "command"
    if "operation" in s or "ops" in s or "infrastructure" in s: return "operations"
    return "general"


def template_for(canonical, dept):
    if dept == "music":      return "MusicStudioInterior"
    if dept == "trading":    return "TradingFloorInterior"
    if dept == "library":    return "LibraryInterior"
    if dept == "commerce":   return "ShopfrontInterior"
    if dept == "wellness":   return "WellnessInterior"
    if dept == "hospitality":return "HospitalityInterior"
    if dept == "research":   return "LabInterior"
    if dept == "security":   return "SecureInterior"
    if dept == "entertainment":return "TheatreInterior"
    if dept == "command":    return "CouncilInterior"
    return "GenericFloorInterior"


def rooms_for(canonical, dept):
    s = (canonical or "").lower()
    if dept == "music":
        return ["Studio A", "Studio B", "Vocal Booth", "Mastering Suite",
                "Recital Hall", "Rehearsal Rooms", "Listening Pods",
                "Piano Hall", "Instrument Library"]
    if dept == "trading":
        return ["Pit", "Risk Desk", "Compliance Wall", "Quote Board", "Strategy Lab"]
    if dept == "library":
        return ["Stacks", "Reading Room", "Catalog", "Archive Vault", "Reference Desk"]
    if dept == "commerce":
        return ["Shop Floor", "Stock Room", "Till Counter", "Display Window", "Office"]
    if dept == "wellness":
        return ["Treatment Room", "Studio", "Quiet Room", "Reception", "Showers"]
    if dept == "hospitality":
        return ["Kitchen", "Prep Line", "Dining Floor", "Bar", "Cold Store"]
    if dept == "research":
        return ["Wet Lab", "Computation Bench", "Library Nook", "Server Closet", "Meeting Room"]
    if dept == "security":
        return ["Lock Room", "Watch Desk", "Cage", "Forensics Bay", "Comms"]
    if dept == "entertainment":
        return ["Auditorium", "Stage", "Projection Booth", "Lobby", "Green Room"]
    if dept == "command":
        return ["Council Chamber", "Briefing Room", "Maps Wall", "Ops Pit", "Secure Comms"]
    return ["Main Hall", "Operations", "Quiet Room", "Lobby", "Storage"]


def worker_count_for(canonical, dept):
    if dept in ("trading", "command"): return 28
    if dept in ("music", "research"):  return 22
    if dept in ("commerce", "hospitality"): return 18
    if dept in ("library", "wellness"): return 14
    if dept == "security": return 16
    return 12


def manager_for(canonical, dept):
    if dept == "music":   return "Studio Manager"
    if dept == "trading": return "Floor Manager"
    if dept == "library": return "Head Librarian"
    if dept == "command": return "Council Chair"
    return "Floor Manager"


def main():
    floors_data = json.loads(FLOORS_FILE.read_text(encoding="utf-8"))
    floor_dir_map = floor_dirs()
    existing = load_existing()
    existing_map = {f["floor_id"]: f for f in existing.get("floors", []) if "floor_id" in f}
    out = []
    new_count = updated_count = 0

    for f in floors_data:
        n = f.get("number")
        if n is None: continue
        floor_id = f"F{n:02d}"
        canonical = f.get("canonical_name") or f.get("department") or f.get("name") or f"Floor {n}"
        dept = department_for(canonical)
        template = template_for(canonical, dept)
        rooms = rooms_for(canonical, dept)
        wc = worker_count_for(canonical, dept)
        mgr = manager_for(canonical, dept)
        existing_entry = existing_map.get(floor_id, {})
        entry = {
            "floor_id": floor_id,
            "floor_name": canonical,
            "department": dept,
            "template": template,
            "rooms": rooms,
            "worker_count": existing_entry.get("worker_count", wc),
            "workers": existing_entry.get("workers", []),
            "manager": existing_entry.get("manager", mgr),
            "watcher": existing_entry.get("watcher", "OpenClaw Supervisor"),
            "openclaw_presence": existing_entry.get("openclaw_presence", n in (38, 41, 42, 43, 44, 153)),
            "safety_locks_visible": True,
            "interior_status": "implemented",
            "regenerated_ts": datetime.now(timezone.utc).isoformat(),
        }
        if floor_id in existing_map:
            updated_count += 1
        else:
            new_count += 1
        out.append(entry)

    payload = {
        "ok": True,
        "kind": "qsb_floor_interior_master_registry_v2",
        "phase": "QSB_TOWER_V1.5",
        "ts": datetime.now(timezone.utc).isoformat(),
        "floor_count": len(out),
        "templates_used": sorted(set(e["template"] for e in out)),
        "openclaw_present_count": sum(1 for e in out if e["openclaw_presence"]),
        "floors": out,
    }
    REGISTRY_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"interior registry → {REGISTRY_FILE.relative_to(ROOT)}")
    print(f"  total: {len(out)}  new: {new_count}  updated: {updated_count}")
    print(f"  templates: {len(payload['templates_used'])}")
    # Also write a mirror in the Godot project so its res:// reads pick it up
    godot_copy = Path("/home/ross/qsb_godot_native_cockpit/data/registries/qsb_floor_interior_master_registry.json")
    godot_copy.parent.mkdir(parents=True, exist_ok=True)
    godot_copy.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  godot mirror → {godot_copy}")


if __name__ == "__main__":
    main()
