#!/usr/bin/env python3
"""qsb_f47_recruit_makeover_team.py — add builders/architects/designers/decorators/fitters to F47.

Ross 2026-06-13: "we need to get all resources, team members, certified workers,
builders, architects, graphic designers, decorators and fitters all on your floor
so we can get it fully operating correctly."

Spawns 5 new roles (29 workers total) into qsb_wren_team_roster.json under the
F47 advisory envelope. They write proposals to qsb_wren_team_outputs.jsonl, the
same way the existing F47 team does. No execution authority — Wren reviews and
queues for sign-off.
"""
from __future__ import annotations
import json, hashlib, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
ROSTER = ROOT / "data/registries/qsb_wren_team_roster.json"
F47_REC = ROOT / "data/registries/qsb_f47_team_records.jsonl"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


NEW_ROLES = [
    ("builder", 8,
        "drafts implementation patches for tower modules; cites file:line; "
        "stamps proposals to qsb_code_proposals.jsonl for Ross sign-off"),
    ("architect", 4,
        "designs floor systems, lift routing, registry shapes; writes ADR-style "
        "notes citing existing modules; never edits code directly"),
    ("graphic_designer", 6,
        "produces SVG palettes, color tokens, scene material specs; reviews "
        "screenshots; proposes visual changes via the proposal queue"),
    ("decorator", 5,
        "applies the F47 amber/violet/dark-glass palette to floor interiors; "
        "proposes CSS + Babylon material tweaks; never auto-applies"),
    ("fitter", 6,
        "wires endpoints to UI panels; runs smoke tests on /api/* after backend "
        "changes; produces wiring diagrams; flags broken routes"),
]


def build_workers(start_ordinal: int) -> list[dict]:
    out = []
    ordinal = start_ordinal
    for role, count, desc in NEW_ROLES:
        for i in range(1, count + 1):
            seed = f"{role}-{i}-2026-06-13".encode()
            short_hash = hashlib.sha256(seed).hexdigest()[:16]
            wid = f"f47.wren.makeover_2026_06_13.{role}.{i:02d}.{short_hash}"
            out.append({
                "worker_id": wid,
                "ordinal_in_team": ordinal,
                "floor": "F47",
                "floor_name": "Claude Embassy (Wren)",
                "role": role,
                "role_description": desc,
                "status": "employed",
                "certified_for_trading": False,
                "execution_authority": "advisory_only",
                "external_api_access": False,
                "spawned_ts": utcnow(),
                "spawned_by": "Wren (this session, 2026-06-13)",
                "helix_short_hash_at_spawn": "ff089b810b38",
                "team": "wren_team_v1",
                "daily_track": "f47_makeover",
                "daily_assignment": f"make F47 fully operational as joint Ross+Wren ops base",
                "delegation_date": "2026-06-13",
            })
            ordinal += 1
    return out


def main():
    d = json.load(ROSTER.open())
    existing = d.get("workers", [])
    start = max((w.get("ordinal_in_team", 0) for w in existing), default=0) + 1
    new_workers = build_workers(start)

    # update role_counts
    rc = d.setdefault("role_counts", {})
    for role, count, _ in NEW_ROLES:
        rc[role] = rc.get(role, 0) + count

    existing.extend(new_workers)
    d["workers"] = existing
    d["team_size"] = len(existing)
    d["generated_ts"] = utcnow()
    d.setdefault("makeover_log", []).append({
        "ts": utcnow(),
        "event": "f47_makeover_recruitment",
        "added_roles": [r for r, _, _ in NEW_ROLES],
        "added_count": sum(c for _, c, _ in NEW_ROLES),
        "new_team_size": d["team_size"],
        "reason": "Ross 2026-06-13: make F47 fully operational as joint ops base",
    })

    ROSTER.write_text(json.dumps(d, indent=2))

    # stamp F47
    rec = {
        "ts": utcnow(),
        "kind": "f47_makeover_recruitment",
        "floor": "F47",
        "operator": "Ross",
        "executed_by": "Wren",
        "added_roles": [{"role": r, "count": c} for r, c, _ in NEW_ROLES],
        "added_count": sum(c for _, c, _ in NEW_ROLES),
        "new_team_size": d["team_size"],
    }
    with F47_REC.open("a") as f:
        f.write(json.dumps(rec) + "\n")

    print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    main()
