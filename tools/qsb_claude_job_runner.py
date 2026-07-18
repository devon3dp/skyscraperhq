#!/usr/bin/env python3
"""
QSB CLAUDE JOB RUNNER — leashed, governed execution  (action_id=WREN-GOVERNOR-LEVEL2)

Runs a governed job ONLY from an approved immutable packet. It captures before/after
state, detects any change OUTSIDE the approved scope or in SAFETY_DENY paths, FREEZES
on violation, runs the deterministic verifier, and NEVER lets Claude approve/verify/
close its own job. Final acceptance is Ross's alone.

This runner does NOT contain an arbitrary shell. A job's "worker" is an explicit,
recorded command from an allow-listed class. Claude may not edit the policy, the
verifier, prior evidence, or this runner's leash during a governed job.

CLI:
  python3 tools/qsb_claude_job_runner.py --packet <packet.json>            # run an approved packet
  python3 tools/qsb_claude_job_runner.py --new-packet ... (helper to draft, stays DRAFT/AWAITING_ROSS)
"""
import argparse, json, hashlib, subprocess, time, os
from datetime import datetime, timezone
from pathlib import Path

_SELF = Path(__file__).resolve()
# When installed as the TRUSTED leash under /etc/qsb-governor (root-owned parent),
# __file__.parent.parent would resolve to /etc — wrong. Pin the tower ROOT and read
# the policy/verifier from the trusted dir beside this file. Content is byte-identical
# to the project copies (verified by checksum), so packet checksums still match.
if str(_SELF).startswith("/etc/qsb-governor"):
    TRUSTED_DIR = _SELF.parent
    ROOT = Path("/vaults/nvme0/qsb_tower_v1")
    POLICY = TRUSTED_DIR / "wren_governor_policy.yaml"
    VERIFIER = TRUSTED_DIR / "qsb_governor_verifier.py"
else:
    ROOT = _SELF.parent.parent
    POLICY = ROOT / "config/wren_governor_policy.yaml"
    VERIFIER = ROOT / "tools/qsb_governor_verifier.py"
REG = ROOT / "data/registries"
LEDGER = REG / "qsb_governor_evidence.jsonl"
SAFETY_DENY = ["CLAUDE.md", "config/wren_governor_policy.yaml", "tools/qsb_governor_verifier.py",
               "tools/qsb_claude_job_runner.py", "floors/floor_28_security_department/vault/", ".env"]

STATES = ["DRAFT", "AWAITING_ROSS", "APPROVED", "READY", "RUNNING", "FROZEN", "EVIDENCE_SUBMITTED",
          "VERIFYING", "CONTRADICTION", "READY_FOR_ROSS", "REJECTED", "ACCEPTED_BY_ROSS", "ROLLED_BACK"]
ALLOWED = {
    "DRAFT": {"AWAITING_ROSS", "REJECTED"}, "AWAITING_ROSS": {"APPROVED", "REJECTED"},
    "APPROVED": {"READY", "REJECTED", "FROZEN"}, "READY": {"RUNNING", "FROZEN"},
    "RUNNING": {"EVIDENCE_SUBMITTED", "FROZEN", "CONTRADICTION"}, "FROZEN": {"REJECTED", "READY_FOR_ROSS", "ROLLED_BACK"},
    "EVIDENCE_SUBMITTED": {"VERIFYING", "FROZEN"}, "VERIFYING": {"READY_FOR_ROSS", "CONTRADICTION", "FROZEN"},
    "CONTRADICTION": {"READY_FOR_ROSS", "FROZEN"}, "READY_FOR_ROSS": {"ACCEPTED_BY_ROSS", "REJECTED", "FROZEN"},
    "REJECTED": set(), "ACCEPTED_BY_ROSS": set(), "ROLLED_BACK": set(),
}
# actors that may NEVER move a job into ACCEPTED_BY_ROSS or READY_FOR_ROSS improperly
def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(p):
    # cage-fix 2026-07-17: skip unreadable files (e.g. browser session cache owned by
    # ross) with a stable sentinel instead of crashing the whole governed job.
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).exists() else None
    except (PermissionError, OSError):
        return "UNREADABLE"


