#!/usr/bin/env python3
"""20 tests for the sandbox worker runtime (Ross 2026-07-10). Nothing live touched."""
import sys, json, hashlib, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qsb_ceo_runtime_worker_sandbox as S

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LIVE_RUNTIME = ROOT / "tools/qsb_ceo_runtime.py"
LIVE_COUNCIL = ROOT / "data/registries/qsb_council_tasks.jsonl"
LIVE_TOWN = ROOT / "data/registries/qsb_town_square.jsonl"

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).exists() else None

PASS, FAIL = [], []
def check(n, c, d=""):
    (PASS if c else FAIL).append(n); print(f"{'PASS' if c else 'FAIL'}  {n}" + (f"  — {d}" if d and not c else ""))

# capture live shas BEFORE
before = {p: sha(p) for p in (LIVE_RUNTIME, LIVE_COUNCIL, LIVE_TOWN)}

# redirect sandbox sinks to temp so we don't touch even /tmp real ones
td = Path(tempfile.mkdtemp(prefix="wsbx_"))
S.SANDBOX_TOWN = td / "town.jsonl"; S.SANDBOX_COUNCIL = td / "council.jsonl"
S.SENDBACK = td / "sendback"; S.SENDBACK.mkdir()

tp = S.cfg("tp_pip"); ac = S.cfg("acer")

# 1-3 capabilities
cap = S.capabilities(tp)
check("01_capabilities_works", isinstance(cap, dict) and "allowed_commands" in cap)
check("02_says_hq_hosted", cap["hq_hosted"] is True)
check("03_physical_independent_false", cap["physical_independent"] is False)

# 4-5 intake
code, r = S.handle_intake(tp, {"task_id": "t_x1", "title": "demo", "requester": "ross", "report_path": str(S.SENDBACK/"r.txt")})
check("04_intake_accepts_valid", code == 200 and r["ok"])
code, r = S.handle_intake(tp, {"title": "no id", "requester": "ross", "report_path": "x"})
check("05_intake_rejects_missing_task_id", code == 400 and "task_id" in r.get("missing", []))

# 6 run allowed
oks = []
for cmd in ("hostname", "whoami", "date"):
    code, r = S.handle_run_readonly(tp, {"cmd": cmd}); oks.append(code == 200 and r["ok"])
check("06_run_allowed_hostname_whoami_date", all(oks))

# 7 reject raw shell
code, r = S.handle_run_readonly(tp, {"cmd": "ls -la; rm -rf /"})
check("07_reject_raw_shell", code == 400 and r["error"] == "not_in_readonly_whitelist")
# 8 reject sudo
code, r = S.handle_run_readonly(tp, {"cmd": "sudo reboot"})
check("08_reject_sudo", code == 400 and not r["ok"])
# 9 reject file edit
code, r = S.handle_run_readonly(tp, {"cmd": "echo hacked > /etc/passwd"})
check("09_reject_file_edit", code == 400 and not r["ok"])

# 10 report to approved path
code, r = S.handle_report(tp, {"task_id": "t_x1", "body": "hello"})
check("10_report_writes_approved_path", code == 200 and Path(r["report_path"]).exists()
      and str(r["report_path"]).startswith(str(S.SENDBACK.resolve())))
# 11 report rejects unsafe path
code, r = S.handle_report(tp, {"task_id": "t_x1", "body": "x", "path": "/etc/qsb_hack.txt"})
check("11_report_rejects_unsafe_path", code == 400 and r["error"] == "unsafe_path_rejected")

# 12 town square -> sandbox only
code, r = S.handle_town_square(tp, {"text": "hi from tp sandbox"})
check("12_town_square_sandbox_only", code == 200 and Path(S.SANDBOX_TOWN).exists()
      and r["sandbox_file"] == str(S.SANDBOX_TOWN))
# 13 council event -> sandbox only
code, r = S.handle_council_event(tp, {"task_id": "t_x1", "event": "intake_received", "text": "got it"})
check("13_council_event_sandbox_only", code == 200 and Path(S.SANDBOX_COUNCIL).exists())
# 14 council rejects done/closed/peer_signoff
bad = [S.handle_council_event(tp, {"event": e})[0] for e in ("done", "closed", "peer_signoff")]
check("14_council_rejects_terminal_events", all(x == 400 for x in bad))

# 15 cannot self-close
check("15_cannot_self_close", cap["can_self_close"] is False
      and S.handle_council_event(tp, {"event": "done"})[0] == 400)
# 16 cannot claim peer verifier
check("16_cannot_verify_peer", cap["can_verify_peer_ceo"] is False)
# 17 identities separate
check("17_identities_separate", tp["id"] == "tp_pip" and ac["id"] == "acer_cass" and tp["id"] != ac["id"])

# 18-20 nothing live changed
after = {p: sha(p) for p in (LIVE_RUNTIME, LIVE_COUNCIL, LIVE_TOWN)}
check("18_live_council_unchanged", before[LIVE_COUNCIL] == after[LIVE_COUNCIL])
check("19_live_town_square_unchanged", before[LIVE_TOWN] == after[LIVE_TOWN])
check("20_live_runtime_unchanged", before[LIVE_RUNTIME] == after[LIVE_RUNTIME])

print("\n=== worker sandbox: {}/{} passed ===".format(len(PASS), len(PASS)+len(FAIL)))
sys.exit(0 if not FAIL else 1)
