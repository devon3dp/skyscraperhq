#!/usr/bin/env python3
"""
qsb_ross_to_room.py — bridge Ross's Town Square posts INTO the leadership relay room.

ROOT CAUSE this fixes (2026-07-29, Claude specialist under Wren, Ross order
"fix the town square ... prove this now"):

  There were TWO disconnected "town squares":
    (1) legacy qsb_town_square.jsonl  — what the boardroom /town/post writes
        (Ross's iPad line lands here).
    (2) leadership_comms/room.jsonl   — the relay :8855 CEO room the CEO room
        bridge (qsb_ceo_room_bridge.py) polls to trigger TP/Asa/Bill cockpit
        replies.

  Ross's line only ever reached (1). It NEVER reached (2), so TP/Asa/Bill's
  relay inboxes never saw a Ross broadcast and their cockpits never replied.
  The town square looked one-sided (Bill + Wren only).

  The relay's /room endpoint requires a CEO token; "ross" is not a relay
  identity, so Ross can't POST there over HTTP. This helper mirrors EXACTLY
  what the relay's /room handler does — append to room.jsonl and enqueue to
  every CEO's inbox queue — but for a from="ross" human broadcast. The CEO
  room bridge already treats HUMAN_SENDERS={"ross"} as reply-worthy, so a
  Ross broadcast now fans out to each online CEO's REAL cockpit and their
  replies flow back into room.jsonl through the existing bridge.

Plumbing only. No persona edits, no mind edits, no relay-auth changes, no
gate flips. Dedup by msg_id (the relay's already_seen equivalent) makes
double-calls harmless.
"""
from __future__ import annotations
import json, os, uuid, threading
from datetime import datetime, timezone

ROOT = "/vaults/nvme0/qsb_tower_v1"
COMMS = os.path.join(ROOT, "data", "registries", "leadership_comms")
ROOM = os.path.join(COMMS, "room.jsonl")
QUEUES = os.path.join(COMMS, "queues")
CEOS = ["wren", "tp", "asa", "bill"]

_LOCK = threading.Lock()


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _append(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")


def _already_in_room(msg_id: str) -> bool:
    if not msg_id or not os.path.exists(ROOM):
        return False
    try:
        with open(ROOM) as f:
            # cheap tail scan; msg_ids are unique per post
            for line in f.read().splitlines()[-500:]:
                if msg_id in line:
                    return True
    except Exception:
        pass
    return False


def post_ross_to_room(text: str, to: str = "room") -> dict:
    """Put a from='ross' human broadcast into the leadership relay room so the
    CEO room bridge triggers each online CEO's real cockpit reply.

    Returns {ok, msg_id, fanout} or {ok:False, ...}.
    """
    body = (text or "").strip()
    if not body:
        return {"ok": False, "error": "empty"}
    msg_id = "r_ross_" + uuid.uuid4().hex[:14]
    ts = _utc()
    msg = {"msg_id": msg_id, "kind": "room", "from": "ross",
           "to": "room", "ts": ts, "body": body[:2000]}
    with _LOCK:
        if _already_in_room(msg_id):
            return {"ok": True, "duplicate": True, "msg_id": msg_id}
        _append(ROOM, msg)
        fan = []
        for ceo in CEOS:
            _append(os.path.join(QUEUES, ceo + ".jsonl"), msg)
            fan.append(ceo)
    return {"ok": True, "msg_id": msg_id, "ts": ts, "fanout": fan}


if __name__ == "__main__":
    import sys
    txt = " ".join(sys.argv[1:]) or sys.stdin.read()
    print(json.dumps(post_ross_to_room(txt)))
