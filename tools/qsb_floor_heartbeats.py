#!/usr/bin/env python3
"""
qsb_floor_heartbeats.py — ONE honest per-floor heartbeat generator for the QSB Tower.

For every floor that has a REAL backing (a real floors/*/floor_card.json with a real
team_roster and gate posture), this single process performs a GENUINE read-action:
it freshly re-reads that floor's own card, counts its real roster, reads its real
floor-manager, zone and gate posture, and (when present) folds in its real per-floor
state/tick registries. It then appends ONE heartbeat row to the shared append-only log

    data/registries/qsb_floor_heartbeats.jsonl

Each row carries the floor number, a fresh UTC ts, and the REAL freshly-read content
(roster_size, floor_manager, zone, advisory_only, execution_mode, card_mtime, and a
content digest of the card). Nothing is templated filler — every field traces to the
floor's own card on disk at heartbeat time.

The sibling index tool (qsb_floor_activity_index.py) reads this log per-floor: a floor
whose most-recent heartbeat row is < FRESH_S old is marked active:true with source
qsb_floor_heartbeats.jsonl, and the transit map then lights it and emits its own real
train (floor -> task_council). No map edits; the map is untouched.

HONESTY (R01 / Ross "NO SIMS"):
  - A floor gets a heartbeat ONLY if its card exists and is real (has a roster).
  - Kernel-reserved Penthouse floors (153, 168) are SKIPPED — they must stay dim
    (CLAUDE.md: kernel-free; no fabricated activity).
  - Curated live nodes (their own richer live signals already light them) are SKIPPED
    here so a weaker heartbeat train never overrides a real live one.
  - Floors with no real roster and no per-floor registry are SKIPPED (honestly dim).
  - Every reported value is freshly read from disk this tick. If a card can't be read,
    that floor is skipped (no row) — never invented.

Floors REPORT their own real state. They do NOT execute anything. No gates flipped.
"""
import json, os, sys, time, glob, hashlib, re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(REPO, "data", "registries")
FLOORS_DIR = os.path.join(REPO, "floors")
OUT = os.path.join(REG, "qsb_floor_heartbeats.jsonl")

ISO = "%Y-%m-%dT%H:%M:%SZ"

# FALLBACK-ONLY (2026-07-29 pivot): the PRIMARY signal that lights a floor is REAL WORKER
# TRAFFIC (tools/qsb_worker_activation_engine.py wakes each floor's real assigned workers,
# who post to per-floor qsb_floor_<n>_worker_activity.jsonl / the shared worker log). These
# card-read heartbeats exist ONLY for floors that have a genuine function but NO fresh
# assigned-worker traffic yet — so we never double-count and never shadow real workers.
WORKER_FRESH_S = 3600
SHARED_WORKER = os.path.join(REG, "qsb_floor_worker_activity.jsonl")

# Kernel-reserved Penthouse floors — MUST stay dim (CLAUDE.md). Never emit a heartbeat.
KERNEL_RESERVED = {153, 168}

# Curated live NAMED-HUB nodes: these are their own named stations on the transit map
# (gene pool, trading floors, council, town square, reception, bench, etc.) — NOT dim-able
# "floor" stations — and are already lit by their OWN richer real live signals in
# qsb_floor_activity_index.py. A floor-heartbeat train can't even originate from a named
# hub, so we skip them here. (Mirrors CURATED_FLOOR_NUM in the transit map.)
#
# NOTE: F49/F50/F51/F52/F53/F167/F169 ARE real dim-able floor stations. They are NOT in
# this skip set: they get a heartbeat too, so they light from their real card even when
# their richer curated/leadership signal (health snapshot / comms) goes stale. The index
# still lets the richer live signal WIN when it is fresh (priority order preserved).
CURATED_LIVE = {0, 10, 24, 40, 41, 42, 43, 44, 46, 47, 48, 74, 75, 77}


def iso(ts):
    return time.strftime(ISO, time.gmtime(ts))


def floors_with_fresh_worker_traffic():
    """Return the set of floor numbers that already have FRESH real worker traffic, so the
    fallback heartbeat can skip them (no double-counting). Reads the per-floor worker files
    and the shared worker log; honest — only rows with a real floor+parseable ts count."""
    import datetime
    now = time.time()
    live = set()
    paths = sorted(glob.glob(os.path.join(REG, "qsb_floor_*_worker_activity.jsonl")))
    if os.path.exists(SHARED_WORKER):
        paths.append(SHARED_WORKER)
    for path in paths:
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    fn = None
                    for fk in ("floor_id", "floor", "floor_num", "floor_number"):
                        v = obj.get(fk)
                        if isinstance(v, int):
                            fn = v; break
                        if isinstance(v, str):
                            m = re.match(r"^(?:floor[_\-]?|f)?(\d+)", v.strip(), re.I)
                            if m:
                                fn = int(m.group(1)); break
                    if fn is None:
                        continue
                    ts = obj.get("ts") or obj.get("timestamp") or obj.get("time")
                    if not isinstance(ts, str):
                        continue
                    try:
                        e = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        continue
                    if (now - e) < WORKER_FRESH_S:
                        live.add(fn)
        except Exception:
            continue
    return live


