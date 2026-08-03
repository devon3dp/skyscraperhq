#!/usr/bin/env python3
"""
qsb_lift_traffic.py — Inter-zone information highways via the tower's REAL lifts.

CLAUDE.md: "Inter-floor communication travels through lifts. Lifts carry sealed
packets." This tool makes cross-building information flow VISIBLE as lift traffic:
whenever real information genuinely moves between two floors that share a real
lift, it emits ONE lift-traffic row along that real lift shaft.

HONESTY (R01): a lift-traffic event is emitted ONLY when a real, sourced info
movement is found in a real registry, AND a real lift exists whose `serves`
includes BOTH endpoint floors. Every row cites its `source` path. Nothing is
fabricated. If two floors have no real info exchange, no lift event. If no real
lift connects the two endpoints, no lift event (logged as skipped, not faked).

TOPOLOGY ONLY: this tool emits traffic *events* to a shared visualization feed.
It executes nothing, dispatches nothing, flips no gate, places no order. It only
reads real registries and APPENDS rows to the shared map traffic feed.

REAL INPUTS (info movements):
  1. Worker needs deliveries  — a floor's NEED routed up to governance (Wren, F46).
     source: data/registries/qsb_worker_needs_queue.json
             + qsb_worker_needs_delivery_cursor.json (only DELIVERED needs move).
     movement: reporting floor N  ->  Wren's floor (46).
  2. Worker chain reports      — a floor's chain report folded into the cycle that
     is delivered to Wren's inbox (delivered.wren_inbox / wren_msg_id present).
     source: data/registries/qsb_worker_chain_reports.jsonl
     movement: each reporting floor  ->  Wren's floor (46).
  3. Leadership comms          — real messages between leadership participants who
     sit on different floors (Wren F46, Bill F47; TP/Asa are boardroom CEOs -> F47).
     source: data/registries/leadership_comms/room.jsonl and dm/*.jsonl
     movement: sender's floor  ->  recipient's floor  (skipped if same floor).

REAL LIFTS: data/registries/qsb_floor_lift_lines.json (9 real lift shafts). For a
movement between floors a,b we pick the lift whose serves_num contains BOTH a and
b, honoring sealed-packet + allowed-zone metadata for the label. If several lifts
qualify, the most specific (fewest floors served) real, online lift wins — that is
the shaft the packet would actually travel.

OUTPUT (append-only, shared with siblings):
  data/registries/qsb_map_traffic_feed.jsonl
  {"ts","from":<floor#>,"to":<floor#>,"cat":"lift","label":<desc>,"real":true,
   "source":<path>, "lift_id":..., "lift":..., "sealed":bool, "zones":[...]}

RATE LIMIT / BOUND: at most --max rows per run (default 40). Own cursor at
data/registries/qsb_lift_traffic_cursor.json prevents re-emitting the same
movement twice. Idempotent across runs.

USAGE:
  python3 tools/qsb_lift_traffic.py            # emit new lift traffic, append feed
  python3 tools/qsb_lift_traffic.py --dry-run  # show what WOULD move, write nothing
  python3 tools/qsb_lift_traffic.py --max 20   # cap rows this run
"""
from __future__ import annotations
import argparse, json, sys, hashlib, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
COMMS = REG / "leadership_comms"

LIFT_LINES = REG / "qsb_floor_lift_lines.json"
NEEDS_QUEUE = REG / "qsb_worker_needs_queue.json"
NEEDS_CURSOR = REG / "qsb_worker_needs_delivery_cursor.json"
CHAIN_REPORTS = REG / "qsb_worker_chain_reports.jsonl"
ROOM = COMMS / "room.jsonl"
DM_DIR = COMMS / "dm"

FEED = REG / "qsb_map_traffic_feed.jsonl"          # SHARED, append-only
CURSOR = REG / "qsb_lift_traffic_cursor.json"      # OURS only

# Real leadership participant -> real floor (from CLAUDE.md memory: F46=Wren's,
# F47=Bill's/Boardroom; TP & Asa are boardroom CEOs -> Boardroom floor 47).
WREN_FLOOR = 46
PARTICIPANT_FLOOR = {
    "wren": 46,
    "bill": 47,
    "tp":   47,
    "asa":  47,
}


def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def _iter_jsonl(p: Path):
    if not p.exists():
        return
    with open(p, "r", errors="replace") as f:
        for line in f:
            line = line.strip().lstrip("\x00")   # boat power-loss NUL guard
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


