#!/usr/bin/env python3
"""Auth-guard tests for the sandbox worker runtime (Ross 2026-07-10).

Exercises dispatch_post() (the POST auth gate) with valid/wrong/missing token,
locked mode, GET-open, capabilities flag, and proves the token value never leaks
into any response. Also re-runs the POST happy-paths THROUGH the authed gate to
confirm the existing behaviour still works with a correct token.
"""
import sys, json, tempfile, io, contextlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qsb_ceo_runtime_worker_sandbox as S

PASS, FAIL = [], []
def check(n, c, d=""):
    (PASS if c else FAIL).append(n); print(f"{'PASS' if c else 'FAIL'}  {n}" + (f"  — {d}" if d and not c else ""))

# isolate sandbox sinks + report dir + a TEST token file (never the real secret)
td = Path(tempfile.mkdtemp(prefix="wauth_"))
S.SANDBOX_TOWN = td / "town.jsonl"; S.SANDBOX_COUNCIL = td / "council.jsonl"
S.SENDBACK = td / "sendback"; S.SENDBACK.mkdir()
TESTTOK = "TESTTOKEN_do_not_log_" + "abc123"
S.TOKEN_FILE = td / "token"; S.TOKEN_FILE.write_text(TESTTOK)

tp = S.cfg("tp_pip")
GOOD = {"task_id": "t1", "title": "demo", "requester": "ross", "report_path": str(S.SENDBACK / "r.txt")}

def dp(path, body, token):
    return S.dispatch_post(tp, path, body, token)

# 1-3 intake auth
check("01_intake_no_token_rejected", dp("/task/intake", GOOD, None)[0] == 403)
check("02_intake_wrong_token_rejected", dp("/task/intake", GOOD, "WRONG")[0] == 403)
check("03_intake_correct_token_accepted", dp("/task/intake", GOOD, TESTTOK)[0] == 200)

# 4-6 run_readonly auth
check("04_run_no_token_rejected", dp("/task/run_readonly", {"cmd": "hostname"}, None)[0] == 403)
check("05_run_wrong_token_rejected", dp("/task/run_readonly", {"cmd": "hostname"}, "X")[0] == 403)
c6, r6 = dp("/task/run_readonly", {"cmd": "hostname"}, TESTTOK)
check("06_run_correct_token_runs_whitelist", c6 == 200 and r6["ok"])

# 7-8 report auth
check("07_report_no_token_rejected", dp("/task/report", {"task_id": "t1", "body": "x"}, None)[0] == 403)
c8, r8 = dp("/task/report", {"task_id": "t1", "body": "x"}, TESTTOK)
check("08_report_correct_token_accepted", c8 == 200 and Path(r8["report_path"]).exists())

# 9-10 town square / council auth
check("09_town_square_no_token_rejected", dp("/task/town_square", {"text": "hi"}, None)[0] == 403)
check("10_council_event_no_token_rejected", dp("/task/council_event", {"event": "intake_received"}, None)[0] == 403)

# 11 GET works without token
check("11_get_health_no_token", S.auth_status()["post_auth_required"] is True and isinstance(S.capabilities(tp), dict))
# 12 capabilities reports post_auth_required=true
check("12_capabilities_post_auth_required", S.capabilities(tp)["post_auth_required"] is True)

# 13 token value never appears in any response/output
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    resps = [dp("/task/intake", GOOD, None), dp("/task/intake", GOOD, "WRONG"),
             dp("/task/intake", GOOD, TESTTOK), S.capabilities(tp), S.auth_status()]
blob = json.dumps(resps, default=str) + buf.getvalue()
check("13_token_never_leaks", TESTTOK not in blob)

# 14-15 locked mode when token file missing
S.TOKEN_FILE = td / "nonexistent_token"
check("14_missing_token_file_locked", S.auth_status()["post_auth_configured"] is False)
locked = [dp(p, b, TESTTOK)[1].get("error") for p, b in
          [("/task/intake", GOOD), ("/task/run_readonly", {"cmd": "hostname"}),
           ("/task/report", {"task_id": "t1", "body": "x"}),
           ("/task/town_square", {"text": "hi"}), ("/task/council_event", {"event": "intake_received"})]]
check("15_locked_mode_rejects_all_posts", all(e == "auth_not_configured" for e in locked))

# 16 existing 20 handler tests still pass (with correct token they route fine)
S.TOKEN_FILE = td / "token"   # restore
import subprocess
r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "test_qsb_ceo_runtime_worker_sandbox.py")],
                   capture_output=True, text=True)
check("16_existing_20_tests_still_pass", r.returncode == 0 and "20/20 passed" in r.stdout,
      r.stdout.splitlines()[-1] if r.stdout else r.stderr[:200])

print("\n=== auth guard: {}/{} passed ===".format(len(PASS), len(PASS)+len(FAIL)))
sys.exit(0 if not FAIL else 1)
