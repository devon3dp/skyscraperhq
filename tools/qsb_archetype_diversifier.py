#!/usr/bin/env python3
"""qsb_archetype_diversifier.py — assigns rich archetypes to floors currently
stuck on the generic template, based on floor_name keyword patterns.

Each archetype gets a distinct palette + furniture set so the Godot interior
renders differently per floor.
"""
from __future__ import annotations
import json, re, pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
FLOORS = ROOT / "floors"
F47 = ROOT / "data" / "registries" / "qsb_f47_team_records.jsonl"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

# Keyword → (archetype, palette, signature_furniture, mood)
ARCHETYPES = [
    # Tech / Engineering
    (r"coding|engineer|architect|developer|build|softw", {
        "archetype": "dev_lab",
        "palette": ["#1e2740", "#2a4d80", "#4ade80"],
        "signature": "Standing desks, dual monitors, whiteboard wall, debug pit",
        "mood": "focused",
    }),
    (r"data\s*centre|data\s*center|server|rack", {
        "archetype": "data_centre",
        "palette": ["#0c1830", "#1c3a60", "#5fa8ff"],
        "signature": "Server racks in rows, blue LED grid, raised floor",
        "mood": "humming",
    }),
    (r"hardware|gpu|cpu|silicon|chip", {
        "archetype": "hardware_bench",
        "palette": ["#2a2030", "#704080", "#ffd359"],
        "signature": "Workbench with soldering, oscilloscopes, chip trays",
        "mood": "precise",
    }),
    # Security / Risk
    (r"security|cyber|risk|defence|guardian", {
        "archetype": "security_ops",
        "palette": ["#2a1010", "#7a2020", "#ff5555"],
        "signature": "Wall of monitors, intrusion log feed, sealed cage",
        "mood": "vigilant",
    }),
    # Communications / Comms
    (r"email|mail|outlook|comm[s]?|messag|postal|telegraph", {
        "archetype": "comms_centre",
        "palette": ["#1a2840", "#3a6090", "#c780ff"],
        "signature": "Mail sorting bays, console with inboxes, ticker tape",
        "mood": "buzzing",
    }),
    # Professional services
    (r"legal|law|advoc|barrist", {
        "archetype": "law_chambers",
        "palette": ["#252012", "#5a4818", "#d4a040"],
        "signature": "Oak shelves, leather-bound books, partner desk, gavel",
        "mood": "formal",
    }),
    (r"tax|account|finance|treasur|bank|ledger", {
        "archetype": "accounting_floor",
        "palette": ["#1a2a18", "#3a5028", "#80c060"],
        "signature": "Long ledger desks, calc machines, green-shade lamps",
        "mood": "diligent",
    }),
    (r"hr|human\s*res|personnel|recruit|workforce", {
        "archetype": "hr_office",
        "palette": ["#2a2018", "#604030", "#ffa050"],
        "signature": "Interview booths, name badge wall, hiring board",
        "mood": "welcoming",
    }),
    # Knowledge / Library / Press
    (r"library|archive|knowledge|memory", {
        "archetype": "library",
        "palette": ["#181410", "#5a4818", "#d8b878"],
        "signature": "Floor-to-ceiling shelves, reading carrels, card catalogue",
        "mood": "studious",
    }),
    (r"press|publish|edit|news|journal|chronicl", {
        "archetype": "press_room",
        "palette": ["#181818", "#404040", "#e8e8e8"],
        "signature": "Newsroom desks, printing press, headline wall",
        "mood": "deadline-driven",
    }),
    # Ops / Testing / QA
    (r"operations|operate|control|command|dispatch", {
        "archetype": "ops_hub",
        "palette": ["#102030", "#3060a0", "#80b2ff"],
        "signature": "Curved console arc, status walls, ops director's chair",
        "mood": "command-and-control",
    }),
    (r"test|qa|quality\s*assur|verification|validat", {
        "archetype": "qa_lab",
        "palette": ["#10282a", "#306060", "#66f2b2"],
        "signature": "Test rigs, pass/fail boards, scenario whiteboards",
        "mood": "methodical",
    }),
    # Support / Help
    (r"help|support|service\s*desk|desk", {
        "archetype": "support_desk",
        "palette": ["#1e1c1a", "#4a4038", "#ffd359"],
        "signature": "Tier-1 desk row, queue display, FAQ shelf, coffee station",
        "mood": "ready",
    }),
    # Research / Lab
    (r"research|lab\b|laborat|experiment|study", {
        "archetype": "research_lab",
        "palette": ["#1c1830", "#3c3060", "#a080ff"],
        "signature": "Workbench grid, sample fridges, mass spectrometer",
        "mood": "curious",
    }),
    # Marketing / Brand
    (r"marketing|brand|advert|promot|outreach", {
        "archetype": "creative_studio",
        "palette": ["#2a1a30", "#603060", "#ff80c0"],
        "signature": "Pinboards, sample products, brainstorm pit",
        "mood": "energetic",
    }),
    # Civic / Hall / Reception
    (r"reception|lobby|hall|civic|public|atrium", {
        "archetype": "civic",
        "palette": ["#1a2030", "#3a5080", "#a0c0ff"],
        "signature": "Marble floor, columns, reception desk, seating arc",
        "mood": "open",
    }),
    # Comms / Speech / Audio
    (r"speech|audio|media|broadcast|voice|sound", {
        "archetype": "media_studio",
        "palette": ["#2a1818", "#603030", "#ff6060"],
        "signature": "Sound-treated booth, mixer console, microphone array",
        "mood": "live-on-air",
    }),
    # Training / Education
    (r"training|academy|classroom|cohort|school|institute", {
        "archetype": "classroom",
        "palette": ["#181c30", "#3850a0", "#80b0ff"],
        "signature": "Lecture rows, instructor podium, smart board, lab benches",
        "mood": "learning",
    }),
    # Logistics / Shipping
    (r"shipping|logistic|warehouse|fulfilment|fulfillment|delivery", {
        "archetype": "logistics_bay",
        "palette": ["#2a2418", "#604018", "#ffb050"],
        "signature": "Conveyor belt, pallet rack, packing stations, dock door",
        "mood": "moving",
    }),
]

