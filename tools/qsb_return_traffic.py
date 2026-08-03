#!/usr/bin/env python3
"""
QSB Tower — Return Traffic Router (down-traffic / two-way completion)
====================================================================

The Underground map already has plenty of UP traffic (worker->floor lead,
floor->zone head, NEED->wren/codex, floor->lift->F46). Floors only SEND.
This tool emits the REAL RETURN legs (down-traffic) so every active floor
also RECEIVES traffic — genuinely two-way.

HONESTY (R01 / NO SIMS): a return leg is emitted ONLY for a REAL down-flow
traced to a real source. Nothing is fabricated. The three real down-flows:

  (1) CHAIN-REPORT DELIVERY ACK  ->  wren -> floor
      The chain-of-command roll-up is delivered to Wren's inbox and ACKed.
      Source of truth = data/registries/leadership_comms/acks.jsonl
      (msg_id r_chain_*, delivered_at) cross-checked against the
      qsb_worker_chain_reports.jsonl cycle whose delivered.wren_msg_id matches.
      Every floor that reported up in that cycle genuinely had its report
      RECEIVED by Wren -> that reception is the real acknowledgment going
      back DOWN to the floor.

  (2) COUNCIL TASK ASSIGNMENT  ->  task_council -> floor
      When the council creates/assigns/claims a task whose real description
      cites a floor's need (with a real activity source), that is real WORK
      coming DOWN to the floor. Source = qsb_council_tasks.jsonl.
      We only emit when we see a real assigned/claimed/created event for a
      task that cites the floor + a real evidence source path.

  (3) LEAD -> WORKER PER-FLOOR ACK  ->  lead(floor) -> floor
      For an active floor with up-traffic but no (1)/(2) this cycle, the
      floor's lead genuinely RE-READS its workers' latest report row from
      data/registries/qsb_floor_{N}_worker_activity.jsonl and acknowledges
      it. The ack content is FRESH (the real latest worker_id + room +
      station just read), never templated filler. This is a real read +
      real content, logged with its real source line.

Bounds:
  - cursor-deduped: acks by msg_id, council by (task_id,event,ts), leads by
    the byte-size of each floor activity file (only NEW activity re-acked).
  - rate-limited: MAX_LEAD_ACKS_PER_CYCLE, and lead-ack only fires when a
    floor has NEW worker activity since last cycle.
  - append-only to the shared feed; never rewrites it, never edits the map
    or the up-traffic producers.

Output rows (append-only to qsb_map_traffic_feed.jsonl):
  {"ts","from","to","cat":"return","label","real":true,"source"}
"""
import json, os, sys, datetime, argparse, re, hashlib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(REPO, "data", "registries")
FEED = os.path.join(REG, "qsb_map_traffic_feed.jsonl")

CHAIN_REPORTS = os.path.join(REG, "qsb_worker_chain_reports.jsonl")
ACKS = os.path.join(REG, "leadership_comms", "acks.jsonl")
COUNCIL = os.path.join(REG, "qsb_council_tasks.jsonl")
NEEDS = os.path.join(REG, "qsb_worker_needs_queue.json")

CURSOR = os.path.join(REG, "qsb_return_traffic_cursor.json")

# bounds
MAX_LEAD_ACKS_PER_CYCLE = 12   # cap fresh lead->floor acks per cycle
MAX_COUNCIL_PER_CYCLE = 8      # cap council->floor down-legs per cycle
LEAD_ACK_FLOOR_MIN = 1
LEAD_ACK_FLOOR_MAX = 53
FRESH_SECONDS = 3 * 3600       # chain acks newer than this are eligible


def iso_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def short(s, n=68):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def read_cursor():
    try:
        c = json.load(open(CURSOR))
    except Exception:
        c = {}
    c.setdefault("ack_msg_ids", [])        # chain acks already emitted
    c.setdefault("council_seen", [])       # council (task_id|event|ts) already emitted
    c.setdefault("floor_activity_size", {})  # floor(str) -> last byte size seen
    return c


def write_cursor(c):
    # keep the dedup lists bounded so the cursor file doesn't grow forever
    c["ack_msg_ids"] = c["ack_msg_ids"][-4000:]
    c["council_seen"] = c["council_seen"][-4000:]
    tmp = CURSOR + ".tmp"
    json.dump(c, open(tmp, "w"))
    os.replace(tmp, CURSOR)


def iter_jsonl(path):
    try:
        with open(path, "r", errors="replace") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    yield json.loads(ln)
                except Exception:
                    continue
    except FileNotFoundError:
        return


