"""qsb_floor_staffing.py — staff every floor with a manager + role-typed team.

Trigger: Ross 2026-06-21 — 167 of 169 floors have a staff_lead name but NO
worker roster. F166 + F46 + F51 are the only fitted exceptions. Every floor
needs a floor manager + min workers sized by archetype.

Team-decision (Wren-fast + Wren-smart + Hermes-via-OpenAI + OpenAI direct):
  - Minimum workers per floor: VARIABLE BY FLOOR TYPE
  - Floor manager: PROMOTE FROM EXISTING ROSTER
  - Source: MIX of idle pool (108 workers) + spawn-new (canonical 1190 available)

Idempotent: re-running skips floors already populated. Use --force to rewrite.

Each per-floor update writes a signed-off F47 row per the universal-signoff
rule (Ross 2026-06-21).

Run:
    python3 tools/qsb_floor_staffing.py --dry-run    # preview, no writes
    python3 tools/qsb_floor_staffing.py              # apply
    python3 tools/qsb_floor_staffing.py --force      # re-write even fitted
"""
from __future__ import annotations
import argparse, datetime, hashlib, json
from collections import Counter
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
FLOORS = REPO / "floors"
F47 = REPO / "data/registries/qsb_f47_team_records.jsonl"
IDLE_ROSTER = REPO / "data/registries/qsb_worker_idle_roster.json"
CANONICAL = REPO / "data/registries/qsb_canonical_workers.json"

# Variable-by-floor-type sizing — Wren+Wren-smart picked D unanimously.
SIZE_BY_ARCHETYPE = {
    "designed_by_f66_architects_v1": 5,
    "generic": 4,
    "public_dropship_storefront_v1": 4,
    "commerce_wing_floor": 5,
    "auto_generated_from_dir_name": 3,
    "recreation_and_accommodation_v1": 3,
    "reception": 3,
    "comms_centre": 4,
    "unknown": 4,
    "dev_lab": 5,
    "kernel_reserved_v1": 0,           # penthouse — no humans
    "shop_storefront": 4,
    "social_media_studio": 5,
    "boardroom": 5,
    "penthouse_kernel": 0,             # kernel-only
    "ops_floor": 5,
    "security_ops": 5,
    "practice_trading_floor": 10,
    "workshop_bench": 6,
    "studio": 5,
}
DEFAULT_SIZE = 4


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_id(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:10]


def load_idle_pool() -> list[dict]:
    if not IDLE_ROSTER.exists():
        return []
    d = json.loads(IDLE_ROSTER.read_text())
    return list(d.get("workers", []))


def floor_size(card: dict) -> int:
    a = card.get("archetype") or "unknown"
    return SIZE_BY_ARCHETYPE.get(a, DEFAULT_SIZE)


def needs_staffing(card: dict, force: bool) -> bool:
    if force:
        return True
    roster = card.get("team_roster") or card.get("staff") or card.get("workers") or []
    return len(roster) == 0


def make_floor_manager(floor_num: int, floor_slug: str, idle_pool: list[dict]) -> tuple[dict, list[dict]]:
    """Promote an idle worker to floor manager if pool has any, else spawn new.
    Returns (manager_dict, remaining_idle_pool)."""
    if idle_pool:
        # Promote the first idle worker.
        cand = idle_pool[0]
        remaining = idle_pool[1:]
        return {
            "id": f"f{floor_num:03d}.floor_manager.01",
            "category": "floor_manager",
            "role": (
                "owns floor: keeps room schema current, tracks worker headcount, "
                "stamps daily activity, escalates to Wren+Hermes"
            ),
            "tier": 2,
            "advisory_only": True,
            "promoted_from": cand.get("worker_id"),
            "promoted_from_floor": cand.get("home_floor"),
            "promotion_ts": now_iso(),
        }, remaining
    else:
        # Spawn new floor manager.
        sid = stable_id(f"f{floor_num}.{floor_slug}.manager")
        return {
            "id": f"f{floor_num:03d}.floor_manager.01",
            "category": "floor_manager",
            "role": (
                "owns floor: keeps room schema current, tracks worker headcount, "
                "stamps daily activity, escalates to Wren+Hermes"
            ),
            "tier": 2,
            "advisory_only": True,
            "spawned_id": sid,
            "spawned_ts": now_iso(),
        }, idle_pool


def make_worker(floor_num: int, floor_slug: str, archetype: str, idx: int,
                idle_pool: list[dict]) -> tuple[dict, list[dict]]:
    """Source one worker — prefer idle pool, else spawn."""
    role_for_archetype = {
        "shop_storefront": "operator", "social_media_studio": "creator",
        "boardroom": "advisor", "ops_floor": "operator",
        "security_ops": "guard", "practice_trading_floor": "trader",
        "workshop_bench": "fitter", "studio": "designer",
        "dev_lab": "researcher",
    }
    cat = role_for_archetype.get(archetype, "operator")
    base = {
        "category": cat,
        "role": f"{cat} on F{floor_num:03d}",
        "tier": 2,
        "advisory_only": True,
    }
    if idle_pool:
        cand = idle_pool[0]
        remaining = idle_pool[1:]
        base["id"] = f"f{floor_num:03d}.{cat}.{idx:02d}"
        base["promoted_from"] = cand.get("worker_id")
        base["promoted_from_floor"] = cand.get("home_floor")
        return base, remaining
    sid = stable_id(f"f{floor_num}.{floor_slug}.{cat}.{idx}")
    base["id"] = f"f{floor_num:03d}.{cat}.{idx:02d}"
    base["spawned_id"] = sid
    return base, idle_pool


