#!/usr/bin/env python3
"""qsb_timeclock.py — stamp workers in / out, summarize shifts.

Ross 2026-06-13: "we need a time clock, so workers can stamp in and stamp out"

Ledger: data/registries/qsb_timeclock_ledger.jsonl
Each row: {"ts","worker_id","kind":"in"|"out","floor","note"}

CLI:
  python3 tools/qsb_timeclock.py in  <worker_id> [--floor N] [--note "..."]
  python3 tools/qsb_timeclock.py out <worker_id> [--floor N] [--note "..."]
  python3 tools/qsb_timeclock.py status [--worker WID]
  python3 tools/qsb_timeclock.py summary [--since 2026-06-13]
"""
from __future__ import annotations
import argparse, json, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LEDGER = ROOT / "data/registries/qsb_timeclock_ledger.jsonl"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append(row: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(row) + "\n")


def read_all() -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    with LEDGER.open() as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out


def stamp_in(worker_id: str, floor=None, note="") -> dict:
    row = {"ts": utcnow(), "worker_id": worker_id, "kind": "in",
           "floor": floor, "note": note}
    append(row)
    return row


def stamp_out(worker_id: str, floor=None, note="") -> dict:
    row = {"ts": utcnow(), "worker_id": worker_id, "kind": "out",
           "floor": floor, "note": note}
    append(row)
    return row


def status(worker_id: str | None = None) -> dict:
    """Return who's currently on-shift (last event was 'in', no later 'out')."""
    by_w: dict[str, dict] = {}
    for row in read_all():
        wid = row["worker_id"]
        if worker_id and wid != worker_id:
            continue
        by_w[wid] = row  # last wins (ledger is append-only)
    on = {w: r for w, r in by_w.items() if r.get("kind") == "in"}
    off = {w: r for w, r in by_w.items() if r.get("kind") == "out"}
    return {
        "on_shift_count": len(on),
        "off_shift_count": len(off),
        "on_shift": [{"worker_id": w, "since": r["ts"], "floor": r.get("floor")}
                     for w, r in on.items()],
    }


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def summary(since: str | None = None) -> dict:
    """Hours-worked per worker since a given UTC date (YYYY-MM-DD)."""
    cutoff = None
    if since:
        cutoff = datetime.fromisoformat(since + "T00:00:00+00:00")
    pairs: dict[str, list] = defaultdict(list)
    for row in read_all():
        ts = _parse_ts(row["ts"])
        if cutoff and ts < cutoff:
            continue
        pairs[row["worker_id"]].append((ts, row["kind"]))
    out = []
    for wid, events in pairs.items():
        events.sort()
        seconds = 0.0
        opened = None
        for ts, kind in events:
            if kind == "in":
                opened = ts
            elif kind == "out" and opened:
                seconds += (ts - opened).total_seconds()
                opened = None
        if opened:  # still on shift — count up to now
            seconds += (datetime.now(timezone.utc) - opened).total_seconds()
        out.append({"worker_id": wid,
                    "hours": round(seconds / 3600.0, 2),
                    "still_on_shift": opened is not None})
    out.sort(key=lambda r: -r["hours"])
    return {"since": since or "all_time", "workers": out}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_in = sub.add_parser("in")
    p_in.add_argument("worker_id")
    p_in.add_argument("--floor", type=int)
    p_in.add_argument("--note", default="")

    p_out = sub.add_parser("out")
    p_out.add_argument("worker_id")
    p_out.add_argument("--floor", type=int)
    p_out.add_argument("--note", default="")

    p_st = sub.add_parser("status")
    p_st.add_argument("--worker")

    p_su = sub.add_parser("summary")
    p_su.add_argument("--since", help="YYYY-MM-DD UTC")

    args = ap.parse_args()
    if args.cmd == "in":
        print(json.dumps(stamp_in(args.worker_id, args.floor, args.note), indent=2))
    elif args.cmd == "out":
        print(json.dumps(stamp_out(args.worker_id, args.floor, args.note), indent=2))
    elif args.cmd == "status":
        print(json.dumps(status(args.worker), indent=2))
    elif args.cmd == "summary":
        print(json.dumps(summary(args.since), indent=2))


if __name__ == "__main__":
    main()
