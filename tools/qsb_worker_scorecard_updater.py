#!/usr/bin/env python3
"""
qsb_worker_scorecard_updater.py
================================
LIVING scorecards for the QSB Tower workforce.

Turns REAL worker activity into REAL, updating scorecard metrics.

HONESTY (R01): every metric is derived, line-for-line, from real activity rows
the workers actually emitted. Nothing is invented. Workers that did NOT act keep
a truthful idle state ("live_status": "idle", live counters all 0, last_active_ts
null). We never fabricate activity for an idle worker.

READ (real, append-only worker activity streams — owned by the activation engine,
we only READ them):
  - data/registries/qsb_floor_*_worker_activity.jsonl
        rows: {ts, kind, floor, worker_id, room, station, need, message, source}
  - data/registries/qsb_bus_journal.jsonl  (worker.floor.report rows, when present)
        this journal is live/rotating; we fold in whatever real rows are currently
        there but never depend on them being persistent.

READ (static registry we OWN and update):
  - data/registries/qsb_worker_scorecards.json  (1190 static scorecards)

WRITE (we own these):
  - data/registries/qsb_worker_scorecards_live.json   (the living scorecards)
  - data/registries/qsb_worker_scorecards.json.bak_<UTC>  (backup, first write only
        per run when --write-registry is passed; default is companion-file only)
  - data/registries/qsb_f47_team_records.jsonl        (append-only F47 audit row)

Real metrics computed per active worker (all traceable to activity rows):
  - live_messages_posted   = count of activity rows that worker emitted
  - live_needs_raised      = count of those rows carrying a non-empty `need`
  - live_heartbeat_ticks   = count of DISTINCT batch timestamps (each tick = one
                             floor heartbeat the worker was present for)
  - live_floors_touched    = sorted distinct floor numbers seen in the worker's rows
  - live_rooms_touched     = sorted distinct rooms seen in the worker's rows
  - live_first_active_ts   = min ts across the worker's rows
  - live_last_active_ts    = max ts across the worker's rows
  - live_needs_latest      = the most recent non-empty need text (verbatim)
  - live_sources           = the activity files this worker's rows came from
  - live_status            = "active" if the worker has real rows, else "idle"

We do NOT touch the sibling activation/index/transit/chain/needs tools. We only
own this updater + the scorecards registry.

Usage:
  python3 tools/qsb_worker_scorecard_updater.py                # write live companion
  python3 tools/qsb_worker_scorecard_updater.py --write-registry # ALSO fold live
                                                               # block into the main
                                                               # registry (backs up
                                                               # first)
  python3 tools/qsb_worker_scorecard_updater.py --status        # summary only
  python3 tools/qsb_worker_scorecard_updater.py --show WID       # one worker
"""
from __future__ import annotations

import glob
import json
import os
import sys
import datetime
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "registries"

SCORECARDS = REG / "qsb_worker_scorecards.json"
LIVE_OUT = REG / "qsb_worker_scorecards_live.json"
BUS_JOURNAL = REG / "qsb_bus_journal.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"
PERFLOOR_GLOB = str(REG / "qsb_floor_*_worker_activity.jsonl")

SCHEMA = "qsb.worker.scorecards.live/1"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _read_jsonl_lines(path: Path):
    """Yield parsed rows from a jsonl file, tolerant of NUL corruption / blanks."""
    if not path.exists():
        return
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip("\x00 \n\r\t")
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                # a torn/append-in-progress line; skip it (never fabricate)
                continue


