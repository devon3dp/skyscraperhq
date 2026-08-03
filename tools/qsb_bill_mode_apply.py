#!/usr/bin/env python3
"""
qsb_bill_mode_apply.py — apply Bill's MODE_SET beacons to the tower mode state.

Closes the relay loop for Ross's natural-language mode switch:

  Ross --("go to work mode")--> relay :8855 --> Bill's Mac responder
     -> responder recognises the phrase LOCALLY and posts back to the room:
        "MODE_SET:work — On it, Ross. Switching to WORK mode ..."
  This tool tails the room log, finds the NEWEST bill MODE_SET:<mode> beacon
  it hasn't applied yet, and calls qsb_bill_mode.set_mode(<mode>, set_by='bill').

So the switch is a genuine round-trip through Bill's OWN real responder — the tower
never guesses Bill's mode; Bill confirms it. Idempotent (tracks last applied beacon
by msg_id/ts). Honest: if Bill's Mac is offline no beacon appears and nothing changes.

Run once (e.g. from the concierge timer or ceo_task_worker tick):
    python3 tools/qsb_bill_mode_apply.py --once
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
REG = os.path.join(ROOT, "data", "registries")
ROOM = os.path.join(REG, "leadership_comms", "room.jsonl")
CURSOR = os.path.join(REG, "qsb_bill_mode_apply_cursor.json")

import qsb_bill_mode as MODE


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_cursor() -> dict:
    try:
        with open(CURSOR) as f:
            return json.load(f)
    except Exception:
        return {"last_applied_ts": "", "last_applied_msg_id": ""}


def _save_cursor(c: dict) -> None:
    with open(CURSOR, "w") as f:
        json.dump(c, f, indent=2)


def _room_rows():
    if not os.path.exists(ROOM):
        return []
    out = []
    with open(ROOM, errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _newest_beacon(rows, since_ts):
    """Newest bill MODE_SET beacon strictly newer than since_ts. Returns (mode,row)."""
    best = None
    for r in rows:
        if r.get("from") != "bill":
            continue
        body = (r.get("body") or "")
        if "MODE_SET:" not in body:
            continue
        ts = r.get("ts") or ""
        if since_ts and ts <= since_ts:
            continue
        token = body.split("MODE_SET:", 1)[1].strip().split()[0].strip().lower().rstrip("—-.,")
        if token in MODE.VALID_MODES:
            if best is None or ts > (best[1].get("ts") or ""):
                best = (token, r)
    return best


def apply_once(verbose=True) -> dict:
    cur = _load_cursor()
    rows = _room_rows()
    beacon = _newest_beacon(rows, cur.get("last_applied_ts", ""))
    if not beacon:
        if verbose:
            print("no new MODE_SET beacon from Bill; mode unchanged =", MODE.get_mode())
        return {"applied": False, "mode": MODE.get_mode()}
    mode, row = beacon
    prev = MODE.get_mode()
    st = MODE.set_mode(mode, set_by="bill",
                       reason=f"Bill confirmed via relay beacon {row.get('msg_id','')} at {row.get('ts','')}")
    cur["last_applied_ts"] = row.get("ts") or utc()
    cur["last_applied_msg_id"] = row.get("msg_id") or ""
    _save_cursor(cur)
    if verbose:
        print(f"applied Bill's mode switch: {prev} -> {mode} "
              f"(from beacon {row.get('msg_id','')} @ {row.get('ts','')})")
        print(json.dumps(st, indent=2))
    return {"applied": True, "from": prev, "to": mode, "beacon": row.get("msg_id"), "status": st}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="apply the newest unseen beacon and exit")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    apply_once(verbose=not a.quiet)
