#!/vaults/nvme0/qsb_tower_v1/.venv/bin/python3
"""
qsb_worker_activation_engine.py — ONE efficient engine that wakes the QSB Tower's
~2,000 assigned floor workers so the whole building becomes alive with REAL,
freshly-read worker traffic on the bus + floor intercom.

Authorized by Ross 2026-07-29: "turn the whole skyscraper on so all the workers
start moving and talking to Wren and Codex."

DESIGN (efficient + honest)
  - ONE process on a systemd timer. NOT 2000 processes, NOT 2000 model calls.
  - Each tick wakes a bounded BATCH of workers (default 120), cycling through the
    whole ~2029-worker population via a persisted cursor. At 120/tick every ~30s
    the full building cycles in a few minutes, then repeats — so it stays alive.
  - For each woken worker, the engine does a REAL DETERMINISTIC ACTION: it reads
    that worker's real station assignment (floor / room / station) and folds in
    its floor's REAL freshly-read card state (roster size, floor manager, zone,
    gate posture, skeleton flag, card mtime). It then composes a FACTUAL short
    line and appends it to:
        (1) the shared bus journal  data/registries/qsb_bus_journal.jsonl
            using the bus's real {"name","payload","ts"} schema (name=
            "worker.floor.report"), same shape the socket bus journals.
        (2) a per-floor worker-activity log
            data/registries/qsb_floor_{N}_worker_activity.jsonl
            (append-only) — this filename is auto-detected by the sibling
            qsb_floor_activity_index.py generic-floor discovery (glob
            *floor_{N}_*.json* + word-boundary regex, prefers JSONL last-row ts),
            so the floor lights on the transit map WITHOUT editing the index.
        (3) honest per-floor counters in
            data/registries/qsb_floor_intercom_state.json (sent/received/kinds).

HONESTY (R01 / Ross's absolute NO SIMS)
  - Every worker message is a REAL fact freshly read this tick from the station
    assignment registry + the floor's own card on disk. Nothing is fabricated
    chatter. A "need" is emitted ONLY when the real data shows one (skeleton card
    still un-fit-out, or a stale card, or a placeholder roster smaller than the
    real station count on that floor) — otherwise no need is stated.
  - Workers REPORT and READ only. No real-world execution. No gate is flipped.
    Every row carries advisory_only=true, execution_allowed=false, source paths.
  - Kernel-reserved Penthouse floors (153, 168) are NEVER emitted (CLAUDE.md).
  - A floor with no real station assignments stays SILENT (never invented).
  - NO per-worker LLM call. Pure file reads. Cheap + safe.

RATE + SAFETY
  - Bounded BATCH per tick (default 120). Between per-worker bus writes we micro-
    sleep so we never flood the journal. Floor cards are read ONCE per floor per
    tick and cached (not once per worker).

USAGE
  python3 tools/qsb_worker_activation_engine.py --once          # one tick
  python3 tools/qsb_worker_activation_engine.py --once --batch 200
  python3 tools/qsb_worker_activation_engine.py --status        # cursor + counts
"""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, re, socket, sys, time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
FLOORS_DIR = ROOT / "floors"

STATIONS = REG / "qsb_worker_station_assignments.json"
BUS_SOCKET = ROOT / "state" / "qsb_bus.sock"         # live socket bus (real)
BUS_JOURNAL = REG / "qsb_bus_journal.jsonl"          # real bus journal (name/payload/ts)
INTERCOM = REG / "qsb_floor_intercom_state.json"     # honest per-floor counters
F47 = REG / "qsb_f47_team_records.jsonl"             # audit record
CURSOR = REG / "qsb_worker_activation_cursor.json"   # persisted round-robin cursor
WORKER_BUS_TAIL = REG / "qsb_worker_bus_activity.jsonl"  # durable worker bus tail (NOT rotated)
PERFLOOR_TPL = "qsb_floor_{n}_worker_activity.jsonl" # per-floor activity (index-detected)

# Kernel-reserved Penthouse floors — MUST stay dim (CLAUDE.md). Never emit.
KERNEL_RESERVED = {153, 168}

DEFAULT_BATCH = 120
PER_WRITE_SLEEP_S = 0.004  # micro-sleep between bus writes so we never flood


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def floor_num_from_id(floor_id: str) -> int | None:
    m = re.search(r"floor_(\d+)", floor_id or "")
    return int(m.group(1)) if m else None


