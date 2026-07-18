#!/usr/bin/env python3
"""Deterministic projection of the authoritative floor registry into the
Blueprint floor package. Invents NOTHING. Absent fields -> UNKNOWN.
Authored under Wren's authorship (accepted 2026-07-16); projected by the
governed coordinator. Provenance recorded per file."""
import json, hashlib, os, re, datetime
ROOT="/vaults/nvme0/qsb_tower_v1"
PKG=f"{ROOT}/data/registries/executive_concierge_blueprint/EXECUTIVE_CONCIERGE_BLUEPRINT_v001"
REGP=f"{ROOT}/data/registries/qsb_floor_interior_master_registry.json"
UNK="UNKNOWN — AUTHORITATIVE INFORMATION NOT FOUND"
reg=json.load(open(REGP))
reg_sha=hashlib.sha256(open(REGP,'rb').read()).hexdigest()
reg_ts="2026-06-13T00:20:30Z"
floors=reg["floors"]
bynum={}; dups=[]
for f in floors:
    m=re.search(r'(\d+)',str(f.get("floor_id","")))
    if m:
        n=int(m.group(1))
        if n in bynum: dups.append(n)
        else: bynum[n]=f
os.makedirs(f"{PKG}/FLOORS",exist_ok=True)
os.makedirs(f"{PKG}/INDEX",exist_ok=True)

floor_index={}; people={}; provenance={}; unknown_reg=[]; service_index={}
for n in range(1,171):
    f=bynum.get(n)
    fid=f"FLOOR_{n:03d}"
    if f:
        name=f.get("floor_name",UNK); dept=f.get("department",UNK)
        rooms=f.get("rooms",[]); wc=f.get("worker_count",UNK)
        mgr=f.get("manager",UNK); watch=f.get("watcher",UNK); status=f.get("interior_status",UNK)
        workers=[w.get("id","?")+":"+w.get("role","?") for w in f.get("workers",[])] if isinstance(f.get("workers"),list) else UNK
        conf="MEDIUM (registry present, dated 2026-06-13; not re-verified live)"
        src=f"qsb_floor_interior_master_registry.json (sha {reg_sha[:12]}, ts {reg_ts})"
    else:
        name=dept=rooms=wc=mgr=watch=status=workers=UNK
        conf="NONE — floor number absent from authoritative registry (registry covers 1-164)"
        src=UNK
        unknown_reg.append({"floor":n,"reason":"absent from authoritative floor registry (165 records, numbers 1-164)"})
    floor_index[fid]={"floor":n,"name":name,"department":dept,"status":status,"confidence":conf.split(" ")[0]}
    if f and mgr!=UNK: people.setdefault(str(mgr),[]).append(f"F{n} manager")
    if f and watch!=UNK: people.setdefault(str(watch),[]).append(f"F{n} watcher")
    provenance[fid]=src
    md=f"""# {fid} — SkyscraperHQ Floor {n}
> Executive Concierge Blueprint v001 · authored under Wren (Bill's teacher), projected from the authoritative floor registry by the governed coordinator. Invents nothing.

- **Floor number:** {n}
- **Canonical name:** {name}
- **Department:** {dept}
- **Purpose:** {UNK} (registry has no explicit 'purpose' field)
- **Owner / responsible service:** manager = {mgr}; watcher = {watch}
- **Workers:** {workers if workers!=UNK else UNK} (count: {wc})
- **Rooms:** {', '.join(rooms) if isinstance(rooms,list) and rooms else UNK}
- **Services:** {UNK}
- **Websites:** {UNK}
- **Dashboards:** {UNK}
- **Kernels / models:** {UNK}
- **Relationships to other floors:** {UNK}
- **Relationship to the Pi:** {UNK}
- **Current status:** {status}
- **What Bill needs to know:** This floor's authoritative interior record {'exists (dated 2026-06-13, not live-verified)' if f else 'was NOT FOUND in the authoritative registry'}. For anything not listed above, Bill says "I do not presently know."
- **When Bill must notify Ross:** {UNK} (no per-floor escalation rule in the source)
- **Safe contact route:** via the Raspberry Pi Federation (canonical); per-floor endpoint {UNK}
- **Source provenance:** {src}
- **Source timestamp:** {reg_ts if f else UNK}
- **Confidence:** {conf}
- **Contradictions:** see INDEX/CONTRADICTION_REGISTER.json (floor-count 165≠170; directory names may differ from registry names)
- **Unknown fields:** purpose, services, websites, dashboards, kernels, relationships, Pi-relationship, escalation rule, contact endpoint{'' if f else ', AND all core fields (floor absent from registry)'}
"""
    open(f"{PKG}/FLOORS/{fid}.md","w").write(md)