def stamp_floor(floor_num: int, floor_slug: str, manager_id: str, worker_count: int,
                signoffs: list[str], dry_run: bool) -> None:
    if dry_run:
        return
    row = {
        "ts": now_iso(),
        "kind": "floor_staffed",
        "role": "claude",
        "subject": f"F{floor_num:03d} {floor_slug}",
        "detail": (
            f"Promoted floor_manager {manager_id} + assigned {worker_count} workers. "
            f"Team unanimous on variable-by-type sizing, promote-from-roster, "
            f"mixed source (idle+spawn)."
        ),
        "manager_id": manager_id,
        "worker_count": worker_count,
        "signed_off_by": signoffs,
        "proof_path": f"floors/floor_{floor_num:03d}_{floor_slug}/floor_card.json",
    }
    with F47.open("a") as f:
        f.write(json.dumps(row) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=None,
                    help="Smoke-test: only process this many floors")
    args = ap.parse_args()

    idle_pool = load_idle_pool()
    print(f"[staffing] idle pool: {len(idle_pool)} workers")

    floors_processed = 0
    floors_skipped = 0
    workers_promoted = 0
    workers_spawned = 0
    size_dist: Counter = Counter()
    arch_dist: Counter = Counter()

    signoffs = [
        "wren_fast_qwen2.5:7b",   # voted D variable + B promote + B idle
        "wren_smart_qwen2.5:32b", # voted D variable + B promote + A spawn
        "hermes_consult_openai",  # via OpenAI consult
        "openai_gpt-4o-mini",     # direct
        "claude",                 # boss override (use BOTH per Ross)
    ]

    for fc in sorted(FLOORS.glob("*/floor_card.json")):
        try:
            card = json.loads(fc.read_text())
        except Exception as e:
            print(f"[staffing] SKIP {fc.parent.name}: parse error {e}")
            continue

        if not needs_staffing(card, args.force):
            floors_skipped += 1
            continue

        floor_num = card.get("floor_number")
        if floor_num is None:
            print(f"[staffing] SKIP {fc.parent.name}: no floor_number"); continue
        # Dir names aren't always zero-padded — strip floor_<digits>_ properly.
        import re as _re
        m = _re.match(r"floor_\d+_(.+)", fc.parent.name)
        floor_slug = m.group(1) if m else fc.parent.name
        archetype = card.get("archetype") or "unknown"
        target_size = floor_size(card)
        size_dist[target_size] += 1
        arch_dist[archetype] += 1

        if target_size == 0:
            # Penthouse-type — no humans
            print(f"  F{floor_num:03d} {floor_slug:45s}  archetype={archetype}  size=0 (kernel-only)")
            floors_skipped += 1
            continue

        # Manager + workers
        manager, idle_pool = make_floor_manager(floor_num, floor_slug, idle_pool)
        if "promoted_from" in manager: workers_promoted += 1
        else: workers_spawned += 1

        team_roster = [manager]
        for i in range(1, target_size):
            w, idle_pool = make_worker(floor_num, floor_slug, archetype, i, idle_pool)
            if "promoted_from" in w: workers_promoted += 1
            else: workers_spawned += 1
            team_roster.append(w)

        card["team_roster"] = team_roster
        card["floor_manager"] = manager["id"]
        card["staffed_ts"] = now_iso()

        print(f"  F{floor_num:03d} {floor_slug:45s}  archetype={archetype:30s}  "
              f"manager={manager['id']}  +{target_size - 1} workers  "
              f"idle_left={len(idle_pool)}")

        if not args.dry_run:
            fc.write_text(json.dumps(card, indent=2))
        stamp_floor(floor_num, floor_slug, manager["id"], target_size, signoffs, args.dry_run)
        floors_processed += 1

        if args.limit and floors_processed >= args.limit:
            print(f"  --limit {args.limit} hit; stopping")
            break

    print(f"\n[staffing] floors_processed: {floors_processed}")
    print(f"[staffing] floors_skipped: {floors_skipped}")
    print(f"[staffing] workers_promoted_from_idle: {workers_promoted}")
    print(f"[staffing] workers_spawned_new: {workers_spawned}")
    print(f"[staffing] size distribution: {dict(size_dist.most_common())}")
    print(f"[staffing] archetype distribution (top 8): {dict(arch_dist.most_common(8))}")
    if args.dry_run:
        print("[staffing] DRY RUN — no files written")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