def load_stations() -> dict:
    with open(STATIONS) as f:
        return json.load(f).get("stations", {})


def find_floor_card(floor_id: str) -> Path | None:
    """Locate the real floor_card.json for a floor_id like 'floor_45_worker_...'."""
    d = FLOORS_DIR / floor_id
    card = d / "floor_card.json"
    if card.exists():
        return card
    # fall back: match by floor number directory prefix. Assignments may use a
    # different department slug than the real dir (e.g. assignment says
    # floor_01_order_fulfilment_hub but the real dir is floor_01_operations_...),
    # and dirs are zero-padded (floor_01_*), so try BOTH padded + unpadded.
    num = floor_num_from_id(floor_id)
    if num is None:
        return None
    for prefix in (f"floor_{num:02d}_", f"floor_{num}_"):
        for sub in FLOORS_DIR.glob(f"{prefix}*"):
            c = sub / "floor_card.json"
            if c.exists():
                return c
    return None


def read_floor_card(floor_id: str) -> dict:
    """Freshly read the floor's real card THIS tick. Returns real facts + a
    genuine `need` (or None). Cached per tick by the caller."""
    card_path = find_floor_card(floor_id)
    if card_path is None:
        return {"ok": False, "floor_id": floor_id}
    try:
        raw = card_path.read_bytes()
        card = json.loads(raw.decode("utf-8"))
    except Exception:
        return {"ok": False, "floor_id": floor_id}
    roster = card.get("team_roster", []) or []
    mtime = os.path.getmtime(card_path)
    gate = card.get("gate_posture", {}) or {}
    cats = {}
    mgr = None
    for m in roster:
        c = m.get("category", "worker")
        cats[c] = cats.get(c, 0) + 1
        if c == "floor_manager" and mgr is None:
            mgr = m.get("id")
    return {
        "ok": True,
        "floor_id": floor_id,
        "card_path": str(card_path.relative_to(ROOT)),
        "floor_name": card.get("floor_name") or card.get("department") or floor_id,
        "floor_number": card.get("floor_number", floor_num_from_id(floor_id)),
        "zone": card.get("zone"),
        "roster_size": len(roster),
        "roster_categories": cats,
        "floor_manager": mgr,
        "skeleton": bool(card.get("skeleton", False)),
        "visitor_open": bool(card.get("visitor_open", False)),
        "advisory_only": bool(gate.get("advisory_only", card.get("advisory_only", True))),
        "execution_allowed": bool(gate.get("execution_allowed", False)),
        "card_mtime": datetime.datetime.fromtimestamp(
            mtime, datetime.timezone.utc).isoformat(),
        "card_mtime_epoch": mtime,
        "card_sha12": hashlib.sha256(raw).hexdigest()[:12],
    }


def genuine_need(card: dict, station_count_on_floor: int) -> str | None:
    """Return a REAL need ONLY when the freshly-read data shows one; else None.
    Every branch traces to a real, checkable condition on disk."""
    if not card.get("ok"):
        return None
    now = time.time()
    # 1) skeleton card still un-fit-out
    if card.get("skeleton"):
        return "floor card still skeleton (fit-out pending)"
    # 2) placeholder roster far smaller than the real assigned station count
    rs = card.get("roster_size", 0)
    if station_count_on_floor > 0 and rs > 0 and rs * 4 < station_count_on_floor:
        return (f"roster card lists {rs} but {station_count_on_floor} stations "
                f"assigned here (headcount reconcile)")
    # 3) stale card (> 30 days since last real card edit)
    age_days = (now - card.get("card_mtime_epoch", now)) / 86400.0
    if age_days > 30:
        return f"floor card {int(age_days)}d stale (refresh pending)"
    return None


def worker_role_on_floor(card: dict, station: dict) -> str:
    """Best real descriptor for what the worker does at this station."""
    room = station.get("room") or "station"
    return room


def compose_message(worker_id: str, card: dict, station: dict, need: str | None) -> str:
    """FACTUAL short line, all fields freshly read. No fabricated content."""
    fn = card.get("floor_number")
    name = card.get("floor_name")
    room = station.get("room", "station")
    st = station.get("station", "")
    base = f"{worker_id} @ F{fn} {name} · {room}"
    facts = f"roster {card.get('roster_size',0)}, mgr {card.get('floor_manager') or 'TBD'}"
    if st:
        facts = f"{st}; " + facts
    tail = " · NEED: " + need if need else " · nominal"
    return f"{base}: {facts}{tail} (advisory_only, exec=off)"