DEFAULT_GENERIC = {
    "archetype": "ops_floor",
    "palette": ["#1a1e2a", "#3a4050", "#6a90c0"],
    "signature": "Standard tower office layout — desks, meeting nook, kitchenette",
    "mood": "professional",
}


def assign_archetype(floor_name: str) -> dict:
    fn = (floor_name or "").lower()
    for pattern, spec in ARCHETYPES:
        if re.search(pattern, fn):
            return spec
    return DEFAULT_GENERIC


def main():
    upgraded = 0
    skipped = 0
    keep = 0
    by_arche = {}
    for d in sorted(FLOORS.iterdir()):
        if not d.is_dir() or not d.name.startswith("floor_"): continue
        m = d / "floor_manifest.json"
        if not m.exists(): continue
        try: data = json.loads(m.read_text())
        except: continue
        brief = data.get("interior_brief") or {}
        old_arche = brief.get("archetype") or "none"
        if old_arche in ("generic", "none"):
            spec = assign_archetype(data.get("floor_name",""))
            brief["archetype"] = spec["archetype"]
            brief["palette"] = spec["palette"]
            brief["signature"] = spec["signature"]
            brief["mood"] = spec["mood"]
            brief["diversified_ts"] = NOW
            brief["diversified_by"] = "qsb_archetype_diversifier_v1"
            data["interior_brief"] = brief
            m.write_text(json.dumps(data, indent=2))
            upgraded += 1
            by_arche[spec["archetype"]] = by_arche.get(spec["archetype"], 0) + 1
        else:
            keep += 1
            by_arche[old_arche] = by_arche.get(old_arche, 0) + 1

    print(f"✓ Diversified {upgraded} generic floors")
    print(f"  Kept {keep} hand-crafted archetypes")
    print()
    print("Archetype distribution after sweep:")
    for a, c in sorted(by_arche.items(), key=lambda x: -x[1]):
        print(f"  {a:25}  {c:4}")

    # F47 stamp
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": NOW,
            "kind": "floors_archetype_diversified_v1",
            "role": "wren",
            "team_actor": "F66 Architects + F17 Graphics",
            "summary": f"Floor archetype diversifier: {upgraded} floors lifted from generic to distinct archetypes (dev_lab, data_centre, security_ops, library, press_room, comms_centre, etc.). Each archetype carries palette + signature furniture + mood. Godot floor interior will now render visually distinct per floor.",
            "advisory_only": False,
        }) + "\n")


if __name__ == "__main__":
    main()