def card_paths():
    """Yield (floor_number:int, card_path) for every real floor card on disk."""
    for card in sorted(glob.glob(os.path.join(FLOORS_DIR, "*", "floor_card.json"))):
        try:
            with open(card) as f:
                d = json.load(f)
        except Exception:
            continue
        fn = d.get("floor_number")
        if isinstance(fn, int):
            yield fn, card, d


def per_floor_registry_digest(num):
    """Fold in a floor's own real per-floor state registries if they exist (freshly read).
    Returns (n_registries, freshest_mtime_iso_or_None). Read-only."""
    pats = [
        os.path.join(REG, f"qsb_f{num}_*.json*"),
        os.path.join(REG, f"qsb_floor{num}_*.json*"),
        os.path.join(REG, f"qsb_floor_{num}_*.json*"),
    ]
    hits = set()
    for p in pats:
        for h in glob.glob(p):
            bn = os.path.basename(h)
            if ".bak" in bn or "heartbeat" in bn or "PRE_REPAIR" in bn:
                continue
            hits.add(h)
    if not hits:
        return 0, None
    freshest = max(os.path.getmtime(h) for h in hits)
    return len(hits), iso(freshest)


def heartbeat_row(num, card_path, card):
    """Build one GENUINE heartbeat row from the floor's freshly-read card state.
    Every field is read from disk this tick — no templated filler."""
    roster = card.get("team_roster") or []
    # Count real roster categories (genuine composition of the floor, freshly read).
    cats = {}
    for m in roster:
        if isinstance(m, dict):
            c = m.get("category") or "unspecified"
            cats[c] = cats.get(c, 0) + 1
    gate = card.get("gate_posture") or {}
    n_reg, reg_ts = per_floor_registry_digest(num)
    # Content digest over the card bytes so the row is verifiably about THIS card state.
    try:
        with open(card_path, "rb") as f:
            raw = f.read()
        digest = hashlib.sha256(raw).hexdigest()[:12]
        card_mtime = iso(os.path.getmtime(card_path))
    except Exception:
        digest = None
        card_mtime = None
    return {
        "floor": num,
        "ts": iso(time.time()),
        "kind": "floor_heartbeat",
        "floor_name": card.get("floor_name"),
        "roster_size": len(roster),
        "roster_categories": cats,
        "floor_manager": card.get("floor_manager"),
        "zone": card.get("zone"),
        "advisory_only": card.get("advisory_only"),
        "execution_mode": card.get("execution_mode"),
        "gate_execution_allowed": gate.get("execution_allowed"),
        "per_floor_registries": n_reg,
        "per_floor_registry_fresh_ts": reg_ts,
        "card_mtime": card_mtime,
        "card_sha12": digest,
        "report": (
            f"F{num} {card.get('floor_name')}: {len(roster)} real roster "
            f"({', '.join(f'{k}x{v}' for k, v in sorted(cats.items())) or 'none'}); "
            f"mgr={card.get('floor_manager') or 'TBD'}; "
            f"advisory_only={card.get('advisory_only')}; "
            f"exec_allowed={gate.get('execution_allowed')}; "
            f"{n_reg} per-floor registries."
        ),
        "source": "floor_card.json (freshly read) — R01 real state, no sim",
    }


def main():
    worker_live = floors_with_fresh_worker_traffic()
    emitted = 0
    skipped_kernel = []
    skipped_curated = []
    skipped_no_backing = []
    skipped_worker_live = []
    rows = []
    for num, card_path, card in card_paths():
        if num in KERNEL_RESERVED:
            skipped_kernel.append(num)
            continue
        if num in CURATED_LIVE:
            skipped_curated.append(num)
            continue
        # PRIMARY signal present -> this floor already lights from REAL worker traffic.
        # Skip the fallback heartbeat so we never double-count or shadow real workers.
        if num in worker_live:
            skipped_worker_live.append(num)
            continue
        roster = card.get("team_roster") or []
        n_reg, _ = per_floor_registry_digest(num)
        # Real backing required: a real roster OR a real per-floor registry. Else stay dim.
        if not roster and n_reg == 0:
            skipped_no_backing.append(num)
            continue
        rows.append(heartbeat_row(num, card_path, card))
        emitted += 1

    # Append-only write (R01: never rewrite history).
    with open(OUT, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    print(f"[qsb_floor_heartbeats] appended {emitted} fallback floor heartbeats -> "
          f"{os.path.relpath(OUT, REPO)}")
    print(f"  skipped worker-live (PRIMARY real worker traffic): {len(skipped_worker_live)} "
          f"floors {sorted(skipped_worker_live)}")
    print(f"  skipped kernel-reserved (stay dim): {sorted(skipped_kernel)}")
    print(f"  skipped curated-live (own signal):  {sorted(skipped_curated)}")
    print(f"  skipped no-backing (honestly dim):  {sorted(skipped_no_backing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
