#!/usr/bin/env python3
"""GATE 19 / R108 team-liveness tests (Ross 2026-07-10). Isolated temp council log."""
import sys, time, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qsb_council_tasks as q

d = Path(tempfile.mkdtemp(prefix="g19_")); q.LOG = d / "t.jsonl"; q.SNAPSHOT = d / "s.json"
PASS, FAIL = [], []
def check(n, c, dd=""):
    (PASS if c else FAIL).append(n); print(f"{'PASS' if c else 'FAIL'}  {n}" + (f"  — {dd}" if dd and not c else ""))

now = time.time()
online = {"reachable": True, "identity": "tp_pip", "expected_id": "tp_pip", "last_heartbeat_ts": now}
stale  = {"reachable": True, "identity": "tp_pip", "expected_id": "tp_pip", "last_heartbeat_ts": now - 20*60}
unreach = {"reachable": False, "expected_id": "acer_cass"}
offline = {"host_down": True, "expected_id": "acer_cass"}
mismatch = {"reachable": True, "identity": "someone_else", "expected_id": "tp_pip", "last_heartbeat_ts": now}

# 1 online passes
check("01_online_node_passes", q.classify_liveness(online) == "ONLINE"
      and q.liveness_gate({"tp": "ONLINE"})["ok"] is True)
# 2 stale creates recovery task
check("02_stale_state", q.classify_liveness(stale) == "STALE")
r = q.create_recovery_task("tp_pip", state="STALE", detector="acer_cass")
check("02b_stale_recovery_task", r.get("ok") and r["task_id"].startswith("t_"))
# 3 unreachable creates recovery task
check("03_unreachable_state", q.classify_liveness(unreach) == "UNREACHABLE")
r = q.create_recovery_task("acer_cass", state="UNREACHABLE", detector="tp_pip")
check("03b_unreachable_recovery_task", r.get("ok"))
# 4 wrong identity => mismatch
check("04_identity_mismatch", q.classify_liveness(mismatch) == "IDENTITY_MISMATCH")
# 5 offline CEO cannot verify (gate blocks when verifier offline)
g = q.liveness_gate({"partner_tp": "ONLINE", "verifier_acer": "OFFLINE"})
check("05_offline_cannot_verify", g["ok"] is False and g["state"] == "blocked_node_offline"
      and "verifier_acer" in g["offline_nodes"])
# 6 offline CEO cannot count as partner
g = q.liveness_gate({"partner_acer": "UNREACHABLE"})
check("06_offline_not_partner", g["ok"] is False and "partner_acer" in g["offline_nodes"])
# 7 Wren can verify outage observability (wren is a valid detector of an outage)
r = q.create_recovery_task("receptionist_pi", state="OFFLINE", detector="wren",
                           evidence="wren observed no heartbeat")
check("07_wren_flags_outage", r.get("ok"))
# 8 Wren cannot replace a CEO — a task needing a CEO partner with only Wren present
#    still blocks (Wren is not counted as the online CEO partner).
g = q.liveness_gate({"ceo_partner": "OFFLINE", "wren_observer": "ONLINE"})
check("08_wren_cannot_replace_ceo", g["ok"] is False and "ceo_partner" in g["offline_nodes"])
# 9 recovered node updates state
check("09_recovered_state_valid", "RECOVERED" in q.LIVENESS_STATES
      and q.liveness_gate({"n": "RECOVERED"})["ok"] is False)  # RECOVERED != ONLINE yet
# 10 no fake agreement from silence — an all-silent node set never returns ok
check("10_silence_not_agreement", q.liveness_gate({"a": "STALE", "b": "OFFLINE"})["ok"] is False)

print("\n=== GATE 19: {}/{} passed ===".format(len(PASS), len(PASS)+len(FAIL)))
sys.exit(0 if not FAIL else 1)
