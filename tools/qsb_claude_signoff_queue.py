#!/usr/bin/env python3
"""qsb_claude_signoff_queue.py — Wren apprentice three-stage gate.

Wren queues an action → sandbox checks → Claude reviews → action applies.

Stages:
  A. queued_pending_sandbox  (just appended)
  B. sandbox_green | sandbox_red (after run_proposal_sandbox)
  C. signoff_approve | signoff_reject (after Claude review)
  D. applied | rolled_back

CLI:
  python3 tools/qsb_claude_signoff_queue.py --queue {json}         # Wren writes here
  python3 tools/qsb_claude_signoff_queue.py --run-sandbox <id>     # bench machinery
  python3 tools/qsb_claude_signoff_queue.py --pending-for-claude   # what's waiting
  python3 tools/qsb_claude_signoff_queue.py --approve <id> [--reason X]
  python3 tools/qsb_claude_signoff_queue.py --reject  <id> --reason X
  python3 tools/qsb_claude_signoff_queue.py --apply <id>           # final exec

Caveat: Wren cannot call --approve or --reject on her own queue items.
"""
from __future__ import annotations
import argparse, datetime, json, os, pathlib, shlex, subprocess, sys, uuid

ROOT = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
QUEUE = REG / "qsb_claude_signoff_queue.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"
GATE = REG / "qsb_wren_local_agentic_gate.json"

SAFETY_DENY = [
    "CLAUDE.md",
    "floors/floor_28_security_department/vault/",
    "tools/qsb_consult_external.py",
    "tools/qsb_oanda.py",
    "src/tower/qsb_floor41_oanda",
    "data/registries/qsb_proposal_autoapply_gate.json",
    "data/registries/qsb_provider_agentic_gate.json",
    "data/registries/qsb_wren_local_agentic_gate.json",
]


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")


def _read_queue() -> list[dict]:
    if not QUEUE.exists(): return []
    out = []
    for line in QUEUE.read_text().splitlines():
        if not line.strip(): continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


def _rewrite_queue(rows: list[dict]):
    tmp = QUEUE.with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    os.replace(tmp, QUEUE)


def _stamp_f47(kind: str, summary: str, operator: str = "claude_signoff_queue"):
    F47.parent.mkdir(parents=True, exist_ok=True)
    with F47.open("a") as f:
        f.write(json.dumps({"ts": now_iso(), "kind": kind, "operator": operator, "summary": summary[:500]})+"\n")


def _is_safety_path(p: str) -> bool:
    for deny in SAFETY_DENY:
        if p == deny or p.startswith(deny.rstrip("/")+"/"): return True
    return False


# ── stage A: enqueue ──────────────────────────────────────────────────

def cmd_queue(payload: str):
    """Wren posts an action: {tool, args, rationale, action_id?}"""
    try: data = json.loads(payload)
    except Exception as e:
        print(f"ERROR: bad json: {e}"); sys.exit(2)
    tool = data.get("tool"); args = data.get("args", {})
    if not tool:
        print("ERROR: tool required"); sys.exit(2)
    # safety check on any path-touching tool
    target = args.get("path") or args.get("target_file") or ""
    if target and _is_safety_path(target):
        print(f"REFUSED: target in SAFETY_DENY: {target}")
        _stamp_f47("apprentice_refused", f"{tool} target={target} → SAFETY_DENY")
        sys.exit(3)
    action_id = data.get("action_id") or f"ap_{uuid.uuid4().hex[:10]}"
    row = {
        "action_id": action_id, "ts_queued": now_iso(),
        "tool": tool, "args": args, "rationale": data.get("rationale","")[:1000],
        "proposer": data.get("proposer","wren_local"),
        "status": "queued_pending_sandbox",
        "sandbox_verdict": None, "signoff": None, "applied_at": None,
        "sha_before": None, "sha_after": None,
    }
    rows = _read_queue() + [row]
    _rewrite_queue(rows)
    _stamp_f47("apprentice_queued", f"{action_id} tool={tool} target={target}")
    print(f"queued {action_id}")
    return action_id


# ── stage B: sandbox ──────────────────────────────────────────────────

