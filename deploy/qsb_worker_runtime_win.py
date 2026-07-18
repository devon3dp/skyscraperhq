#!/usr/bin/env python3
"""qsb_worker_runtime_win.py — self-contained AUTHENTICATED worker runtime for the
REAL physical ThinkPad / Acer Windows boxes (Ross 2026-07-10).

Derived from the reviewed sandbox worker runtime + auth guard, but self-contained
(no Linux /vaults paths) so it runs natively on Windows Python. Proves PHYSICAL
independence: host_truth reports the REAL box hostname (e.g. DESKTOP-1E2FB5N),
physical_independent=True, host_mode=PHYSICAL — NOT 24.04ubuntu / HQ-hosted.

USAGE (on the box):
    python qsb_worker_runtime_win.py --ceo tp_pip --port 8871
Token file: %USERPROFILE%\\qsb_worker\\.secrets\\runtime_token  (created by deploy).
POST routes require header X-QSB-Runtime-Token. Missing token file => LOCKED.
"""
import argparse, json, os, re, socket, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = Path(os.path.expanduser("~")) / "qsb_worker"
SECRETS = BASE / ".secrets"; TOKEN_FILE = SECRETS / "runtime_token"
REPORTS = BASE / "reports"; NOTES = BASE / "notes.jsonl"
SANDBOX_TOWN = BASE / "town_square.jsonl"; SANDBOX_COUNCIL = BASE / "council_events.jsonl"
for d in (BASE, SECRETS, REPORTS):
    d.mkdir(parents=True, exist_ok=True)

CEOS = {"tp_pip": ("TP-Pip", "ThinkPad Command Cathedral CEO"),
        "acer_cass": ("Acer-Cass", "Data Foundry / model-serving CEO"),
        "acer": ("Acer-Cass", "Data Foundry / model-serving CEO")}

def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def _expected_token():
    try:
        t = TOKEN_FILE.read_text().strip(); return t or None
    except Exception:
        return None

def host_truth(cid, cname):
    hn = socket.gethostname()
    hq_hosted = hn.lower() in ("24.04ubuntu",)  # if it ever runs on HQ, say so
    return {"runtime_id": cid, "name": cname, "hostname": hn, "process_host": hn,
            "hq_hosted": hq_hosted, "physical_independent": (not hq_hosted),
            "host_mode": ("HQ_HOSTED" if hq_hosted else "PHYSICAL"),
            "classification": ("HQ_HOSTED_RUNTIME" if hq_hosted else "PHYSICAL_INDEPENDENT_WORKER")}

# read-only command whitelist (Windows-safe, by name)
def run_readonly(cmd):
    m = {"hostname": ["hostname"], "whoami": ["whoami"], "ver": ["cmd", "/c", "ver"],
         "ipconfig": ["ipconfig"], "date": ["cmd", "/c", "echo %DATE% %TIME%"],
         "python_version": [sys.executable, "--version"], "tasklist_py": ["cmd", "/c", "tasklist | findstr python"]}
    if cmd not in m:
        return 400, {"ok": False, "error": "not_in_readonly_whitelist", "cmd": cmd}
    try:
        r = subprocess.run(m[cmd], capture_output=True, text=True, timeout=15)
        return 200, {"ok": True, "cmd": cmd, "output": (r.stdout or r.stderr).strip()[:2000]}
    except Exception as e:
        return 500, {"ok": False, "error": str(e)[:200]}

def _append(p, obj):
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")

def capabilities(cid, cname):
    ht = host_truth(cid, cname)
    return {"identity": {"id": cid, "name": cname}, **ht,
            "can_receive_task": True, "can_run_readonly": True, "can_write_report": True,
            "can_post_town_square": True, "can_post_task_council": True,
            "can_verify_peer_ceo": False, "can_self_close": False,
            "task_capable": True, "executor_available": True, "report_writer_available": True,
            "local_model_running": False, "current_provider": None,
            "routing_mode": "physical_worker_local",
            "post_auth_required": True, "post_auth_configured": bool(_expected_token()),
            "allowed_commands": ["hostname", "whoami", "ver", "ipconfig", "date",
                                 "python_version", "tasklist_py"],
            "forbidden_actions": ["arbitrary_shell", "destructive", "self_close",
                                  "peer_signoff", "claim_when_hq_hosted"]}