def _ledger_last_hash():
    if LEDGER.exists() and LEDGER.read_text().strip():
        return json.loads(LEDGER.read_text().splitlines()[-1]).get("current_event_hash", "GENESIS")
    return "GENESIS"


CAGE_EVIDENCE = None  # set to a job-local path when running as the caged identity


def ledger_append(ev):
    ev.setdefault("ts", _utc())
    ev["previous_event_hash"] = _ledger_last_hash()
    ev["current_event_hash"] = hashlib.sha256((ev["previous_event_hash"] + json.dumps(ev, sort_keys=True)).encode()).hexdigest()
    # The caged identity CANNOT write the governor ledger (by design). It records
    # evidence to its own job workspace; the governor (as Ross) ingests it afterward.
    try:
        with open(LEDGER, "a") as f:
            f.write(json.dumps(ev) + "\n")
    except (PermissionError, OSError):
        if CAGE_EVIDENCE:
            with open(CAGE_EVIDENCE, "a") as f:
                f.write(json.dumps({**ev, "sink": "cage_job_evidence (governor ledger not writable by caged identity)"}) + "\n")
    return ev["current_event_hash"]


def transition(job, new_state, actor):
    old = job["state"]
    if new_state not in ALLOWED.get(old, set()):
        ledger_append({"event_id": "transition_denied", "task_id": job["job_id"], "actor": actor, "role": "runner",
                       "claim": "%s -> %s" % (old, new_state), "result": "STATE_TRANSITION_DENIED"})
        return {"ok": False, "error": "STATE_TRANSITION_DENIED", "from": old, "to": new_state}
    # a governed AI actor may never self-accept
    if new_state == "ACCEPTED_BY_ROSS" and actor != "ross":
        ledger_append({"event_id": "self_accept_blocked", "task_id": job["job_id"], "actor": actor, "role": "runner",
                       "result": "STATE_TRANSITION_DENIED", "claim": "non-Ross actor tried ACCEPTED_BY_ROSS"})
        return {"ok": False, "error": "ONLY_ROSS_ACCEPTS"}
    job["state"] = new_state
    return {"ok": True, "state": new_state}


def snapshot(paths):
    # cage-fix 2026-07-17: skip volatile / non-cage files (browser session cache,
    # pycache, git, backups) so watching broad paths like 'tools' does not crash or
    # raise false out-of-scope alarms from unrelated churn.
    _skip = ("whatsapp_inbound/auth_data", "__pycache__", "/.git/", ".bak")
    snap = {}
    for base in paths:
        b = ROOT / base
        if b.is_dir():
            for f in b.rglob("*"):
                if f.is_file():
                    rel = str(f.relative_to(ROOT))
                    if any(sk in rel for sk in _skip):
                        continue
                    snap[rel] = _sha(f)
        elif b.exists():
            snap[base] = _sha(b)
    return snap


def run_worker(cmd_class, cmd, permitted_paths):
    """Execute an allow-listed worker command class only. No arbitrary shell from web."""
    ALLOW = {"noop", "controlled_write", "read_report", "claude_chat"}
    if cmd_class not in ALLOW:
        return {"ok": False, "error": "command class not allow-listed: " + cmd_class}
    if cmd_class == "noop":
        return {"ok": True, "note": "read-only job — no write performed by runner"}
    if cmd_class == "claude_chat":
        # CHAT_ONLY Claude Max via `claude -p`: NO tools, NO MCP, NO API key. Output only
        # to the approved job output dir. The subprocess inherits the caged identity.
        prompt = str(cmd.get("prompt", ""))[:4000]
        out_rel = cmd.get("output_path")
        target = ROOT / out_rel
        if not any(str(target).startswith(str(ROOT / p)) for p in permitted_paths):
            return {"ok": False, "error": "OUT_OF_SCOPE output refused: " + str(out_rel)}
        home = os.environ.get("HOME", "/var/lib/claude_runner")
        env = {"HOME": home, "PATH": "/usr/local/bin:/usr/bin:/bin",
               "CLAUDE_CONFIG_DIR": home + "/.claude", "TERM": "dumb"}
        cmd_v = ["/usr/bin/claude", "-p", prompt, "--allowed-tools", "", "--strict-mcp-config", "--output-format", "text"]
        try:
            r = subprocess.run(cmd_v, env=env, capture_output=True, text=True, timeout=int(cmd.get("timeout", 180)))
        except Exception as e:
            return {"ok": False, "error": "claude -p failed: " + type(e).__name__ + ":" + str(e)[:120]}
        resp = (r.stdout or "").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(resp)
        return {"ok": bool(resp) and r.returncode == 0, "wrote": out_rel, "returncode": r.returncode,
                "response_chars": len(resp), "response_preview": resp[:300],
                "stderr_tail": (r.stderr or "")[-160:], "auth": "SUBSCRIPTION_OAUTH", "api_key_present": False,
                "command": "claude -p --allowed-tools '' --strict-mcp-config --output-format text (tools+MCP disabled)"}
    if cmd_class == "controlled_write":
        # cmd = {"path": <rel under a permitted dir>, "content": <exact>}
        rel = cmd.get("path", ""); content = cmd.get("content", "")
        target = ROOT / rel
        in_scope = any(str(target).startswith(str(ROOT / p)) for p in permitted_paths)
        if not in_scope:
            return {"ok": False, "error": "OUT_OF_SCOPE write refused: " + rel}
        if any(rel.startswith(d) or d in rel for d in SAFETY_DENY):
            return {"ok": False, "error": "SAFETY_DENY: " + rel}
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            Path(str(target) + ".bak_governor").write_bytes(target.read_bytes())
        target.write_text(content)
        return {"ok": True, "wrote": rel, "sha": _sha(target)}
    return {"ok": False, "error": "unhandled"}