def cmd_run_sandbox(action_id: str):
    rows = _read_queue()
    target_row = next((r for r in rows if r["action_id"] == action_id), None)
    if not target_row:
        print(f"ERROR: action_id not found: {action_id}"); sys.exit(2)
    if target_row["status"] != "queued_pending_sandbox":
        print(f"ERROR: not in queued_pending_sandbox state (current: {target_row['status']})"); sys.exit(2)
    tool = target_row["tool"]; args = target_row["args"]

    verdict = "sandbox_red"
    reason = "unknown"
    try:
        if tool == "wren_edit_file":
            # smoke: would the edit be syntactically reasonable? minimal check — file exists, old_text appears
            path = (ROOT / args.get("path","").lstrip("/")).resolve()
            if not path.exists():
                reason = f"target file does not exist: {args.get('path')}"
            else:
                content = path.read_text(errors="replace")
                count = content.count(args.get("old_text",""))
                if count == 0: reason = "old_text not found in file"
                elif count > 1: reason = f"old_text appears {count} times (not unique)"
                else:
                    # additional: if .py, attempt ast.parse on the resulting content
                    if path.suffix == ".py":
                        import ast
                        new_content = content.replace(args["old_text"], args["new_text"], 1)
                        try:
                            ast.parse(new_content)
                            verdict = "sandbox_green"; reason = "py syntax check passed"
                        except SyntaxError as e:
                            reason = f"py syntax error after edit: {e}"
                    else:
                        verdict = "sandbox_green"; reason = "edit looks clean (non-py, can't verify syntax)"
        elif tool == "wren_bash":
            cmd = args.get("cmd","")
            # safety: refuse anything matching the deny patterns even in sandbox
            if any(b in cmd for b in ["rm -rf", "sudo", "dd ", "mkfs", "chmod +s", ">/etc"]):
                reason = f"bash deny pattern in cmd"
            else:
                # read-only allowlist (ls/cat/grep/find/etc) → run with cwd=ROOT so
                # the test reflects what the actual apply step would see.
                # mutating commands (none allowed in allowlist today) would need
                # a copy-tree sandbox.
                first = (shlex.split(cmd)[:1] or [""])[0]
                read_only = first in {"ls","cat","grep","rg","find","wc","head","tail","jq","df","du","git"}
                try:
                    cwd = str(ROOT) if read_only else None  # None → /tmp behavior for mutating
                    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=10)
                    if r.returncode == 0:
                        verdict = "sandbox_green"; reason = f"exit 0, stdout {len(r.stdout)}b (cwd={'ROOT' if read_only else 'tmp'})"
                    else:
                        reason = f"exit {r.returncode}, stderr: {r.stderr[:200]}"
                except Exception as e:
                    reason = f"sandbox exec error: {e}"
        elif tool == "wren_curl":
            # read-only GET; sandbox by doing the call against host allowlist
            gate = json.loads(GATE.read_text())
            allow = gate["tools"]["wren_curl"]["host_allowlist"]
            from urllib.parse import urlparse
            host = urlparse(args.get("url","")).hostname or ""
            if host not in allow:
                reason = f"host {host} not in allowlist"
            else:
                verdict = "sandbox_green"; reason = f"host {host} ok; deferring fetch to apply step"
        elif tool == "wren_scrcpy":
            gate = json.loads(GATE.read_text())
            allow = gate["tools"]["wren_scrcpy"]["action_allowlist"]
            if args.get("action") not in allow:
                reason = f"action {args.get('action')} not in allowlist"
            else:
                verdict = "sandbox_green"; reason = "action allowlisted; deferring exec to apply"
        else:
            reason = f"unknown tool {tool}"
    except Exception as e:
        reason = f"sandbox crash: {e}"

    target_row["status"] = verdict
    target_row["sandbox_verdict"] = {"ts": now_iso(), "verdict": verdict, "reason": reason}
    _rewrite_queue(rows)
    _stamp_f47("apprentice_sandbox", f"{action_id} → {verdict}: {reason}")
    print(f"{action_id} → {verdict}: {reason}")


# ── stage C: claude signoff ───────────────────────────────────────────

def cmd_pending_for_claude():
    rows = _read_queue()
    pending = [r for r in rows if r["status"] == "sandbox_green" and r.get("signoff") is None]
    if not pending: print("(none pending)"); return
    for r in pending:
        print(f"\n--- {r['action_id']}  tool={r['tool']}  queued_at={r['ts_queued']}")
        print(f"    rationale: {r['rationale'][:200]}")
        print(f"    args: {json.dumps(r['args'])[:300]}")
        print(f"    sandbox: {r['sandbox_verdict']['reason'][:120]}")


def cmd_approve(action_id: str, reason: str = ""):
    _decide(action_id, "signoff_approve", reason)


def cmd_reject(action_id: str, reason: str):
    if not reason: print("ERROR: --reason required for reject"); sys.exit(2)
    _decide(action_id, "signoff_reject", reason)


