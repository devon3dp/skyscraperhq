#!/usr/bin/env python3
"""qsb_ceo_runtime_worker_sandbox.py — SANDBOX upgrade of the CEO runtime.

Ross 2026-07-10: turn TP-Pip / Acer-Cass from status-only GET servers into SAFE
task-capable workers — WITHOUT shell/sudo/edit power, WITHOUT touching live
Task Council / Town Square, and WITHOUT ever claiming physical independence.

SANDBOX ONLY. Does NOT modify the live qsb_ceo_runtime.py. Town Square / Council
writes go to /tmp sandbox files, never the live registries.

Logic is factored into pure functions (handle_*) so tests can call them directly;
do_POST just dispatches to them.
"""
from __future__ import annotations
import argparse, json, os, re, socket, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
SENDBACK = Path("/home/ross/Desktop/SKYSCRAPERHQ_RUNS/00_SEND_THIS_TO_CHATGPT")
# SANDBOX sinks — never the live files
SANDBOX_TOWN = Path("/tmp/qsb_sandbox_town_square.jsonl")
SANDBOX_COUNCIL = Path("/tmp/qsb_sandbox_council_events.jsonl")

# ── shared-secret auth for POST routes (never hardcoded, never committed) ──
# Token lives in a 600-perm file under .secrets/ (git-ignored). If the file is
# missing/empty the runtime starts in LOCKED mode: GET works, every POST returns
# 403 auth_not_configured. The token VALUE is never printed or returned.
TOKEN_FILE = Path("/vaults/nvme0/qsb_tower_v1/.secrets/qsb_runtime_worker_token")
def _expected_token():
    try:
        t = TOKEN_FILE.read_text().strip()
        return t or None
    except Exception:
        return None
def auth_status() -> dict:
    return {"post_auth_required": True, "post_auth_configured": bool(_expected_token()),
            "auth_header": "X-QSB-Runtime-Token"}

def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

CEOS = {
    "acer":   {"id": "acer_cass", "name": "Acer-Cass", "role": "Data Foundry / model-serving CEO",
               "notes": REG / "acer_cass_notes.jsonl", "port": 8872},
    "tp_pip": {"id": "tp_pip", "name": "TP-Pip", "role": "ThinkPad Command Cathedral CEO",
               "notes": REG / "tp_pip_notes.jsonl", "port": 8871},
}
def cfg(ceo: str) -> dict:
    k = ceo.lower().replace("-", "_")
    if k in ("acer", "acer_cass", "cass", "asa"): return CEOS["acer"]
    if k in ("tp", "tp_pip", "thinkpad", "pip"):  return CEOS["tp_pip"]
    raise SystemExit(f"unknown ceo: {ceo}")

# ── host truth ──────────────────────────────────────────────────────
def host_truth(c: dict) -> dict:
    return {"runtime_id": c["id"], "hostname": socket.gethostname(),
            "process_host": socket.gethostname(),
            "hq_hosted": True, "physical_independent": False,
            "classification": "HQ_HOSTED_RUNTIME_WORKER_SANDBOX"}

# ── read-only command whitelist (by NAME, never raw shell) ───────────
APPROVED_REGISTRY_FILES = {"qsb_council_tasks.jsonl", "qsb_council_tasks_snapshot.json"}
def _approved_target_file(target: str):
    name = os.path.basename(target or "")
    if name in APPROVED_REGISTRY_FILES and (REG / name).exists():
        return str(REG / name)
    return None