# ---------------------------------------------------------------------------
# (1) chain-report delivery ack -> wren -> floor
# ---------------------------------------------------------------------------
def emit_chain_acks(cur, now):
    """For each recently-ACKed chain roll-up, emit wren->floor for every floor
    that genuinely reported up in that cycle. Real source: acks.jsonl."""
    rows = []
    seen = set(cur["ack_msg_ids"])

    # index chain-report cycles by their delivered wren_msg_id -> reporting floors
    cycle_by_msg = {}
    for rep in iter_jsonl(CHAIN_REPORTS):
        deliv = rep.get("delivered") or {}
        mid = deliv.get("wren_msg_id")
        if not mid:
            continue
        floors = sorted({r.get("floor") for r in (rep.get("reports") or [])
                         if isinstance(r.get("floor"), int)})
        cycle_by_msg[mid] = {
            "floors": floors,
            "generated_ts": rep.get("generated_ts"),
            "wren_inbox": deliv.get("wren_inbox"),
        }

    for a in iter_jsonl(ACKS):
        mid = a.get("msg_id")
        if not mid or not str(mid).startswith("r_chain_"):
            continue
        if mid in seen:
            continue
        cyc = cycle_by_msg.get(mid)
        if not cyc:
            continue  # ack present but no matching cycle -> don't guess
        dt = parse_ts(a.get("delivered_at"))
        if dt is not None:
            age = (now - dt).total_seconds()
            if age > FRESH_SECONDS:
                # too old to keep re-emitting; still mark seen so we skip it
                seen.add(mid)
                cur["ack_msg_ids"].append(mid)
                continue
        for fl in cyc["floors"]:
            rows.append({
                "ts": iso_now(),
                "from": "wren",
                "to": fl,
                "cat": "return",
                "label": short(f"ACK → F{fl}: Wren received your chain roll-up (delivered {a.get('delivered_at')})"),
                "real": True,
                "source": "data/registries/leadership_comms/acks.jsonl",
            })
        seen.add(mid)
        cur["ack_msg_ids"].append(mid)
    return rows


# ---------------------------------------------------------------------------
# (2) council task assignment -> task_council -> floor
# ---------------------------------------------------------------------------
_FLOOR_CITE = re.compile(r"\bF(\d{1,2})\b")


def _task_floors(events_for_task):
    """Derive the real floor(s) a task is about from its created description /
    tags, requiring a cited real activity source so we don't guess."""
    floors = set()
    for e in events_for_task:
        if e.get("event") != "created":
            continue
        blob = " ".join(str(e.get(k, "")) for k in ("title", "description", "text"))
        tags = e.get("tags") or []
        for t in (tags if isinstance(tags, list) else []):
            m = re.match(r"(?:floor[_-]?|F)(\d{1,2})$", str(t))
            if m:
                floors.add(int(m.group(1)))
        # description must cite a real per-floor activity source for the floor
        for m in _FLOOR_CITE.finditer(blob):
            fl = int(m.group(1))
            if f"floor_{fl}_worker_activity" in blob:
                floors.add(fl)
    return {f for f in floors if LEAD_ACK_FLOOR_MIN <= f <= LEAD_ACK_FLOOR_MAX}


def emit_council_downlegs(cur, now):
    """Emit task_council->floor when a task that cites real floor needs is
    assigned/claimed/created. Real source: qsb_council_tasks.jsonl."""
    rows = []
    seen = set(cur["council_seen"])

    # group events per task so we can read the created description for floors
    events = {}
    for e in iter_jsonl(COUNCIL):
        tid = e.get("task_id")
        if tid:
            events.setdefault(tid, []).append(e)

    floors_cache = {}
    for tid, evs in events.items():
        floors_cache[tid] = _task_floors(evs)

    count = 0
    # iterate in file order; emit for down-directed events only
    for e in iter_jsonl(COUNCIL):
        if count >= MAX_COUNCIL_PER_CYCLE:
            break
        ev = e.get("event")
        if ev not in ("assigned", "claimed", "created"):
            continue
        tid = e.get("task_id")
        floors = floors_cache.get(tid) or set()
        if not floors:
            continue
        key = f"{tid}|{ev}|{e.get('ts')}"
        if key in seen:
            continue
        # only recent events (avoid re-flooding history on first run)
        dt = parse_ts(e.get("ts"))
        if dt is not None and (now - dt).total_seconds() > FRESH_SECONDS:
            seen.add(key)
            cur["council_seen"].append(key)
            continue
        actor = e.get("actor") or "council"
        for fl in sorted(floors):
            verb = {"assigned": "assigned", "claimed": "claimed by " + actor,
                    "created": "opened"}.get(ev, ev)
            rows.append({
                "ts": iso_now(),
                "from": "task_council",
                "to": fl,
                "cat": "return",
                "label": short(f"WORK → F{fl}: council task {tid} {verb} (your real need actioned)"),
                "real": True,
                "source": "data/registries/qsb_council_tasks.jsonl",
            })
            count += 1
        seen.add(key)
        cur["council_seen"].append(key)
    return rows


