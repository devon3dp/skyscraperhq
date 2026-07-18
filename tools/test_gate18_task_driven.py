#!/usr/bin/env python3
"""GATE 18 tests — Task-driven work only (Ross 2026-07-10).

Isolated temp log; real council data untouched. 7 cases:
  1. code edit without task_id is blocked
  2. dashboard edit without task_id is blocked
  3. service action without task_id is blocked
  4. helper work without parent task_id is blocked
  5. Ross direct emergency override works only with override_event
  6. read-only audit allowed only when task_class=audit or smoke_test
  7. valid task_id + intake + owner + partner allows work
"""
import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qsb_council_tasks as q

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))


def isolate():
    d = Path(tempfile.mkdtemp(prefix="gate18_"))
    q.LOG = d / "tasks.jsonl"
    q.SNAPSHOT = d / "snap.json"
    return d


def make_task(owner=None, partner=None, state="in_progress"):
    tid = q.create("work", actor="ross_knechtel")["task_id"]
    if owner:
        q._append_event({"ts": q.utc(), "event": "claimed", "task_id": tid, "actor": owner})
    if partner:
        q._append_event({"ts": q.utc(), "event": "assigned", "task_id": tid,
                         "actor": owner or "ross_knechtel", "assignee": partner})
    if state and state != "claimed":
        q._append_event({"ts": q.utc(), "event": "updated", "task_id": tid,
                         "actor": owner or "ross_knechtel", "state": state})
    return tid


# 1. code edit without task_id → blocked
isolate()
r = q.work_authorization("hq_claude", task_id=None)
check("1_code_edit_no_task_blocked",
      not r["ok"] and r.get("state") == "blocked_no_task", r)

# 2. dashboard edit without task_id → blocked (same envelope)
isolate()
r = q.work_authorization("tp_pip", task_id=None)
check("2_dashboard_edit_no_task_blocked",
      not r["ok"] and r.get("state") == "blocked_no_task", r)

# 3. service action without task_id → blocked
isolate()
r = q.work_authorization("acer_cass", task_id=None)
check("3_service_action_no_task_blocked",
      not r["ok"] and r.get("state") == "blocked_no_task", r)

# 4. helper work without parent task_id → blocked
isolate()
r = q.work_authorization("deepseek_coder", is_helper=True, parent_task_id=None)
check("4_helper_no_parent_blocked",
      not r["ok"] and r.get("error") == "helper_no_parent_task", r)

# 5. Ross emergency override works ONLY with a logged override_event
isolate()
tid = make_task(owner="hq_claude", partner=None, state="in_progress")  # no partner
before = q.work_authorization("hq_claude", task_id=tid)  # blocked (no partner)
q.ross_work_override("hq_claude", reason="emergency pi rebuild")
after = q.work_authorization("hq_claude", task_id=tid)
check("5_ross_override_only_with_event",
      (not before["ok"]) and after["ok"] is True,
      f"before={before.get('error')} after={after}")

# 6. read-only audit allowed only for audit/smoke_test class
isolate()
tid = make_task(owner="hq_claude", state="in_progress")
bad = q.work_authorization("hq_claude", task_id=tid, readonly=True, task_class="build")
good = q.work_authorization("hq_claude", task_id=tid, readonly=True, task_class="audit")
check("6_readonly_only_audit_class",
      (not bad["ok"]) and good["ok"] is True,
      f"bad={bad.get('error')} good={good}")

# 7. valid task_id + owner + partner allows work
isolate()
tid = make_task(owner="hq_claude", partner="tp_pip", state="in_progress")
r = q.work_authorization("hq_claude", task_id=tid)
check("7_valid_owner_partner_allows",
      r["ok"] is True and r.get("partner") == "tp_pip", r)

print("\n=== GATE 18: {}/{} passed ===".format(len(PASS), len(PASS) + len(FAIL)))
sys.exit(0 if not FAIL else 1)