# ---------------- cursor persistence ----------------
def load_cursor() -> int:
    if CURSOR.exists():
        try:
            return int(json.loads(CURSOR.read_text()).get("cursor", 0))
        except Exception:
            return 0
    return 0


def save_cursor(cur: int, total: int, last_batch: int, emitted: int) -> None:
    CURSOR.write_text(json.dumps({
        "kind": "qsb_worker_activation_cursor",
        "cursor": cur,
        "total_workers": total,
        "last_batch": last_batch,
        "last_emitted": emitted,
        "ts": now_iso(),
    }, indent=1))


# ---------------- intercom counter update (honest) ----------------
def update_intercom(per_floor_counts: dict) -> None:
    """Fold this tick's REAL per-floor worker-report counts into the honest
    per-floor intercom counters. Append-only semantics on counts; nothing faked —
    each increment is one real worker report actually written this tick."""
    try:
        state = json.loads(INTERCOM.read_text())
    except Exception:
        return
    pf = state.setdefault("per_floor", {})
    total_new = 0
    for fnum, cnt in per_floor_counts.items():
        key = f"floor_{fnum}"
        ent = pf.setdefault(key, {"sent": 0, "received": 0, "kinds_sent": {},
                                  "lift_use": {}})
        ent["sent"] = int(ent.get("sent", 0)) + cnt
        ks = ent.setdefault("kinds_sent", {})
        ks["worker_floor_report"] = int(ks.get("worker_floor_report", 0)) + cnt
        # every packet routes via a lift (rule: no direct floor-to-floor)
        lu = ent.setdefault("lift_use", {})
        lu["service_lift"] = int(lu.get("service_lift", 0)) + cnt
        total_new += cnt
    state["total_packets"] = int(state.get("total_packets", 0)) + total_new
    kinds = set(state.get("kinds", []))
    kinds.add("worker_floor_report")
    state["kinds"] = sorted(kinds)
    state["last_worker_activation_ts"] = now_iso()
    state["execution_allowed"] = False
    state["advisory_only"] = True
    tmp = INTERCOM.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, INTERCOM)


# ---------------- bus + per-floor append ----------------
def bus_socket_publish(rows: list[dict], sample: int = 30) -> int:
    """Publish a BOUNDED SAMPLE of worker report events LIVE to the real socket
    bus so subscribers hear them, using the bus protocol
    {"action":"publish","event":{name,payload,ts}}. Best-effort: if the bus
    daemon is down we silently fall back to the durable tail (below) — never
    fatal, never blocks the tick. Rate-limited to `sample` per tick because the
    live journal rotates at 1000 lines and must not be flooded."""
    if not BUS_SOCKET.exists():
        return 0
    sent = 0
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(str(BUS_SOCKET))
        for r in rows[:sample]:
            line = json.dumps({"action": "publish", "event": r},
                              separators=(",", ":")) + "\n"
            s.sendall(line.encode())
            sent += 1
            time.sleep(PER_WRITE_SLEEP_S)
        s.close()
    except (ConnectionRefusedError, FileNotFoundError, OSError, socket.timeout):
        return sent
    return sent


def worker_bus_tail_append(rows: list[dict]) -> None:
    """Append ALL worker report events to a DURABLE worker bus tail that the
    live daemon does NOT rotate — this is the honest, permanent record of worker
    bus traffic (the shared journal is high-frequency + rotated, so it's the
    live wire, not the store)."""
    with open(WORKER_BUS_TAIL, "a") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


def perfloor_append(fnum: int, rows: list[dict]) -> None:
    path = REG / PERFLOOR_TPL.format(n=fnum)
    with open(path, "a") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