def run_packet(packet_path):
    global CAGE_EVIDENCE
    job = json.loads(Path(packet_path).read_text())
    jid = job.get("job_id", "job")
    job.setdefault("state", "APPROVED")
    ws = job.get("job_workspace")
    if ws:
        ev_dir = Path(ws) / "evidence"
        try:
            ev_dir.mkdir(parents=True, exist_ok=True)
            CAGE_EVIDENCE = str(ev_dir / "cage_evidence.jsonl")
        except Exception:
            CAGE_EVIDENCE = None
    # ---- Phase 3 gate checks ----
    checks = {"policy_sha": _sha(POLICY), "verifier_sha": _sha(VERIFIER)}
    fail = []
    if job.get("policy_checksum") and job["policy_checksum"] != checks["policy_sha"]:
        fail.append("policy checksum mismatch")
    if job.get("verifier_checksum") and job["verifier_checksum"] != checks["verifier_sha"]:
        fail.append("verifier checksum mismatch")
    # recompute packet hash over the immutable fields
    core = {k: job[k] for k in job if k not in ("state", "packet_hash")}
    calc_hash = hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()
    if job.get("packet_hash") and job["packet_hash"] != calc_hash:
        fail.append("packet hash mismatch (packet tampered)")
    if job.get("approving_actor") != "ross":
        fail.append("not Ross-approved")
    if fail:
        ledger_append({"event_id": "gate_fail", "task_id": jid, "actor": "runner", "role": "runner", "result": "BLOCKED", "claim": ";".join(fail)})
        return {"job_id": jid, "state": "REJECTED", "gate": "FAILED", "reasons": fail}
    transition(job, "READY", "wren"); transition(job, "RUNNING", "wren")
    ledger_append({"event_id": "job_start", "task_id": jid, "actor": "claude_hq", "role": "governed",
                   "claim": job.get("ross_instruction", "")[:120], "result": "RUNNING", "risk": job.get("risk_level")})
    before = snapshot(job.get("permitted_paths", []) + job.get("watch_paths", []))
    # ---- run each worker step; freeze on any refusal ----
    results = []
    for step in job.get("worker_steps", []):
        r = run_worker(step.get("class"), step.get("cmd", {}), job.get("permitted_paths", []))
        results.append({"step": step.get("label", step.get("class")), **r})
        if not r.get("ok"):
            transition(job, "FROZEN", "runner")
            ledger_append({"event_id": "freeze_out_of_scope", "task_id": jid, "actor": "runner", "role": "runner",
                           "result": "FROZEN", "claim": r.get("error")})
    after = snapshot(job.get("permitted_paths", []) + job.get("watch_paths", []))
    # ---- out-of-scope change detection across watch_paths ----
    changed = sorted(set([k for k in after if before.get(k) != after.get(k)] + [k for k in before if k not in after]))
    permitted = job.get("permitted_paths", [])
    out_of_scope = [c for c in changed if not any(c.startswith(p) for p in permitted)]
    forbidden = [c for c in changed if any(c.startswith(d) or d in c for d in SAFETY_DENY)]
    if out_of_scope or forbidden:
        transition(job, "FROZEN", "runner")
        ledger_append({"event_id": "unapproved_change", "task_id": jid, "actor": "runner", "role": "runner",
                       "result": "FROZEN", "claim": "out_of_scope=%s forbidden=%s" % (out_of_scope, forbidden)})
    else:
        transition(job, "EVIDENCE_SUBMITTED", "claude_hq")
    # ---- deterministic verify ----
    transition(job, "VERIFYING", "wren") if job["state"] == "EVIDENCE_SUBMITTED" else None
    verify = []
    for chk in job.get("verifier_checks", []):
        # Absolutise path args so the trusted verifier (which may live under
        # /etc/qsb-governor and resolve its own ROOT to /etc) still finds tower files.
        achk, i = [], 0
        while i < len(chk):
            tok = chk[i]; achk.append(tok)
            if tok == "--file" and i + 1 < len(chk):
                v = chk[i + 1]; achk.append(v if v.startswith("/") else str(ROOT / v)); i += 2; continue
            if tok == "--files" and i + 1 < len(chk):
                v = chk[i + 1]
                achk.append(",".join(x if x.startswith("/") else str(ROOT / x) for x in v.split(","))); i += 2; continue
            i += 1
        try:
            out = subprocess.run(["python3", str(VERIFIER)] + achk, capture_output=True, text=True, timeout=30, cwd=str(ROOT))
            verify.append(json.loads(out.stdout.strip() or "{}"))
        except Exception as e:
            verify.append({"check": " ".join(chk), "result": "BLOCKED", "evidence": str(e)[:80]})
    if job["state"] in ("VERIFYING",):
        transition(job, "READY_FOR_ROSS", "wren")
    ledger_append({"event_id": "job_evidence", "task_id": jid, "actor": "claude_hq", "role": "governed",
                   "claim": "worker+verify results submitted", "result": job["state"],
                   "evidence_type": "runner", "evidence_source": "qsb_claude_job_runner",
                   "changed_files": changed, "out_of_scope": out_of_scope, "forbidden": forbidden})
    return {"job_id": jid, "final_state": job["state"], "changed_files": changed, "out_of_scope": out_of_scope,
            "forbidden": forbidden, "worker_results": results, "verifier_results": verify,
            "note": "Claude cannot ACCEPT — only Ross may move READY_FOR_ROSS -> ACCEPTED_BY_ROSS"}