# --------------------------------------------------------------------- lifts
def load_lifts() -> list[dict]:
    """Real lift shafts with the set of floor numbers each one serves."""
    reg = _read_json(LIFT_LINES, {})
    lifts = []
    for r in reg.get("lifts", []):
        if str(r.get("real_or_proposed", "real")).lower().startswith("prop"):
            continue                       # topology reality: real shafts only
        nums = r.get("serves_num")
        if not isinstance(nums, list):
            nums = []
            for f in (r.get("serves") or []):
                try:
                    nums.append(int(str(f).replace("floor_", "").strip()))
                except Exception:
                    pass
        lifts.append({
            "lift_id": r.get("lift_id") or r.get("id") or "lift",
            "label": r.get("label") or r.get("name") or "",
            "serves": set(int(n) for n in nums),
            "sealed": bool(r.get("sealed_packets_required", False)),
            "zones": r.get("allowed_zones") or [],
            "status": r.get("status", "online"),
            "type": r.get("type", ""),
        })
    return lifts


def pick_lift(lifts: list[dict], a: int, b: int) -> dict | None:
    """The REAL lift that actually connects floors a and b: serves BOTH.
    Prefer the most specific online shaft (fewest floors) — that's the shaft the
    sealed packet would travel; the big service/security/stairwell shafts are the
    fallback only when no dedicated line joins the two floors."""
    cands = [l for l in lifts if a in l["serves"] and b in l["serves"]
             and str(l.get("status", "")).lower() in ("online", "available")]
    if not cands:
        return None
    # most specific first; break ties by preferring non-stairwell (sealed) lines
    cands.sort(key=lambda l: (len(l["serves"]), l["type"] == "stairwell"))
    return cands[0]


# --------------------------------------------------------------------- cursor
def load_cursor() -> dict:
    c = _read_json(CURSOR, {})
    if not isinstance(c, dict):
        c = {}
    c.setdefault("emitted_sigs", [])
    return c