def collect_real_activity() -> tuple[dict, dict]:
    """
    Scan the REAL per-floor activity files (and any live bus rows) and aggregate
    per worker. Returns (per_worker, meta).

    per_worker[worker_id] = {
        messages, needs, ticks(set), floors(set), rooms(set),
        first_ts, last_ts, latest_need, latest_need_ts, sources(set)
    }
    """
    per = {}
    files_seen = []

    def bump(wid, ts, need, floor, room, source):
        if not wid:
            return
        d = per.get(wid)
        if d is None:
            d = per[wid] = {
                "messages": 0,
                "needs": 0,
                "ticks": set(),
                "floors": set(),
                "rooms": set(),
                "first_ts": None,
                "last_ts": None,
                "latest_need": None,
                "latest_need_ts": None,
                "sources": set(),
            }
        d["messages"] += 1
        if ts:
            d["ticks"].add(ts)
            if d["first_ts"] is None or ts < d["first_ts"]:
                d["first_ts"] = ts
            if d["last_ts"] is None or ts > d["last_ts"]:
                d["last_ts"] = ts
        if floor is not None:
            d["floors"].add(floor)
        if room:
            d["rooms"].add(room)
        if source:
            d["sources"].add(source)
        if need:
            d["needs"] += 1
            if d["latest_need_ts"] is None or (ts and ts >= d["latest_need_ts"]):
                d["latest_need"] = need
                d["latest_need_ts"] = ts

    # 1) per-floor activity files (the durable, append-only real stream)
    for path in sorted(glob.glob(PERFLOOR_GLOB)):
        p = Path(path)
        rel = str(p.relative_to(ROOT)) if str(p).startswith(str(ROOT)) else p.name
        count = 0
        for r in _read_jsonl_lines(p):
            wid = r.get("worker_id")
            floor = r.get("floor")
            bump(wid, r.get("ts"), r.get("need"), floor, r.get("room"), rel)
            count += 1
        files_seen.append({"file": rel, "rows": count})

    # 2) live bus journal worker.floor.report rows (best-effort, non-durable)
    bus_rows = 0
    for r in _read_jsonl_lines(BUS_JOURNAL):
        if r.get("name") != "worker.floor.report":
            continue
        pl = r.get("payload") or {}
        wid = pl.get("worker_id")
        floor = pl.get("floor")
        bump(wid, r.get("ts") or pl.get("ts"), pl.get("need"),
             floor, pl.get("room"), "data/registries/qsb_bus_journal.jsonl")
        bus_rows += 1

    meta = {"perfloor_files": files_seen, "bus_worker_rows": bus_rows}
    return per, meta


def build_live_block(agg: dict) -> dict:
    """Turn one worker's real aggregate into a live scorecard block."""
    return {
        "live_status": "active",
        "live_messages_posted": agg["messages"],
        "live_needs_raised": agg["needs"],
        "live_heartbeat_ticks": len(agg["ticks"]),
        "live_floors_touched": sorted(agg["floors"]),
        "live_rooms_touched": sorted(agg["rooms"]),
        "live_first_active_ts": agg["first_ts"],
        "live_last_active_ts": agg["last_ts"],
        "live_needs_latest": agg["latest_need"],
        "live_sources": sorted(agg["sources"]),
    }


def idle_block(prev: dict | None) -> dict:
    """
    Honest idle block. If a worker was active in a PRIOR run we preserve its
    last_seen (that WAS real). If it never acted, everything is null/0.
    """
    prev = prev or {}
    return {
        "live_status": "idle",
        "live_messages_posted": 0,
        "live_needs_raised": 0,
        "live_heartbeat_ticks": 0,
        "live_floors_touched": [],
        "live_rooms_touched": [],
        "live_first_active_ts": None,
        # last_seen carried from a real prior observation, if any; else null
        "live_last_active_ts": prev.get("live_last_active_ts"),
        "live_needs_latest": None,
        "live_sources": [],
    }


def load_prev_live() -> dict:
    """Map worker_id -> prior live block, for honest last_seen carry-over."""
    if not LIVE_OUT.exists():
        return {}
    try:
        d = json.load(open(LIVE_OUT))
    except Exception:
        return {}
    out = {}
    for s in d.get("scorecards", []):
        wid = s.get("worker_id")
        if wid:
            out[wid] = {k: v for k, v in s.items() if k.startswith("live_")}
    return out