def new_packet(args):
    core = {"job_id": args.job_id, "task_id": args.task_id, "ross_instruction": args.instruction,
            "wren_interpretation": args.interpretation, "risk_level": args.risk, "assigned_worker": args.worker,
            "permitted_paths": args.permitted.split(",") if args.permitted else [],
            "watch_paths": args.watch.split(",") if args.watch else [],
            "forbidden_paths": SAFETY_DENY, "expected_evidence": args.evidence,
            "worker_steps": json.loads(args.steps) if args.steps else [],
            "verifier_checks": json.loads(args.checks) if args.checks else [],
            "timeout": args.timeout, "approving_actor": "PENDING",
            "policy_checksum": _sha(POLICY), "verifier_checksum": _sha(VERIFIER)}
    core["packet_hash"] = hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()
    core["state"] = "AWAITING_ROSS"
    Path(args.out).write_text(json.dumps(core, indent=2))
    print(json.dumps({"drafted": args.out, "state": "AWAITING_ROSS", "packet_hash": core["packet_hash"][:16]}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet"); ap.add_argument("--new-packet", action="store_true")
    for k in ("job-id", "task-id", "instruction", "interpretation", "worker", "permitted", "watch", "evidence", "steps", "checks", "out"):
        ap.add_argument("--" + k, default="")
    ap.add_argument("--risk", default="LOW_READ_ONLY"); ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    if a.new_packet:
        return new_packet(a)
    if a.packet:
        print(json.dumps(run_packet(a.packet), indent=2))


if __name__ == "__main__":
    main()