def sig(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


# --------------------------------------------------------------------- movements
def gather_movements() -> list[dict]:
    """Return real, sourced info movements: {a,b,label,source,mkey}."""
    moves: list[dict] = []

    # (1) NEEDS delivered up to governance (Wren F46). Only needs whose signature
    #     is in the delivery cursor actually MOVED (were routed to Wren's queue).
    q = _read_json(NEEDS_QUEUE, {})
    cur = _read_json(NEEDS_CURSOR, {})
    delivered = set(cur.get("delivered_need_signatures", []))
    for n in q.get("needs", []):
        floor = n.get("floor")
        need = (n.get("need") or "").strip()
        if not isinstance(floor, int) or not need:
            continue
        nsig = f"{floor}|{need}"
        if nsig not in delivered:
            continue                       # not yet routed up -> no real movement
        if floor == WREN_FLOOR:
            continue                       # can't ride a lift to itself
        moves.append({
            "a": floor, "b": WREN_FLOOR,
            "label": f"F{floor} need -> governance (F{WREN_FLOOR}): {need[:70]}",
            "source": "data/registries/qsb_worker_needs_queue.json",
            "mkey": sig("need", floor, need, n.get("ts", "")),
        })

    # (2) CHAIN REPORTS: only cycles actually delivered to Wren's inbox count as a
    #     real cross-floor packet. Each reporting floor -> Wren F46.
    last_cycles = list(_iter_jsonl(CHAIN_REPORTS))[-6:]   # bound: recent cycles only
    for cyc in last_cycles:
        d = cyc.get("delivered") or {}
        if not (d.get("wren_msg_id") and d.get("wren_inbox")):
            continue                       # not delivered up -> no real movement
        cid = cyc.get("cycle_id", "")
        for rep in cyc.get("reports", []):
            floor = rep.get("floor")
            if not isinstance(floor, int) or floor == WREN_FLOOR:
                continue
            lead = rep.get("lead_role") or rep.get("lead_worker_id") or "chain"
            moves.append({
                "a": floor, "b": WREN_FLOOR,
                "label": f"F{floor} chain report -> Wren (F{WREN_FLOOR}) [{lead}]",
                "source": "data/registries/qsb_worker_chain_reports.jsonl",
                "mkey": sig("chain", cid, floor),
            })

    # (3) LEADERSHIP COMMS: real messages between participants on different floors.
    src_files = [("room", ROOM)]
    if DM_DIR.exists():
        for p in sorted(DM_DIR.glob("*.jsonl")):
            src_files.append(("dm", p))
    for kind, p in src_files:
        recent = list(_iter_jsonl(p))[-40:]              # bound per file
        for m in recent:
            frm = str(m.get("from", "")).lower()
            to = str(m.get("to", "")).lower()
            fa = PARTICIPANT_FLOOR.get(frm)
            # room posts fan out to all other participants; DM has a real recipient
            targets = []
            if to == "room":
                targets = [(pp, fl) for pp, fl in PARTICIPANT_FLOOR.items() if pp != frm]
            else:
                tb = PARTICIPANT_FLOOR.get(to)
                if tb is not None:
                    targets = [(to, tb)]
            if fa is None:
                continue
            for tp_name, fb in targets:
                if fa == fb:
                    continue               # same floor -> no lift ride
                mid = m.get("msg_id", "")
                body = (m.get("body") or "").strip().replace("\n", " ")
                moves.append({
                    "a": fa, "b": fb,
                    "label": f"{frm} (F{fa}) -> {tp_name} (F{fb}): {body[:60]}",
                    "source": ("data/registries/leadership_comms/room.jsonl"
                               if kind == "room"
                               else f"data/registries/leadership_comms/dm/{p.name}"),
                    "mkey": sig("comms", mid, fa, fb),
                })

    # Interleave movement types round-robin so a single --max run lights up the
    # variety of real lifts (leadership comms on the executive lift, needs on the
    # executive/service lifts, chain reports on the service lift) rather than
    # draining one source first. Ordering only — every row is still real+sourced.
    buckets: dict[str, list[dict]] = {}
    for mv in moves:
        cat = mv["mkey"].__class__  # unused; group by source family
        fam = ("comms" if "leadership_comms" in mv["source"]
               else "needs" if "needs_queue" in mv["source"]
               else "chain")
        buckets.setdefault(fam, []).append(mv)
    interleaved: list[dict] = []
    order = [f for f in ("comms", "needs", "chain") if f in buckets]
    idx = {f: 0 for f in order}
    while any(idx[f] < len(buckets[f]) for f in order):
        for f in order:
            if idx[f] < len(buckets[f]):
                interleaved.append(buckets[f][idx[f]])
                idx[f] += 1
    return interleaved


# --------------------------------------------------------------------- emit
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=40, help="max rows this run (rate limit)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    lifts = load_lifts()
    if not lifts:
        print("no real lifts found in", LIFT_LINES, file=sys.stderr)
        return 2

    cursor = load_cursor()
    seen = set(cursor["emitted_sigs"])
    moves = gather_movements()

    rows, skipped_no_lift, skipped_dup = [], 0, 0
    lifts_used: dict[str, int] = {}
    for mv in moves:
        if len(rows) >= args.max:
            break
        if mv["mkey"] in seen:
            skipped_dup += 1
            continue
        lift = pick_lift(lifts, mv["a"], mv["b"])
        if lift is None:
            skipped_no_lift += 1           # honest: no real lift connects these floors
            continue
        row = {
            "ts": utc(),
            "from": mv["a"],
            "to": mv["b"],
            "cat": "lift",
            "label": mv["label"],
            "real": True,
            "source": mv["source"],
            "lift_id": lift["lift_id"],
            "lift": lift["label"],
            "sealed": lift["sealed"],
            "zones": lift["zones"],
        }
        rows.append((mv["mkey"], row))
        lifts_used[lift["lift_id"]] = lifts_used.get(lift["lift_id"], 0) + 1

    if args.dry_run:
        for _, r in rows:
            print(json.dumps(r))
        print(f"\n[dry-run] would emit {len(rows)} lift-traffic rows across "
              f"{len(lifts_used)} real lifts; "
              f"skipped {skipped_dup} dup, {skipped_no_lift} no-lift.",
              file=sys.stderr)
        print(f"[dry-run] lifts carrying traffic: {lifts_used}", file=sys.stderr)
        return 0

    if rows:
        FEED.parent.mkdir(parents=True, exist_ok=True)
        with open(FEED, "a") as f:                       # APPEND-ONLY (shared)
            for _, r in rows:
                f.write(json.dumps(r) + "\n")
        for mkey, _ in rows:
            seen.add(mkey)
        cursor["emitted_sigs"] = list(seen)[-5000:]      # bound cursor growth
        cursor["last_run"] = utc()
        CURSOR.write_text(json.dumps(cursor, indent=1))

    print(json.dumps({
        "ok": True,
        "emitted": len(rows),
        "lifts_carrying_traffic": len(lifts_used),
        "lifts_used": lifts_used,
        "skipped_dup": skipped_dup,
        "skipped_no_lift": skipped_no_lift,
        "feed": "data/registries/qsb_map_traffic_feed.jsonl",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