def run(write_registry: bool = False) -> dict:
    base = json.load(open(SCORECARDS))
    scorecards = base.get("scorecards", [])
    per, meta = collect_real_activity()
    prev_live = load_prev_live()

    ts = now_iso()
    live_scorecards = []
    active_ct = idle_ct = 0
    active_wids_in_registry = set()

    for sc in scorecards:
        wid = sc.get("worker_id")
        merged = dict(sc)  # preserve every static field verbatim
        agg = per.get(wid)
        if agg and agg["messages"] > 0:
            merged.update(build_live_block(agg))
            active_ct += 1
            active_wids_in_registry.add(wid)
        else:
            merged.update(idle_block(prev_live.get(wid)))
            idle_ct += 1
        merged["live_updated_ts"] = ts
        live_scorecards.append(merged)

    # workers who genuinely acted but have NO scorecard in the registry we own.
    # We do NOT invent scorecards for them (not our file to grow); we record the
    # honest count so nothing real is hidden.
    unscored_actives = sorted(w for w, a in per.items()
                              if a["messages"] > 0 and w not in active_wids_in_registry)

    out = {
        "ok": True,
        "schema": SCHEMA,
        "kind": "living_worker_scorecards",
        "honesty": ("Every live_* metric is counted directly from real worker "
                    "activity rows in qsb_floor_*_worker_activity.jsonl (and live "
                    "bus rows when present). Idle workers keep truthful zeroed "
                    "counters. No activity is fabricated for any worker."),
        "generated_ts": ts,
        "source_registry": "data/registries/qsb_worker_scorecards.json",
        "activity_sources": meta,
        "total_scorecards": len(live_scorecards),
        "live_active_scorecards": active_ct,
        "idle_scorecards": idle_ct,
        "active_workers_without_scorecard_count": len(unscored_actives),
        "active_workers_without_scorecard_sample": unscored_actives[:25],
        # carry the tower's real gate posture forward, unchanged
        "execution_allowed": base.get("execution_allowed", False),
        "advisory_only": base.get("advisory_only", True),
        "real_money_live_trading_enabled": base.get("real_money_live_trading_enabled", False),
        "scorecards": live_scorecards,
    }

    # atomic write of the companion live file
    tmp = LIVE_OUT.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, LIVE_OUT)

    if write_registry:
        # back up the static registry first (never overwrite without a backup)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bak = SCORECARDS.with_name(SCORECARDS.name + f".bak_{stamp}")
        if not bak.exists():
            with open(bak, "w") as f:
                json.dump(base, f, indent=2)
        # fold the live blocks back into the registry, preserving its wrapper
        base["scorecards"] = live_scorecards
        base["live_updated_ts"] = ts
        base["live_active_scorecards"] = active_ct
        base["idle_scorecards"] = idle_ct
        rtmp = SCORECARDS.with_suffix(".json.tmp")
        with open(rtmp, "w") as f:
            json.dump(base, f, indent=2)
        os.replace(rtmp, SCORECARDS)
        out["registry_backup"] = str(bak.relative_to(ROOT))
        out["registry_written"] = True

    # append-only F47 audit row
    try:
        with open(F47, "a") as f:
            f.write(json.dumps({
                "ts": ts,
                "kind": "worker_scorecard_live_update",
                "tool": "tools/qsb_worker_scorecard_updater.py",
                "active": active_ct,
                "idle": idle_ct,
                "total": len(live_scorecards),
                "unscored_actives": len(unscored_actives),
                "wrote_registry": bool(write_registry),
                "honesty": "metrics counted from real activity rows only; no fabrication",
            }) + "\n")
    except Exception:
        pass

    return out


def cmd_status() -> None:
    out = run(write_registry=False)
    print(f"[scorecards] total={out['total_scorecards']} "
          f"live_active={out['live_active_scorecards']} "
          f"idle={out['idle_scorecards']} "
          f"unscored_actives={out['active_workers_without_scorecard_count']}")
    print(f"  live file: {LIVE_OUT.relative_to(ROOT)}")
    for fs in out["activity_sources"]["perfloor_files"]:
        print(f"  src {fs['file']}: {fs['rows']} rows")


def cmd_show(wid: str) -> None:
    d = json.load(open(LIVE_OUT)) if LIVE_OUT.exists() else run()
    for s in d.get("scorecards", []):
        if s.get("worker_id") == wid:
            print(json.dumps({k: v for k, v in s.items()
                              if k.startswith("live_") or k in
                              ("worker_id", "name", "floor", "rank")}, indent=2))
            return
    print(f"no scorecard for {wid}")


def main() -> int:
    args = sys.argv[1:]
    if "--status" in args:
        cmd_status()
        return 0
    if "--show" in args:
        i = args.index("--show")
        cmd_show(args[i + 1] if i + 1 < len(args) else "")
        return 0
    write_registry = "--write-registry" in args
    out = run(write_registry=write_registry)
    print(f"[scorecards] wrote {LIVE_OUT.relative_to(ROOT)} "
          f"— active={out['live_active_scorecards']} idle={out['idle_scorecards']} "
          f"total={out['total_scorecards']}"
          + (f" — registry folded (backup {out.get('registry_backup')})"
             if write_registry else " (companion-only)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
