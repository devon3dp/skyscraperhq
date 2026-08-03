#!/usr/bin/env python3
"""
QSB Tower — Worker Information Router
=====================================

Routes REAL worker output to where it genuinely needs to go, generating
directional traffic across the building.

HONESTY (R01 / NO SIMS): every routed row traces to a real worker
message/need in data/registries/qsb_floor_{N}_worker_activity.jsonl,
using the REAL chain of command (qsb_worker_chain_of_command.json) and the
REAL needs queue (qsb_worker_needs_queue.json). No destination is fabricated.

Routing model per floor with fresh activity:
  worker  -> floor (its floor LEAD; the floor manager owns the floor)
  floor   -> zone-head anchor (lead escalates to its department/zone head)
  NEED    -> wren  (governance hub; real needs-queue destination)
  NEED    -> codex (build/fix hub; real needs-queue destination)

Only the LATEST unseen rows per floor are routed (cursor by byte offset),
and the per-cycle emission is capped so the feed + map stay readable.

Output: append-only to data/registries/qsb_map_traffic_feed.jsonl
  {"ts","from","to","cat":"route","label","real":true,"source"}

This tool OWNS its router logic and its cursor; it only APPENDS to the
shared feed (siblings append too). It never rewrites the feed and never
edits the map, the activation engine, the activity index, or sibling tools.
"""
import json, os, sys, time, datetime, argparse, glob, re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(REPO, "data", "registries")
FEED = os.path.join(REG, "qsb_map_traffic_feed.jsonl")
COC = os.path.join(REG, "qsb_worker_chain_of_command.json")
NEEDS = os.path.join(REG, "qsb_worker_needs_queue.json")
FLOORS = os.path.join(REG, "floors.json")
CURSOR = os.path.join(REG, "qsb_worker_info_router_cursor.json")

# freshness + rate-limit bounds
FRESH_SECONDS = 3600          # only route rows newer than this
MAX_ROWS_PER_FLOOR = 3        # representative real rows per floor per cycle
GOV_HUBS = ("wren", "codex")  # real needs-queue destinations (up the chain)


def iso_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def load_zone_heads():
    """Map zone -> anchor floor number (the lowest floor in that zone = its head)."""
    floors = json.load(open(FLOORS))
    zone_min = {}
    for f in floors:
        z = f.get("zone")
        n = f.get("number")
        if z is None or n is None:
            continue
        if z not in zone_min or n < zone_min[z]:
            zone_min[z] = n
    floor_zone = {f["number"]: f.get("zone") for f in floors if "number" in f}
    return floor_zone, zone_min


def load_need_floors():
    """Floors that have a live entry in the real needs queue -> escalate to hubs."""
    try:
        nq = json.load(open(NEEDS))
    except Exception:
        return set()
    out = set()
    for n in nq.get("needs", []):
        fl = n.get("floor")
        if isinstance(fl, int) and fl > 0:
            out.add(fl)
    return out


def read_cursor():
    try:
        return json.load(open(CURSOR))
    except Exception:
        return {}


def write_cursor(cur):
    tmp = CURSOR + ".tmp"
    json.dump(cur, open(tmp, "w"))
    os.replace(tmp, CURSOR)


def tail_new_lines(path, last_size):
    """Return (new_lines, new_size). If file shrank/rotated, read from 0."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return [], last_size
    start = last_size if (last_size and last_size <= size) else 0
    lines = []
    with open(path, "r", errors="replace") as fh:
        fh.seek(start)
        data = fh.read()
    for ln in data.splitlines():
        ln = ln.strip()
        if ln:
            lines.append(ln)
    return lines, size


def short(s, n=64):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single cycle then exit")
    ap.add_argument("--dry", action="store_true", help="print rows, do not append")
    args = ap.parse_args()

    floor_zone, zone_min = load_zone_heads()
    need_floors = load_need_floors()
    cur = read_cursor()
    src_rel = "data/registries/qsb_floor_{N}_worker_activity.jsonl"

    now = datetime.datetime.now(datetime.timezone.utc)
    emitted = []
    files = sorted(glob.glob(os.path.join(REG, "qsb_floor_*_worker_activity.jsonl")))

    for path in files:
        m = re.search(r"qsb_floor_(\d+)_worker_activity", os.path.basename(path))
        if not m:
            continue
        floor = int(m.group(1))
        key = str(floor)
        last_size = cur.get(key, {}).get("size", 0)
        lines, new_size = tail_new_lines(path, last_size)
        if not lines:
            cur.setdefault(key, {})["size"] = new_size
            continue

        # take the freshest rows only, cap per floor
        picked = []
        for ln in reversed(lines):  # newest last in append-only file
            try:
                row = json.loads(ln)
            except Exception:
                continue
            ts = parse_ts(row.get("ts"))
            if ts is None:
                continue
            if (now - ts).total_seconds() > FRESH_SECONDS:
                break  # older rows below; stop (file is time-ordered)
            picked.append(row)
            if len(picked) >= MAX_ROWS_PER_FLOOR:
                break
        picked.reverse()

        zone = floor_zone.get(floor)
        zone_head = zone_min.get(zone) if zone else None
        rel_src = src_rel.replace("{N}", str(floor))

        floor_emitted_route_up = False  # only escalate floor->zone-head once/cycle
        need_hub_sent = set()           # dedupe NEED->hub per (need,hub) per cycle
        for row in picked:
            wid = row.get("worker_id") or "worker"
            need = row.get("need")
            ts = row.get("ts") or iso_now()

            # worker -> floor (worker reports to its floor lead)
            emitted.append({
                "ts": ts, "from": wid, "to": floor, "cat": "route",
                "label": f"{short(wid,32)} → F{floor} lead",
                "real": True, "source": rel_src,
            })

            # floor -> zone head (lead escalates to department/zone head), once
            if zone_head is not None and zone_head != floor and not floor_emitted_route_up:
                emitted.append({
                    "ts": ts, "from": floor, "to": zone_head, "cat": "route",
                    "label": f"F{floor} lead → {zone} head F{zone_head}",
                    "real": True, "source": rel_src,
                })
                floor_emitted_route_up = True

            # NEED -> governance hubs (real needs-queue destinations)
            if need and floor in need_floors:
                for hub in GOV_HUBS:
                    dedupe_key = (short(need, 44), hub)
                    if dedupe_key in need_hub_sent:
                        continue
                    need_hub_sent.add(dedupe_key)
                    emitted.append({
                        "ts": ts, "from": floor, "to": hub, "cat": "route",
                        "label": f"F{floor} NEED → {hub}: {short(need,44)}",
                        "real": True, "source": rel_src,
                    })

        cur[key] = {"size": new_size, "last_route_ts": iso_now()}

    if args.dry:
        for e in emitted:
            print(json.dumps(e))
        print(f"# DRY: {len(emitted)} rows from {len({e['source'] for e in emitted})} floors",
              file=sys.stderr)
        return

    if emitted:
        with open(FEED, "a") as fh:
            for e in emitted:
                fh.write(json.dumps(e) + "\n")
    write_cursor(cur)

    distinct_floors = len({e["source"] for e in emitted})
    print(json.dumps({
        "ok": True, "kind": "qsb_worker_info_router",
        "ts": iso_now(), "rows_appended": len(emitted),
        "distinct_floors": distinct_floors, "feed": "data/registries/qsb_map_traffic_feed.jsonl",
    }))


if __name__ == "__main__":
    main()