def _local_url(u: str) -> bool:
    m = re.match(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?(/|$)", u or "")
    return bool(m)

def _cmd_argv(cmd: str, target: str = ""):
    if cmd == "pwd":            return ("getcwd", None)  # handled specially
    if cmd == "hostname":       return (["hostname"], None)
    if cmd == "whoami":         return (["whoami"], None)
    if cmd == "date":           return (["date", "-Is"], None)
    if cmd == "ip_addr":        return (["ip", "addr"], None)
    if cmd == "ip_route":       return (["ip", "route"], None)
    if cmd == "ss_listen":      return (["ss", "-ltnp"], None)
    if cmd == "curl_local":
        if not _local_url(target): return (None, "curl_local target must be a local URL")
        return (["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "4", target], None)
    if cmd == "wc_task_log":
        f = _approved_target_file(target)
        return ((["wc", "-l", f], None) if f else (None, "wc target not an approved registry file"))
    if cmd == "json_snapshot_check":
        f = _approved_target_file(target)
        return ((["python3", "-m", "json.tool", f], None) if f else (None, "json target not approved"))
    if cmd == "tail_task_log":
        f = _approved_target_file(target)
        return ((["tail", "-n", "20", f], None) if f else (None, "tail target not approved"))
    return (None, "not_in_readonly_whitelist")

WHITELIST = ["pwd","hostname","whoami","date","ip_addr","ip_route","ss_listen",
             "curl_local","wc_task_log","json_snapshot_check","tail_task_log"]

def handle_run_readonly(c: dict, body: dict):
    cmd = (body or {}).get("cmd", "")
    target = (body or {}).get("target", "")
    # reject raw shell / metacharacters / anything not an exact whitelist name
    if cmd not in WHITELIST:
        return 400, {"ok": False, "error": "not_in_readonly_whitelist", "cmd": cmd,
                     "host_truth": host_truth(c)}
    argv, err = _cmd_argv(cmd, target)
    if err:
        return 400, {"ok": False, "error": err, "host_truth": host_truth(c)}
    try:
        if argv == "getcwd":
            out = os.getcwd()
        else:
            r = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=15)
            out = (r.stdout or r.stderr).strip()[:2000]
        return 200, {"ok": True, "cmd": cmd, "output": out, "host_truth": host_truth(c)}
    except Exception as e:
        return 500, {"ok": False, "error": str(e)[:200], "host_truth": host_truth(c)}

# ── task intake ─────────────────────────────────────────────────────
REQUIRED_INTAKE = ["task_id", "title", "requester", "report_path"]
def handle_intake(c: dict, body: dict):
    body = body or {}
    missing = [k for k in REQUIRED_INTAKE if not body.get(k)]
    if missing:
        return 400, {"ok": False, "error": "missing_fields", "missing": missing,
                     "host_truth": host_truth(c)}
    _append(c["notes"], {"ts": _utc(), "who": c["id"], "kind": "task_intake",
                         "task_id": body["task_id"], "title": body["title"][:200]})
    return 200, {"ok": True, "accepted": True, "task_id": body["task_id"],
                 "actor": c["id"], "host_truth": host_truth(c)}

# ── report writer (approved path only) ──────────────────────────────
def handle_report(c: dict, body: dict):
    body = body or {}
    path = Path(body.get("path") or (SENDBACK / f"{body.get('task_id','task')}_{c['id']}_REPORT.txt"))
    # path guard: must live under the approved send-back folder
    try:
        rp = path.resolve()
    except Exception:
        return 400, {"ok": False, "error": "bad_path", "host_truth": host_truth(c)}
    if not str(rp).startswith(str(SENDBACK.resolve())):
        return 400, {"ok": False, "error": "unsafe_path_rejected", "path": str(rp),
                     "host_truth": host_truth(c)}
    ht = host_truth(c)
    hdr = (f"REPORT by {c['id']} ({c['name']})\n"
           f"process_host: {ht['hostname']}  hq_hosted: {ht['hq_hosted']}  "
           f"physical_independent: {ht['physical_independent']}\n"
           f"classification: {ht['classification']}\n"
           f"received_task: {body.get('task_id')}\n" + "=" * 50 + "\n")
    footer = "\nfinal_status: needs Ross/ChatGPT/verifier review — not self-scored, not complete.\n"
    try:
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(hdr + (body.get("body", "")) + footer)
        return 200, {"ok": True, "report_path": str(rp), "actor": c["id"], "host_truth": ht}
    except Exception as e:
        return 500, {"ok": False, "error": str(e)[:200], "host_truth": ht}

# ── sandbox town square (never live) ────────────────────────────────
def handle_town_square(c: dict, body: dict):
    text = (body or {}).get("text", "")
    if not text:
        return 400, {"ok": False, "error": "empty_text", "host_truth": host_truth(c)}
    _append(SANDBOX_TOWN, {"ts": _utc(), "from": c["id"], "src": "ceo_runtime_sandbox", "text": text[:1000]})
    return 200, {"ok": True, "sandbox_file": str(SANDBOX_TOWN), "actor": c["id"],
                 "host_truth": host_truth(c)}

# ── sandbox council event (never live) ──────────────────────────────
ALLOWED_COUNCIL_EVENTS = {"intake_received", "proof_attached", "report_written",
                          "blocked", "needs_review"}
FORBIDDEN_COUNCIL_EVENTS = {"done", "closed", "peer_signoff", "verifier_approval",
                            "reopened", "signoff_approve"}
def handle_council_event(c: dict, body: dict):
    body = body or {}
    ev = body.get("event", "")
    if ev in FORBIDDEN_COUNCIL_EVENTS or ev not in ALLOWED_COUNCIL_EVENTS:
        return 400, {"ok": False, "error": "event_not_allowed_from_runtime", "event": ev,
                     "allowed": sorted(ALLOWED_COUNCIL_EVENTS), "host_truth": host_truth(c)}
    _append(SANDBOX_COUNCIL, {"ts": _utc(), "actor": c["id"], "event": ev,
                              "task_id": body.get("task_id"), "text": (body.get("text", ""))[:500]})
    return 200, {"ok": True, "sandbox_file": str(SANDBOX_COUNCIL), "actor": c["id"],
                 "event": ev, "host_truth": host_truth(c)}

# ── capabilities ────────────────────────────────────────────────────
def capabilities(c: dict) -> dict:
    ht = host_truth(c)
    return {"identity": {"id": c["id"], "name": c["name"], "role": c["role"]},
            "host": ht["hostname"], "hq_hosted": True, "physical_independent": False,
            "can_receive_task": True, "can_run_readonly": True, "can_write_report": True,
            "can_post_town_square": True, "can_post_task_council": True,
            "can_verify_peer_ceo": False, "can_self_close": False,
            "post_auth_required": True,
            "post_auth_configured": bool(_expected_token()),
            "allowed_commands": WHITELIST,
            "forbidden_actions": ["arbitrary_shell", "sudo", "destructive", "code_edit",
                                  "self_close", "peer_signoff", "live_council_write",
                                  "live_town_square_write", "claim_physical_independence"],
            "classification": ht["classification"]}

def _append(p: Path, obj: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(obj) + "\n"); f.flush(); os.fsync(f.fileno())

# ── POST auth gate + dispatch (all POST routes protected) ───────────
POST_ROUTES = {"/task/intake": handle_intake, "/task/run_readonly": handle_run_readonly,
               "/task/report": handle_report, "/task/town_square": handle_town_square,
               "/task/council_event": handle_council_event}

def dispatch_post(c: dict, path: str, body: dict, token: str):
    """Auth-gate every POST. token = value of X-QSB-Runtime-Token header."""
    fn = POST_ROUTES.get(path)
    if not fn:
        return 404, {"err": "not found"}
    expected = _expected_token()
    if not expected:                                   # LOCKED mode
        return 403, {"ok": False, "error": "auth_not_configured", "locked": True,
                     "host_truth": host_truth(c)}
    if not token or token != expected:                 # missing/wrong token
        return 403, {"ok": False, "error": "auth_rejected", "host_truth": host_truth(c)}
    return fn(c, body)                                  # authed -> normal validation

# ── HTTP handler (dispatches to the pure functions above) ───────────
def make_handler(c: dict):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/health", "/"):
                self._send(200, {"ok": True, **host_truth(c), "executor": "readonly_whitelist",
                                 "report_writer": True, "council_writer": "sandbox",
                                 "town_square_writer": "sandbox", **auth_status(), "ts": _utc()})
            elif path == "/capabilities":
                self._send(200, capabilities(c))
            elif path == "/whoami":
                self._send(200, {"id": c["id"], "name": c["name"], "role": c["role"], **host_truth(c)})
            else:
                self._send(404, {"err": "not found"})
        def do_POST(self):
            path = self.path.split("?")[0]
            n = int(self.headers.get("Content-Length") or 0)
            try: body = json.loads(self.rfile.read(n).decode() or "{}")
            except Exception: body = {}
            token = self.headers.get("X-QSB-Runtime-Token")   # auth gate
            code, obj = dispatch_post(c, path, body, token)
            self._send(code, obj)
    return H

def serve(c: dict, port: int):
    srv = HTTPServer(("127.0.0.1", port), make_handler(c))
    print(f"[SANDBOX {c['name']}] worker runtime on 127.0.0.1:{port} — HQ_HOSTED_RUNTIME_WORKER_SANDBOX")
    srv.serve_forever()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ceo", required=True)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=None)
    a = ap.parse_args()
    c = cfg(a.ceo)
    if a.serve: serve(c, a.port or c["port"]); return
    print(json.dumps(capabilities(c), indent=1))

if __name__ == "__main__":
    main()