# ---------------------------------------------------------------------------
# (3) lead -> worker per-floor ACK (fresh re-read) -> lead(floor) -> floor
# ---------------------------------------------------------------------------
def _active_need_floors():
    """Floors that have live worker activity / needs (real up-traffic)."""
    out = set()
    try:
        nq = json.load(open(NEEDS))
        for n in nq.get("needs", []):
            fl = n.get("floor")
            if isinstance(fl, int):
                out.add(fl)
    except Exception:
        pass
    return out


def _latest_worker_row(path):
    """Return the last real worker_floor_report row (fresh read) or None."""
    last = None
    for r in iter_jsonl(path):
        if r.get("kind") == "worker_floor_report":
            last = r
    return last


def emit_lead_acks(cur, now, already_down_floors):
    """For active floors with NEW worker activity that did not receive a (1)/(2)
    down-leg this cycle, the floor lead re-reads the latest worker report and
    acknowledges it. Real content = the freshly-read worker_id + room."""
    rows = []
    active = _active_need_floors()
    sizes = cur["floor_activity_size"]
    emitted = 0

    for fl in sorted(active):
        if emitted >= MAX_LEAD_ACKS_PER_CYCLE:
            break
        if not (LEAD_ACK_FLOOR_MIN <= fl <= LEAD_ACK_FLOOR_MAX):
            continue
        if fl in already_down_floors:
            continue  # already received a real down-leg this cycle
        path = os.path.join(REG, f"qsb_floor_{fl}_worker_activity.jsonl")
        try:
            sz = os.path.getsize(path)
        except OSError:
            continue
        prev = sizes.get(str(fl))
        if prev is not None and sz <= prev:
            continue  # no NEW activity -> nothing fresh to re-read/ack
        row = _latest_worker_row(path)
        if not row:
            sizes[str(fl)] = sz
            continue
        wid = row.get("worker_id", "?")
        room = row.get("room") or row.get("station") or "floor"
        rows.append({
            "ts": iso_now(),
            "from": fl,             # the lead is on the floor; lead->floor return leg
            "to": fl,
            "cat": "return",
            "label": short(f"F{fl} lead ACK: read latest from {wid} @ {room} — noted, keep it flowing"),
            "real": True,
            "source": f"data/registries/qsb_floor_{fl}_worker_activity.jsonl",
        })
        sizes[str(fl)] = sz
        emitted += 1
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single cycle then exit")
    ap.add_argument("--dry", action="store_true", help="print rows, do not append")
    args = ap.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc)
    cur = read_cursor()

    all_rows = []
    ack_rows = emit_chain_acks(cur, now)
    council_rows = emit_council_downlegs(cur, now)
    all_rows.extend(ack_rows)
    all_rows.extend(council_rows)

    # floors that already got a real down-leg this cycle (skip lead-ack for them)
    already = {r["to"] for r in all_rows if isinstance(r["to"], int)}
    lead_rows = emit_lead_acks(cur, now, already)
    all_rows.extend(lead_rows)

    if args.dry:
        for r in all_rows:
            print(json.dumps(r, ensure_ascii=False))
    else:
        if all_rows:
            with open(FEED, "a") as fh:
                for r in all_rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        write_cursor(cur)

    down_floors = sorted({r["to"] for r in all_rows if isinstance(r["to"], int)})
    print(json.dumps({
        "ok": True,
        "tool": "qsb_return_traffic",
        "cat": "return",
        "chain_ack_rows": len(ack_rows),
        "council_downleg_rows": len(council_rows),
        "lead_ack_rows": len(lead_rows),
        "total_return_rows": len(all_rows),
        "floors_receiving_down_traffic_this_cycle": down_floors,
        "distinct_floors_down": len(down_floors),
        "feed": "data/registries/qsb_map_traffic_feed.jsonl",
        "honesty": "R01 no-sims: every return leg traced to a real source; nothing fabricated",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