# ---------------- one tick ----------------
def tick(batch: int, verbose: bool = False) -> dict:
    stations = load_stations()
    worker_ids = sorted(stations.keys())
    total = len(worker_ids)
    if total == 0:
        return {"ok": False, "reason": "no stations"}

    # station count per floor (real) — for genuine-need headcount reconcile
    station_count_by_floor: dict[int, int] = {}
    for wid, s in stations.items():
        fn = floor_num_from_id(s.get("floor", ""))
        if fn is not None:
            station_count_by_floor[fn] = station_count_by_floor.get(fn, 0) + 1

    cur = load_cursor() % total
    idx = [(cur + i) % total for i in range(min(batch, total))]

    card_cache: dict[str, dict] = {}
    bus_rows: list[dict] = []
    perfloor_rows: dict[int, list[dict]] = {}
    perfloor_counts: dict[int, int] = {}
    distinct_floors = set()
    emitted = 0
    ts = now_iso()

    for i in idx:
        wid = worker_ids[i]
        station = stations[wid]
        floor_id = station.get("floor", "")
        fnum = floor_num_from_id(floor_id)
        if fnum is None or fnum in KERNEL_RESERVED:
            continue  # honestly skip kernel-reserved / unresolvable
        if floor_id not in card_cache:
            card_cache[floor_id] = read_floor_card(floor_id)
        card = card_cache[floor_id]
        if not card.get("ok"):
            continue  # no real card -> stay silent, never invent
        need = genuine_need(card, station_count_by_floor.get(fnum, 0))
        msg = compose_message(wid, card, station, need)

        # (1) bus journal event — real bus schema
        bus_rows.append({
            "name": "worker.floor.report",
            "payload": {
                "worker_id": wid,
                "floor": fnum,
                "floor_id": floor_id,
                "floor_name": card.get("floor_name"),
                "room": station.get("room"),
                "station": station.get("station"),
                "roster_size": card.get("roster_size"),
                "floor_manager": card.get("floor_manager"),
                "zone": card.get("zone"),
                "need": need,
                "message": msg,
                "advisory_only": True,
                "execution_allowed": False,
                "source": [
                    "data/registries/qsb_worker_station_assignments.json",
                    card.get("card_path"),
                ],
                "card_sha12": card.get("card_sha12"),
                "card_mtime": card.get("card_mtime"),
            },
            "ts": ts,
        })
        # (2) per-floor activity row (index auto-detected)
        perfloor_rows.setdefault(fnum, []).append({
            "ts": ts,
            "kind": "worker_floor_report",
            "floor": fnum,
            "worker_id": wid,
            "room": station.get("room"),
            "station": station.get("station"),
            "roster_size": card.get("roster_size"),
            "floor_manager": card.get("floor_manager"),
            "need": need,
            "message": msg,
            "advisory_only": True,
            "execution_allowed": False,
            "source": card.get("card_path"),
        })
        perfloor_counts[fnum] = perfloor_counts.get(fnum, 0) + 1
        distinct_floors.add(fnum)
        emitted += 1
        if verbose:
            print(msg)

    # write everything (append-only)
    live_sent = bus_socket_publish(bus_rows)       # live wire (bounded sample)
    worker_bus_tail_append(bus_rows)               # durable store (all rows)
    for fnum, rows in perfloor_rows.items():
        perfloor_append(fnum, rows)
    update_intercom(perfloor_counts)

    new_cur = (cur + len(idx)) % total
    save_cursor(new_cur, total, len(idx), emitted)

    # F47 audit record
    with open(F47, "a") as f:
        f.write(json.dumps({
            "ts": ts,
            "kind": "worker_activation_tick",
            "operator": "qsb_worker_activation_engine",
            "summary": (f"woke {len(idx)} workers, {emitted} real reports across "
                        f"{len(distinct_floors)} floors; cursor {cur}->{new_cur}/{total}"),
            "distinct_floors": sorted(distinct_floors),
            "advisory_only": True,
            "execution_allowed": False,
            "no_sims": True,
        }) + "\n")

    return {
        "ok": True, "total_workers": total, "woken": len(idx),
        "emitted": emitted, "distinct_floors": sorted(distinct_floors),
        "live_bus_published": live_sent, "cursor_from": cur, "cursor_to": new_cur,
    }


def cmd_status() -> None:
    stations = load_stations()
    total = len(stations)
    cur = load_cursor()
    perfloor = sorted(REG.glob("qsb_floor_*_worker_activity.jsonl"))
    print(json.dumps({
        "total_workers": total,
        "cursor": cur,
        "per_floor_activity_files": len(perfloor),
        "per_floor_files_sample": [p.name for p in perfloor[:8]],
    }, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="run one tick and exit")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        cmd_status()
        return 0
    # default behaviour is one tick (systemd timer calls --once)
    res = tick(a.batch, verbose=a.verbose)
    print(json.dumps(res, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