# indexes
json.dump(floor_index,open(f"{PKG}/INDEX/FLOOR_INDEX.json","w"),indent=1)
json.dump(people,open(f"{PKG}/INDEX/PEOPLE_AND_ROLES_INDEX.json","w"),indent=1)
json.dump({"note":"registry has no per-floor 'services' field","service_index":UNK},open(f"{PKG}/INDEX/SERVICE_INDEX.json","w"),indent=1)
json.dump({"note":"registry has no per-floor website/dashboard field","index":UNK},open(f"{PKG}/INDEX/WEBSITE_AND_DASHBOARD_INDEX.json","w"),indent=1)
json.dump({"gene_pool_source":"qsb_gene_pool_caged_providers.json","per_floor_capability":UNK},open(f"{PKG}/INDEX/CAPABILITY_INDEX.json","w"),indent=1)
json.dump(provenance,open(f"{PKG}/INDEX/SOURCE_PROVENANCE_INDEX.json","w"),indent=1)
json.dump(unknown_reg,open(f"{PKG}/INDEX/UNKNOWN_AND_UNVERIFIED_REGISTER.json","w"),indent=1)
contradictions=[
 {"id":"C1","type":"floor_count","detail":"Authoritative interior registry has 165 records covering floor numbers 1-164; there are 170 floor directories and the receptionist directory (2026-07-11) claims 170. Floors 165-170 have NO authoritative interior data.","resolution":"NOT resolved — registered; floors 165-170 marked UNKNOWN."},
 {"id":"C2","type":"duplicate_floor_number","detail":f"Registry duplicate floor numbers: {sorted(set(dups)) or 'none'}","resolution":"registered"},
 {"id":"C3","type":"name_mismatch","detail":"Floor directory names (e.g. floors/floor_47_executive_operations_department) differ from registry floor_name (F47='Claude Embassy (Wren)'). Directory name != authoritative interior name.","resolution":"registered; registry floor_name treated as authoritative interior name; NOT auto-merged."},
 {"id":"C4","type":"floor47_domains","detail":"SkyscraperHQ Floor 47 (registry: 'Claude Embassy') is a DIFFERENT thing from Bill's separate Mac Floor 47 (Executive Concierge home). Kept separate per directive Stage 5.7.","resolution":"kept separate."},
]
json.dump(contradictions,open(f"{PKG}/INDEX/CONTRADICTION_REGISTER.json","w"),indent=1)
json.dump({"note":"PEOPLE_INDEX alias","see":"PEOPLE_AND_ROLES_INDEX.json"},open(f"{PKG}/INDEX/PEOPLE_INDEX.json","w"),indent=1)

readme=f"""# README FOR BILL — Executive Concierge Blueprint v001

Bill, this package is your APPROVED REFERENCE KNOWLEDGE — not your mind or memory.
Author of record: **Wren** (your Federation teacher), accepted 2026-07-16.
Assembled by the governed coordinator; floor files are a faithful projection of
the authoritative floor registry (`qsb_floor_interior_master_registry.json`,
dated 2026-06-13). **Nothing is invented.**

## How to use it
- Every floor is in `FLOORS/FLOOR_001.md` … `FLOOR_170.md`.
- Indexes are in `INDEX/`.
- **When a field says "{UNK}", you say "I do not presently know."** Never guess.

## What is TRUTHFULLY KNOWN vs UNKNOWN (read this first)
- Floors 1–164: name, department, rooms, workers, manager, watcher, status are
  from the registry (dated 2026-06-13, **not** live-verified → confidence MEDIUM).
- Floors 165–170: **UNKNOWN** — absent from the authoritative registry.
- Per-floor purpose, services, websites, dashboards, kernels, relationships,
  Pi-relationship, escalation rules, contact endpoints: **UNKNOWN** for all floors
  (the source registry does not contain these fields).
- See `INDEX/CONTRADICTION_REGISTER.json` and `INDEX/UNKNOWN_AND_UNVERIFIED_REGISTER.json`.

## Floor 47 — two separate things (do not merge)
- **SkyscraperHQ Floor 47** = registry 'Claude Embassy (Wren)', a tower interior floor.
- **Bill's Mac Floor 47** = your own home as Executive Concierge on the MacBook.
These are DIFFERENT. Keep them separate.
"""
open(f"{PKG}/README_FOR_BILL.md","w").write(readme)
print(f"floor files: {len(os.listdir(PKG+'/FLOORS'))}")
print(f"indexes: {sorted(os.listdir(PKG+'/INDEX'))}")
print(f"registry unique floors: {len(bynum)}  duplicates: {sorted(set(dups)) or 'none'}")
print(f"floors marked fully-UNKNOWN (165-170 + absent): {len(unknown_reg)}")