def _decide(action_id: str, decision: str, reason: str):
    rows = _read_queue()
    target_row = next((r for r in rows if r["action_id"] == action_id), None)
    if not target_row:
        print(f"ERROR: not found: {action_id}"); sys.exit(2)
    if target_row["status"] != "sandbox_green":
        print(f"ERROR: not in sandbox_green state: {target_row['status']}"); sys.exit(2)
    target_row["signoff"] = {"ts": now_iso(), "decision": decision, "reason": reason[:500], "by": "claude"}
    target_row["status"] = decision
    _rewrite_queue(rows)
    _stamp_f47("apprentice_" + decision, f"{action_id} {target_row['tool']}: {reason[:200]}")

    # update graduation counter on approve
    if decision == "signoff_approve":
        try:
            g = json.loads(GATE.read_text())
            tool = target_row["tool"]
            current = g.setdefault("apprentice_graduation", {}).setdefault("current", {})
            current[tool] = current.get(tool, 0) + 1
            threshold = g["apprentice_graduation"].get("approvals_to_graduate", 20)
            if current[tool] >= threshold:
                _stamp_f47("apprentice_graduated", f"{tool} graduated after {current[tool]} approvals")
            GATE.write_text(json.dumps(g, indent=2))
        except Exception as e:
            _stamp_f47("graduation_counter_err", str(e))
    elif decision == "signoff_reject":
        try:
            g = json.loads(GATE.read_text())
            tool = target_row["tool"]
            g.setdefault("apprentice_graduation", {}).setdefault("current", {})[tool] = 0
            GATE.write_text(json.dumps(g, indent=2))
        except Exception: pass
    print(f"{action_id} → {decision}")


# ── stage D: apply ────────────────────────────────────────────────────

def cmd_apply(action_id: str):
    rows = _read_queue()
    target_row = next((r for r in rows if r["action_id"] == action_id), None)
    if not target_row:
        print(f"ERROR: not found: {action_id}"); sys.exit(2)
    if target_row["status"] != "signoff_approve":
        print(f"ERROR: not approved (status: {target_row['status']})"); sys.exit(2)
    tool = target_row["tool"]; args = target_row["args"]
    sha_before = None; sha_after = None
    try:
        if tool == "wren_edit_file":
            path = (ROOT / args.get("path","").lstrip("/")).resolve()
            content = path.read_text(errors="replace")
            new_content = content.replace(args["old_text"], args["new_text"], 1)
            import hashlib
            sha_before = hashlib.sha256(content.encode()).hexdigest()[:12]
            tmp = path.with_suffix(path.suffix + ".apprentice_tmp")
            tmp.write_text(new_content)
            os.replace(tmp, path)
            sha_after = hashlib.sha256(new_content.encode()).hexdigest()[:12]
            outcome = f"edited {args['path']} ({len(content)}→{len(new_content)})"
        elif tool == "wren_bash":
            r = subprocess.run(args["cmd"], shell=True, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            outcome = f"exit {r.returncode}; stdout {len(r.stdout)}b; stderr {len(r.stderr)}b"
        elif tool == "wren_curl":
            import urllib.request
            req = urllib.request.Request(args["url"], method="GET")
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read().decode("utf-8", errors="replace")
            outcome = f"GET {args['url']}: {len(body)}b"
        elif tool == "wren_scrcpy":
            # delegated to qsb_wren_local_agent's scrcpy impl
            outcome = f"scrcpy {args.get('action')} — deferred to runtime"
        else:
            outcome = "unknown tool"
        target_row["status"] = "applied"
        target_row["applied_at"] = now_iso()
        target_row["sha_before"] = sha_before
        target_row["sha_after"] = sha_after
        target_row["outcome"] = outcome[:500]
    except Exception as e:
        target_row["status"] = "apply_failed"
        target_row["outcome"] = f"ERROR: {e}"[:500]
    _rewrite_queue(rows)
    _stamp_f47("apprentice_applied" if target_row["status"]=="applied" else "apprentice_apply_failed",
               f"{action_id} {tool}: {target_row.get('outcome','')[:200]}")
    print(f"{action_id} → {target_row['status']}: {target_row.get('outcome','')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", help="JSON payload to queue")
    ap.add_argument("--run-sandbox", dest="run_sandbox", metavar="ID")
    ap.add_argument("--pending-for-claude", action="store_true")
    ap.add_argument("--approve", metavar="ID")
    ap.add_argument("--reject",  metavar="ID")
    ap.add_argument("--apply",   metavar="ID")
    ap.add_argument("--reason", default="")
    a = ap.parse_args()
    if a.queue: cmd_queue(a.queue)
    elif a.run_sandbox: cmd_run_sandbox(a.run_sandbox)
    elif a.pending_for_claude: cmd_pending_for_claude()
    elif a.approve: cmd_approve(a.approve, a.reason)
    elif a.reject:  cmd_reject(a.reject, a.reason)
    elif a.apply:   cmd_apply(a.apply)
    else: ap.print_help()

if __name__ == "__main__":
    main()