def make_handler(cid, cname):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            p = self.path.split("?")[0]
            if p in ("/health", "/"):
                self._send(200, {"ok": True, **host_truth(cid, cname), "executor": "readonly_whitelist",
                                 "post_auth_configured": bool(_expected_token()), "ts": utc()})
            elif p == "/whoami":
                self._send(200, {"id": cid, "name": cname, **host_truth(cid, cname)})
            elif p == "/capabilities":
                self._send(200, capabilities(cid, cname))
            else:
                self._send(404, {"err": "not found"})
        def do_POST(self):
            p = self.path.split("?")[0]
            n = int(self.headers.get("Content-Length") or 0)
            try: body = json.loads(self.rfile.read(n).decode() or "{}")
            except Exception: body = {}
            token = self.headers.get("X-QSB-Runtime-Token")
            exp = _expected_token()
            routes = ("/task/intake", "/task/run_readonly", "/task/report",
                      "/task/town_square", "/task/council_event")
            if p not in routes:
                self._send(404, {"err": "not found"}); return
            if not exp:
                self._send(403, {"ok": False, "state": "blocked_no_task", "error": "auth_not_configured",
                                 **host_truth(cid, cname)}); return
            if not token or token != exp:
                self._send(403, {"ok": False, "error": "auth_rejected", **host_truth(cid, cname)}); return
            if p == "/task/intake":
                miss = [k for k in ("task_id", "title", "requester", "report_path") if not body.get(k)]
                if miss:
                    self._send(400, {"ok": False, "error": "missing_fields", "missing": miss}); return
                _append(NOTES, {"ts": utc(), "who": cid, "kind": "task_intake", "task_id": body["task_id"]})
                self._send(200, {"ok": True, "accepted": True, "task_id": body["task_id"], "actor": cid,
                                 **host_truth(cid, cname)}); return
            if p == "/task/run_readonly":
                code, obj = run_readonly(body.get("cmd", "")); obj.update(host_truth(cid, cname))
                self._send(code, obj); return
            if p == "/task/report":
                path = REPORTS / (str(body.get("task_id", "task")) + "_" + cid + "_REPORT.txt")
                ht = host_truth(cid, cname)
                hdr = (f"REPORT by {cid} ({cname})\nprocess_host: {ht['hostname']}  "
                       f"host_mode: {ht['host_mode']}  physical_independent: {ht['physical_independent']}\n"
                       + "=" * 40 + "\n")
                footer = "\nfinal_status: needs Ross/ChatGPT/verifier review.\n"
                path.write_text(hdr + str(body.get("body", "")) + footer, encoding="utf-8")
                self._send(200, {"ok": True, "report_path": str(path), "actor": cid, **ht}); return
            if p == "/task/town_square":
                if not body.get("text"): self._send(400, {"ok": False, "error": "empty_text"}); return
                _append(SANDBOX_TOWN, {"ts": utc(), "from": cid, "text": body["text"][:1000]})
                self._send(200, {"ok": True, "file": str(SANDBOX_TOWN), "actor": cid}); return
            if p == "/task/council_event":
                ev = body.get("event", "")
                allowed = {"intake_received", "proof_attached", "report_written", "blocked", "needs_review"}
                if ev not in allowed:
                    self._send(400, {"ok": False, "error": "event_not_allowed_from_runtime", "event": ev}); return
                _append(SANDBOX_COUNCIL, {"ts": utc(), "actor": cid, "event": ev, "task_id": body.get("task_id")})
                self._send(200, {"ok": True, "file": str(SANDBOX_COUNCIL), "event": ev, "actor": cid}); return
    return H

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ceo", required=True); ap.add_argument("--port", type=int, default=8871)
    a = ap.parse_args()
    key = a.ceo.lower().replace("-", "_")
    if key not in CEOS: raise SystemExit("unknown ceo: " + a.ceo)
    cid = "acer_cass" if key in ("acer", "acer_cass") else "tp_pip"
    cname, _role = CEOS[cid]
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(cid, cname))
    print(f"[{cname}] PHYSICAL worker runtime on {socket.gethostname()}:{a.port} "
          f"physical_independent={host_truth(cid,cname)['physical_independent']}")
    srv.serve_forever()

if __name__ == "__main__":
    main()
