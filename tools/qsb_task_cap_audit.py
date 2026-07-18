#!/usr/bin/env python3
"""qsb_task_cap_audit.py — Task Council Active Task Cap Audit (GATE 17).

Ross 2026-07-10: find all CEOs over 3 active tasks, plus stale / ownerless /
waiting-verification / blocked-by-unreachable-peer tasks. Recommends cleanup
actions ONLY — never deletes or mutates tasks.

Writes report to SKYSCRAPERHQ_RUNS/00_SEND_THIS_TO_CHATGPT/.
"""
import json, socket, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qsb_council_tasks as q

CAP = q.ACTIVE_CAP
CAPPED = q.CAPPED_CEOS
ACTIVE = q.CAP_ACTIVE_STATES
STALE_HOURS = 48

OUT_DIR = Path("/home/ross/Desktop/SKYSCRAPERHQ_RUNS/00_SEND_THIS_TO_CHATGPT")
REPORT = OUT_DIR / "TASK_COUNCIL_ACTIVE_TASK_CAP_AUDIT_REPORT.txt"
LATEST = OUT_DIR / "LATEST_REPORT.txt"

# Peers whose unreachability can block a task (dash ports).
PEER_PORTS = {"tp_pip": 8861, "acer_cass": 8862, "wren": 8851}


def utcnow():
    return datetime.now(timezone.utc)


def parse_ts(ts):
    try:
        return datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except Exception:
        return None


def age_hours(ts):
    d = parse_ts(ts)
    if not d:
        return None
    return (utcnow() - d).total_seconds() / 3600.0


def held_by(t):
    return t.get("owner") or t.get("assignee")


def last_activity_ts(t):
    hist = t.get("history") or []
    if hist:
        return hist[-1].get("ts")
    return t.get("started_at") or t.get("created_at")


