#!/usr/bin/env python3
"""GATE 17 tests — Max 3 active tasks per CEO (Ross 2026-07-10).

Runs against an ISOLATED temp event-log so real council data is never touched.
7 cases per Ross's spec:
  1. CEO with 0 active tasks can claim.
  2. CEO with 2 active tasks can claim one more.
  3. CEO with 3 active tasks is blocked (blocked_task_cap).
  4. Done/closed/cancelled tasks do not count.
  5. Helpers cannot be used to bypass the cap.
  6. Ross override can bypass only if override_event is logged.
  7. Blocking task list is shown in the refusal.
"""
import sys, tempfile, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qsb_council_tasks as q

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))


def isolate():
    """Point the module at a fresh temp log+snapshot."""
    d = Path(tempfile.mkdtemp(prefix="gate17_"))
    q.LOG = d / "tasks.jsonl"
    q.SNAPSHOT = d / "snap.json"
    return d


def seed_active(actor, n, state="in_progress"):
    """Create n tasks already HELD+active by actor, bypassing the gate for setup
    (direct events, not claim())."""
    ids = []
    for i in range(n):
        tid = "t_" + f"{actor}{i}".ljust(10, "x")[:10]
        q._append_event({"ts": q.utc(), "event": "created", "task_id": tid,
                         "actor": "ross_knechtel", "title": f"seed {i}"})
        q._append_event({"ts": q.utc(), "event": "claimed", "task_id": tid, "actor": actor})
        if state != "claimed":
            q._append_event({"ts": q.utc(), "event": "updated", "task_id": tid,
                             "actor": actor, "state": state})
        ids.append(tid)
    return ids


def seed_done(actor, n):
    ids = []
    for i in range(n):
        tid = "t_done" + f"{actor}{i}".ljust(6, "x")[:6]
        q._append_event({"ts": q.utc(), "event": "created", "task_id": tid,
                         "actor": "ross_knechtel", "title": f"done {i}"})
        q._append_event({"ts": q.utc(), "event": "claimed", "task_id": tid, "actor": actor})
        q._append_event({"ts": q.utc(), "event": "done", "task_id": tid, "actor": actor})
        ids.append(tid)
    return ids


# 1. 0 active → can claim
isolate()
r = q.create("fresh", actor="ross_knechtel")
res = q.claim(r["task_id"], "hq_claude")
check("1_zero_active_can_claim", res.get("ok") is True, res)

# 2. 2 active → can claim a 3rd
isolate()
seed_active("tp_pip", 2)
r = q.create("third", actor="ross_knechtel")
res = q.claim(r["task_id"], "tp_pip")
check("2_two_active_can_claim_third", res.get("ok") is True, res)

# 3. 3 active → blocked
isolate()
seed_active("acer_cass", 3)
r = q.create("fourth", actor="ross_knechtel")
res = q.claim(r["task_id"], "acer_cass")
check("3_three_active_blocked",
      res.get("ok") is False and res.get("state") == "blocked_task_cap", res)

# 4. done tasks don't count → 3 done + 0 active can claim
isolate()
seed_done("hq_claude", 3)
r = q.create("after_done", actor="ross_knechtel")
res = q.claim(r["task_id"], "hq_claude")
check("4_done_tasks_dont_count", res.get("ok") is True, res)

# 5. helpers cannot be used to bypass → helper claim refused
isolate()
r = q.create("helperjob", actor="ross_knechtel")
res = q.claim(r["task_id"], "deepseek_coder")
check("5_helper_cannot_bypass",
      res.get("ok") is False and res.get("error") == "helpers_have_no_task_slots", res)

# 6. Ross override bypasses ONLY if logged
isolate()
seed_active("wren", 3)
r = q.create("overridejob", actor="ross_knechtel")
before = q.claim(r["task_id"], "wren")
q.ross_cap_override("wren", reason="test bypass")
after = q.claim(r["task_id"], "wren")
check("6_ross_override_only_if_logged",
      before.get("ok") is False and after.get("ok") is True,
      f"before={before.get('state')} after={after}")

# 7. refusal shows blocking task list
isolate()
ids = seed_active("tp_pip", 3)
r = q.create("blocked7", actor="ross_knechtel")
res = q.claim(r["task_id"], "tp_pip")
bt = res.get("blocking_tasks") or []
check("7_refusal_shows_blocking_list",
      len(bt) == 3 and all("id" in b and "state" in b for b in bt),
      f"blocking={bt}")

print("\n=== GATE 17: {}/{} passed ===".format(len(PASS), len(PASS) + len(FAIL)))
sys.exit(0 if not FAIL else 1)
