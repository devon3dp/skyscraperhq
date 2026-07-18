#!/usr/bin/env python3
"""Tests for the HQ dashboard chat-to-work bridge (Ross 2026-07-10).

Test 1 — greeting: 'hello' -> GREETING, no Task Council task.
Test 2 — task command: a mini task -> TASK_COMMAND, report written, LATEST
         copied, dashboard reply includes report path, task left OPEN.
(Test 3 — full live smoke via curl is run against the running dash separately.)
"""
import sys, json, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qsb_hq_chat_bridge as b
import qsb_council_tasks as qct

PASS, FAIL = [], []
def check(n, c, d=""):
    (PASS if c else FAIL).append(n)
    print(f"{'PASS' if c else 'FAIL'}  {n}" + (f"  — {d}" if d and not c else ""))

# isolate council log so the test doesn't touch real tasks
d = Path(tempfile.mkdtemp(prefix="bridge_"))
qct.LOG = d / "tasks.jsonl"; qct.SNAPSHOT = d / "snap.json"
# isolate report output
rep = Path(tempfile.mkdtemp(prefix="bridgerep_"))
b.DEFAULT_REPORT_DIR = rep
b.LATEST = rep / "LATEST_REPORT.txt"

# Test 1 — greeting
check("1_greeting_classified", b.classify("hello") == "GREETING")
check("1_greeting_is_not_task", b.classify("hey HQ") != "TASK_COMMAND")

# Test 2 — mini task command
MINI = """TASK TITLE:
Mini Dashboard Chat Bridge Test

Work from:
/vaults/nvme0/qsb_tower_v1

Run:
pwd
hostname
whoami

Write report to:
%s/MINI_DASHBOARD_CHAT_BRIDGE_TEST_REPORT.txt
""" % rep
check("2_task_classified", b.classify(MINI) == "TASK_COMMAND")
res = b.handle_task_command(MINI, received_via="claude_hq_dashboard_chat", message_id="test-123")
check("2_task_created", isinstance(res.get("task_id"), str) and res["task_id"].startswith("t_"),
      res.get("task_id"))
check("2_report_written", Path(res["report_path"]).exists(), res.get("report_path"))
check("2_latest_copied", Path(res["latest_report"]).exists())
check("2_reply_has_report_path", "MINI_DASHBOARD_CHAT_BRIDGE_TEST_REPORT" in res["dashboard_reply"])
# ran pwd/hostname/whoami
ran_cmds = {r["cmd"].lower() for r in res["ran"]}
check("2_ran_pwd_hostname_whoami",
      {"pwd", "hostname", "whoami"}.issubset(ran_cmds), ran_cmds)
check("2_commands_succeeded", all(r["ok"] for r in res["ran"] if r["cmd"].lower() in ("pwd","hostname","whoami")))
# task left OPEN (not done/closed) — no self-close
snap = qct.snapshot()
t = next((x for x in snap["tasks"] if x["id"] == res["task_id"]), None)
check("2_task_left_open", t is not None and t["state"] not in ("done", "closed"),
      t["state"] if t else "missing")
# received_via evidence attached
check("2_received_via_evidence",
      any("received_via=claude_hq_dashboard_chat" in (n.get("text","")) for n in (t.get("notes") or [])))
# report contains full message + final_status
rep_txt = Path(res["report_path"]).read_text()
check("2_report_preserves_message", "Mini Dashboard Chat Bridge Test" in rep_txt)
check("2_report_not_self_scored", "needs Ross/ChatGPT/verifier review" in rep_txt)

print("\n=== bridge: {}/{} passed ===".format(len(PASS), len(PASS)+len(FAIL)))
sys.exit(0 if not FAIL else 1)