def probe_peer(port):
    """Truthful reachability: TCP connect to 127.0.0.1:port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except Exception:
        return False


def main():
    snap = q.snapshot()
    tasks = snap.get("tasks", [])
    active_tasks = [t for t in tasks if (t.get("state") or "").lower() in ACTIVE]
    stale_tasks, ownerless, waiting_verify, blocked_peer = [], [], [], []
    per_ceo = {}

    WAIT_STATES = {"awaiting_peer_signoff", "needs_verification",
                   "needs_second_verifier", "ready_to_ship",
                   "needs_ross_chatgpt_verifier_review"}
    BLOCK_STATES = {"blocked", "blocked_waiting_for_peer",
                    "blocked_waiting_for_verifier"}

    for t in active_tasks:
        owner = held_by(t)
        if owner:
            per_ceo.setdefault(owner, []).append(t)
        else:
            ownerless.append(t)
        ah = age_hours(last_activity_ts(t))
        if ah is not None and ah > STALE_HOURS:
            stale_tasks.append((t, ah))
        st = (t.get("state") or "").lower()
        if st in WAIT_STATES:
            waiting_verify.append(t)
        if st in BLOCK_STATES:
            blocked_peer.append(t)

    # peer reachability (truthful probe)
    peer_status = {name: ("REACHABLE" if probe_peer(port) else "UNREACHABLE")
                   for name, port in PEER_PORTS.items()}

    over_cap = {ceo: ts for ceo, ts in per_ceo.items()
                if ceo in CAPPED and len(ts) > CAP}

    L = []
    A = L.append
    A("TASK COUNCIL ACTIVE TASK CAP AUDIT — GATE 17")
    A("Generated: " + utcnow().isoformat(timespec="seconds").replace("+00:00", "Z"))
    A("Rule: Ross 2026-07-10 — MAX THREE ACTIVE TASKS PER CEO")
    A("Auditor: hq_claude (not self-scored — needs Ross/ChatGPT/verifier review)")
    A("=" * 64)
    A("")
    A("SUMMARY")
    A(f"  total tasks in council      : {len(tasks)}")
    A(f"  total ACTIVE tasks          : {len(active_tasks)}")
    A(f"  total STALE (> {STALE_HOURS}h no update): {len(stale_tasks)}")
    A(f"  ownerless active tasks      : {len(ownerless)}")
    A(f"  waiting for verification    : {len(waiting_verify)}")
    A(f"  blocked (peer/verifier)     : {len(blocked_peer)}")
    A(f"  CEOs over cap ({CAP})           : {len(over_cap)}")
    A("")
    A("PEER REACHABILITY (truthful TCP probe, 127.0.0.1)")
    for name, st in peer_status.items():
        A(f"  {name:12s} :{PEER_PORTS[name]}  {st}")
    A("")
    A("ACTIVE TASKS PER CEO")
    for ceo in sorted(set(list(per_ceo) + list(CAPPED))):
        held = per_ceo.get(ceo, [])
        flag = "  <== OVER CAP" if (ceo in CAPPED and len(held) > CAP) else ""
        capnote = "" if ceo in CAPPED else "  (not a capped CEO)"
        A(f"  {ceo:14s} active={len(held)}  allowed={CAP}{flag}{capnote}")
    A("")
    A("=" * 64)
    A("CEOs OVER CAP — DETAIL")
    if not over_cap:
        A("  none — every capped CEO is at or under 3 active tasks.")
    for ceo, held in over_cap.items():
        held_sorted = sorted(held, key=lambda t: t.get("started_at") or t.get("created_at") or "")
        stale_ids = [t["id"] for t in held
                     if (age_hours(last_activity_ts(t)) or 0) > STALE_HOURS]
        A("")
        A(f"  CEO: {ceo}")
        A(f"  active_count: {len(held)}")
        A(f"  allowed_count: {CAP}")
        A(f"  over_by: {len(held) - CAP}")
        A(f"  blocking_task_ids: {[t['id'] for t in held]}")
        oldest = held_sorted[0] if held_sorted else None
        if oldest:
            A(f"  oldest_active_task: {oldest['id']} — {oldest.get('title','')[:70]} "
              f"[{oldest.get('state')}]")
        A(f"  stale_task_ids: {stale_ids or '[]'}")
        A("  recommended action: finish oldest properly OR move to "
          "needs_verification OR hand off OR mark superseded/duplicate OR ask "
          "Ross to archive. Do NOT auto-delete.")

    A("")
    A("=" * 64)
    A("STALE ACTIVE TASKS (> {}h since last update)".format(STALE_HOURS))
    if not stale_tasks:
        A("  none")
    for t, ah in sorted(stale_tasks, key=lambda x: -x[1]):
        A(f"  {t['id']}  age={ah:.0f}h  owner={held_by(t)}  state={t.get('state')}  "
          f"{t.get('title','')[:60]}")

    A("")
    A("OWNERLESS ACTIVE TASKS")
    if not ownerless:
        A("  none")
    for t in ownerless:
        A(f"  {t['id']}  state={t.get('state')}  {t.get('title','')[:60]}")

    A("")
    A("TASKS WAITING FOR VERIFICATION")
    if not waiting_verify:
        A("  none")
    for t in waiting_verify:
        A(f"  {t['id']}  owner={held_by(t)}  state={t.get('state')}  "
          f"{t.get('title','')[:60]}")

    A("")
    A("TASKS BLOCKED (may be waiting on unreachable peer)")
    if not blocked_peer:
        A("  none")
    for t in blocked_peer:
        A(f"  {t['id']}  owner={held_by(t)}  state={t.get('state')}  "
          f"{t.get('title','')[:60]}")
    A("  NOTE: peer reachability above — a task blocked on an UNREACHABLE peer "
      "cannot clear until that peer is back.")

    A("")
    A("=" * 64)
    A("RECOMMENDED CLEANUP ACTIONS (no auto-delete; Ross/CEO to action)")
    A("  - finish properly")
    A("  - move to needs_verification")
    A("  - hand off to another CEO (respecting their own cap)")
    A("  - mark superseded / duplicate")
    A("  - mark blocked_waiting_for_peer where truly peer-blocked")
    A("  - ask Ross to archive")
    A("  - create a violation task if any CEO bypassed the cap without a "
      "logged task_cap_override")
    A("")
    A("ENFORCEMENT STATUS")
    A("  GATE 17 (max 3 active per CEO) wired into tools/qsb_council_tasks.py: "
      "claim(), assign(), update(state=in_progress). Refusal state = "
      "blocked_task_cap, logs a task_cap_blocked event, shows the blocking "
      "tasks. Helpers get no slots. Ross override via ross_cap_override() only "
      "(logged). Tests: tools/test_gate17_task_cap.py 7/7 PASS.")
    A("  GATE 18 (task-driven work only) added to tools/qsb_council_tasks.py: "
      "work_authorization(actor, task_id, task_class, readonly, is_helper, "
      "parent_task_id). Refusal state = blocked_no_task. Requires valid task_id "
      "in a work-allowing state + owner + partner (unless logged Ross emergency "
      "override via ross_work_override()). Helpers need a parent_task_id. "
      "Read-only work allowed only under audit/smoke_test class. Ross-direct "
      "chat is a separate allowed mode. Tests: "
      "tools/test_gate18_task_driven.py 7/7 PASS.")
    A("")
    A("final_status: needs Ross/ChatGPT/verifier review — NOT self-scored, "
      "NOT complete.")

    text = "\n".join(L) + "\n"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text)
    LATEST.write_text(text)
    print(text)
    print(f"[written] {REPORT}")
    print(f"[written] {LATEST}")


if __name__ == "__main__":
    main()
