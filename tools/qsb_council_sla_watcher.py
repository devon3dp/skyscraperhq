#!/usr/bin/env python3
"""qsb_council_sla_watcher.py — GAP 3 fix.

Enforces R01 SLA (10-min task life). If a task is claimed and no note in 5 min
AND elapsed > 10 min, auto-return to open pool.

Runs as a daemon (or one-shot via --once). Emits reopens with actor=sla_watcher.
"""
import argparse, json, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
import qsb_council_tasks as tasks

STALE_SECS = 600      # 10 min
NOTE_SECS  = 300      # 5 min
POLL_SECS  = 60


def now(): return datetime.now(timezone.utc)


def parse_ts(s):
    try: return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except: return None


def scan_and_return_stale(dry=False):
    """Read board, find claimed-but-cold tasks, return to open pool."""
    events = []
    p = Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_council_tasks.jsonl")
    with p.open() as f:
        for line in f:
            try: events.append(json.loads(line))
            except: pass

    # Reconstruct: task_id -> {state, owner, last_activity_ts, claim_ts, notes[]}
    state = {}
    for ev in events:
        tid = ev.get("task_id")
        if not tid: continue
        e = ev.get("event", "")
        ts = parse_ts(ev.get("ts", ""))
        if not ts: continue
        st = state.setdefault(tid, {"claim_ts": None, "owner": None, "state": "proposed",
                                    "last_activity": ts, "sla_returned_at": None})
        st["last_activity"] = ts
        if e == "claimed":
            st["state"] = "in_progress"
            st["owner"] = ev.get("actor")
            st["claim_ts"] = ts
        elif e == "sandbox_passed":
            st["state"] = "awaiting_peer_signoff"
        elif e == "peer_signoff":
            v = ev.get("verdict", "approve")
            st["state"] = "in_progress" if v == "reject" else "signed"
        elif e == "done":
            st["state"] = "done"
        elif e == "reopened":
            st["state"] = "proposed"; st["owner"] = None; st["claim_ts"] = None
            if ev.get("actor") == "sla_watcher":
                st["sla_returned_at"] = ts
        elif e == "noted":
            pass  # keeps last_activity fresh

    # Find stale
    returned = []
    for tid, st in state.items():
        if st["state"] != "in_progress": continue
        if not st["claim_ts"]: continue
        age = (now() - st["claim_ts"]).total_seconds()
        idle = (now() - st["last_activity"]).total_seconds()
        # Never re-return the same task twice per SLA cycle (10min cooldown after last return)
        if st["sla_returned_at"] and (now() - st["sla_returned_at"]).total_seconds() < STALE_SECS:
            continue
        if age > STALE_SECS and idle > NOTE_SECS:
            returned.append({"task_id": tid, "owner": st["owner"], "age_s": int(age), "idle_s": int(idle)})
            if not dry:
                tasks.reopen(tid, "sla_watcher")
                tasks.note(tid, "sla_watcher",
                           f"R01 SLA auto-return — age={int(age)}s idle={int(idle)}s "
                           f"(was owned by {st['owner']}). Anyone can re-claim.")
    return returned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single scan, no loop")
    ap.add_argument("--dry-run", action="store_true", help="don't reopen, just print")
    args = ap.parse_args()
    if args.once:
        r = scan_and_return_stale(dry=args.dry_run)
        print(json.dumps({"returned": r, "ts": now().isoformat()}))
        return
    print(f"[sla_watcher] polling every {POLL_SECS}s. stale={STALE_SECS}s note_within={NOTE_SECS}s")
    while True:
        r = scan_and_return_stale(dry=args.dry_run)
        if r:
            for x in r:
                print(f"[sla_watcher] returned {x['task_id']} (was owned by {x['owner']}, age {x['age_s']}s, idle {x['idle_s']}s)")
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    main()
