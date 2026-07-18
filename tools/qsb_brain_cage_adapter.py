#!/usr/bin/env python3
"""
QSB BRAIN CAGE ADAPTER V1  (action_id=BRAIN-CAGE-ADAPTER-V1)

A SEPARATE, authenticated sidecar that lets authorised Skyscraper requesters (ross, wren,
tp_pip, acer_cass, claude_hq) submit governed requests to the proven Claude Max OAuth cage —
WITHOUT touching the live Brain Module (:8860), OAuth credentials, the Claude CLI, systemd
directly, a sudo password, arbitrary shell, or production writes.

Governed flow per request:
  requester -> Wren scope review -> Task Council task -> Ross approval (commissioning) ->
  cage broker (via the narrow root helper /usr/local/sbin/qsb-cage-ctl) -> CLAUDE_MAX_CAGE_OAUTH ->
  deterministic verifier -> Wren verdict -> result returned to requester.

HARD boundaries:
  - Does NOT read .env.sudo or any password. Cage start/stop/status is done ONLY via
    `sudo -n /usr/local/sbin/qsb-cage-ctl <start|stop|is-active> <job>` (self-validating helper).
  - Binds 127.0.0.1 by default (localhost). No wildcard CORS; explicit trusted-origin allowlist.
  - Bearer-token auth + X-Requested-By (CSRF) on every state-changing route. Rate + size limits. Audit log.
  - No requester may final-accept. Claude cannot self-approve/verify/close. Only Ross ACCEPTS.
  - The live router file is never touched by this process.

Run:  python3 tools/qsb_brain_cage_adapter.py [--port 8859] [--host 127.0.0.1]
"""
import argparse, json, os, re, subprocess, hashlib, time, secrets
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
TRUSTED = Path("/etc/qsb-governor")
IDENTITY_FILE = TRUSTED / "claude_hq_identity.yaml"
POLICY = TRUSTED / "wren_governor_policy.yaml"
VERIFIER = TRUSTED / "qsb_governor_verifier.py"
CAGE_CTL = "/usr/local/sbin/qsb-cage-ctl"            # the ONLY privileged action (narrow root helper)
CAGE = ROOT / "runtime/claude_cage"
ADAPT = CAGE / "adapter"                              # adapter state (ross-only)
JOBS_DB = ADAPT / "jobs.json"
AUDIT = ADAPT / "audit.jsonl"
TOKEN_FILE = ADAPT / "adapter_token"                 # 0600, ross-only
COUNCIL = REG / "qsb_council_tasks.jsonl"
CAGED_PROVIDERS = REG / "qsb_gene_pool_caged_providers.json"
WREN_AGENT = ROOT / "tools/qsb_wren_local_agent.py"

# Requester identity model
ALLOWED_REQUESTERS = {"ross", "wren", "tp_pip", "acer_cass", "claude_hq"}
CONTROL_PLANE = {"ross", "wren", "claude_hq"}          # local control-plane requesters
PHYSICAL = {"tp_pip": "192.168.1.74", "acer_cass": "192.168.1.78"}
RETIRED = {"acer_cass": "192.168.1.41"}
HOSTNAMES = {"tp_pip": "DESKTOP-9RBVKSM", "acer_cass": "DESKTOP-1E2FB5N"}
SURROGATE_IP = {"127.0.0.1", "::1", "localhost"}
JOB_RX = re.compile(r"^(chat|wren|tppip|acer|hq)_[0-9]{6,}$")   # MUST match the root helper's regex
PREFIX = {"ross": "chat", "wren": "wren", "tp_pip": "tppip", "acer_cass": "acer", "claude_hq": "hq"}
MODES = {"CHAT_ONLY", "READ_ONLY_REVIEW", "SANDBOX_WRITE", "PRODUCTION_PATCH_REQUEST"}
# Council lifecycle
STATES = ["DRAFT", "WREN_REVIEW", "AWAITING_ROSS", "APPROVED", "STAGED", "RUNNING",
          "OUTPUT_RECEIVED", "VERIFYING", "READY_FOR_ROSS", "FROZEN", "REJECTED",
          "ACCEPTED_BY_ROSS", "WAITING_FOR_MAX_RESET"]
TRUSTED_ORIGINS = {"http://127.0.0.1:8859", "http://localhost:8859"}
MAX_BODY = 64 * 1024
RATE = {}                                              # ip -> [timestamps]
ALLOWED_IPS = set()                                    # empty => localhost-bind mode; set => strict source allowlist

ADAPT.mkdir(parents=True, exist_ok=True)


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except Exception:
        return None


def get_token():
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    tok = secrets.token_hex(24)
    TOKEN_FILE.write_text(tok)
    os.chmod(TOKEN_FILE, 0o600)
    return tok


ADAPTER_TOKEN = get_token()


def load_jobs():
    if JOBS_DB.exists():
        try:
            return json.loads(JOBS_DB.read_text())
        except Exception:
            return {}
    return {}


def save_jobs(j):
    tmp = JOBS_DB.with_suffix(".tmp")
    tmp.write_text(json.dumps(j, indent=2))
    tmp.replace(JOBS_DB)


def audit(ev):
    ev["ts"] = utc()
    with open(AUDIT, "a") as f:
        f.write(json.dumps(ev) + "\n")


def council_write(task):
    """Append a REAL Task Council record. Never marked completed by the adapter."""
    with open(COUNCIL, "a") as f:
        f.write(json.dumps(task) + "\n")


def read_yaml_flat(p):
    d, cur = {}, None
    try:
        for raw in Path(p).read_text().splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            ind = len(raw) - len(raw.lstrip(" ")); s = raw.strip()
            if ind > 0 and s.startswith("- "):
                if not isinstance(d.get(cur), list):
                    d[cur] = []
                d[cur].append(s[2:].strip().strip('"')); continue
            if ind > 0 and ":" in s:
                k, v = s.split(":", 1)
                if not isinstance(d.get(cur), dict):
                    d[cur] = {}
                d[cur][k.strip()] = v.strip().strip('"'); continue
            if ind == 0 and ":" in raw:
                k, v = raw.split(":", 1); cur = k.strip()
                d[cur] = v.strip().strip('"') if v.strip() else None
    except Exception:
        pass
    return d


def identity_preamble():
    idc = read_yaml_flat(IDENTITY_FILE)
    i = idc.get("identity", {}) if isinstance(idc.get("identity"), dict) else {}
    a = idc.get("authority", {}) if isinstance(idc.get("authority"), dict) else {}
    return ("You are %s. Role: %s. Owner/final authority: %s (with ChatGPT). Governor/checker: %s. "
            "Work recorded in the %s. Physical peers: TP-Pip and Acer-Cass. Your Claude Max inference runs "
            "inside an OS-level cage; you have NO direct production write access. Forbidden: direct production "
            "editing, self-approval, self-verification, self-close, editing Wren policy/verifier, altering "
            "prior evidence, impersonating physical workers, surrogate/physical mixing, API-key fallback. "
            "Answer as %s. Do not describe yourself as a QSB Tower auditor, generic assistant, local model, "
            "physical worker, or unrestricted CLI.\n"
            % (i.get("display_name", "Claude HQ"), i.get("role", "CEO/architect/engineer"),
               a.get("owner", "Ross"), a.get("governor", "Wren"), a.get("work_ledger", "Task Council"),
               i.get("display_name", "Claude HQ")))


# ---------- requester classification / rejection (Phase 4) ----------
def classify(requester_id, client_ip, declared_endpoint=""):
    """Return (ok, classification, reason)."""
    if requester_id not in ALLOWED_REQUESTERS:
        return False, "unknown", "unknown requester '%s'" % requester_id
    if requester_id in CONTROL_PLANE:
        # local control-plane requesters must originate locally
        if client_ip not in SURROGATE_IP and not client_ip.startswith("192.168."):
            return False, "control_plane", "control-plane requester from unexpected ip %s" % client_ip
        return True, "control_plane_local", ""
    # physical worker requester (tp_pip / acer_cass)
    if requester_id in RETIRED and client_ip == RETIRED[requester_id]:
        return False, "retired", "retired endpoint %s rejected for %s" % (client_ip, requester_id)
    if client_ip in SURROGATE_IP:
        return False, "surrogate_as_physical", "HQ surrogate (%s) presented as physical %s — rejected" % (client_ip, requester_id)
    if client_ip != PHYSICAL.get(requester_id):
        return False, "wrong_physical_ip", "physical %s must originate from %s, got %s" % (
            requester_id, PHYSICAL.get(requester_id), client_ip)
    return True, "physical", ""


# ---------- the cage broker (Phase 7 — via the narrow helper, NO sudo password) ----------
def cage_ctl(action, job):
    if action not in ("start", "stop", "is-active", "read", "summary") or not JOB_RX.match(job):
        return 99, "", "adapter refused: action/job"
    r = subprocess.run(["sudo", "-n", CAGE_CTL, action, job], capture_output=True, text=True, timeout=240)
    return r.returncode, (r.stdout or ""), (r.stderr or "").strip()


def build_packet(job, requester_id, question, mode):
    prompt = identity_preamble() + "\n[Request from %s, mode=%s]\nQuestion: %s" % (requester_id, mode, question.strip())
    ws = "runtime/claude_cage/active/%s" % job
    out_rel = "%s/output/claude_response.txt" % ws
    core = {
        "job_id": job, "task_id": "brain_" + job, "ross_instruction": question.strip()[:400],
        "requester_id": requester_id,
        "wren_interpretation": "Brain Cage Adapter CHAT_ONLY; identity injected; claude -p; no tools/MCP/writes beyond job dir.",
        "risk_level": "LOW_READ_ONLY" if mode in ("CHAT_ONLY", "READ_ONLY_REVIEW") else "MEDIUM",
        "assigned_worker": "claude_runner", "mode": mode, "job_workspace": ws,
        "permitted_paths": [ws], "watch_paths": ["runtime/claude_cage/active"],
        "forbidden_paths": ["CLAUDE.md", "config/wren_governor_policy.yaml",
                            "tools/qsb_governor_verifier.py", "tools/qsb_claude_job_runner.py"],
        "identity_contract_hash": (sha(IDENTITY_FILE) or "")[:16],
        "worker_steps": [{"label": "brain-cage chat (no tools)", "class": "claude_chat",
                          "cmd": {"prompt": prompt[:4000], "output_path": out_rel, "timeout": 180}}],
        "verifier_checks": [["--check", "file", "--file", out_rel]],
        "timeout": 300, "approving_actor": "ross",
        "policy_checksum": sha(POLICY), "verifier_checksum": sha(VERIFIER),
    }
    core["packet_hash"] = hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()
    return core, out_rel


def run_cage(job, requester_id, question, mode, simulate_max_exhausted=False):
    # Phase 6 — simulated Max-usage exhaustion path (no real allowance consumed)
    if simulate_max_exhausted:
        return {"sentinel": "MAX_USAGE_LIMIT_REACHED_NO_PAID_FALLBACK", "final_state": "WAITING_FOR_MAX_RESET",
                "auth": "SUBSCRIPTION_OAUTH", "api_key_present": False, "paid_fallback_used": False,
                "response": None, "cage_closed": True, "note": "simulated Max exhaustion; request preserved; no paid fallback"}
    packet, out_rel = build_packet(job, requester_id, question, mode)
    (CAGE / "inbox" / ("%s.json" % job)).write_text(json.dumps(packet, indent=2))
    cage_ctl("stop", job)  # ensure clean
    rc, out, err = cage_ctl("start", job)
    # oneshot start blocks until done; settle-poll for closure
    result_state = subprocess.run(["systemctl", "show", "-p", "Result", "--value",
                                   "qsb-claude-cage@%s.service" % job], capture_output=True, text=True, timeout=5).stdout.strip()
    # Read the runner's JSON summary and the response via the narrow root helper (no sudo password,
    # no login shell/MOTD pollution, no journal-permission dependency).
    _, jsum, _ = cage_ctl("summary", job)
    summary = {}
    blocks = re.findall(r"\{[\s\S]*?\n\}", jsum)
    for b in reversed(blocks):
        try:
            summary = json.loads(b); break
        except Exception:
            continue
    _, resp, _ = cage_ctl("read", job)
    resp = resp.strip()
    caged = "1"
    for _ in range(30):
        caged = subprocess.run(["ps", "-u", "claude_runner", "--no-headers"], capture_output=True, text=True, timeout=5).stdout
        caged = str(len([l for l in caged.splitlines() if l.strip()]))
        if caged == "0":
            break
        time.sleep(1)
    wr = (summary.get("worker_results") or [{}])[0]
    vr = (summary.get("verifier_results") or [{}])[0]
    # Detect a real Max-usage failure (rc!=0 + empty + usage/limit hint) -> sentinel, no paid fallback
    stderr_l = (wr.get("stderr_tail") or "").lower()
    if not resp and wr.get("returncode") not in (0, None) and any(k in stderr_l for k in ("usage limit", "rate limit", "quota", "exhaust")):
        return {"sentinel": "MAX_USAGE_LIMIT_REACHED_NO_PAID_FALLBACK", "final_state": "WAITING_FOR_MAX_RESET",
                "auth": "SUBSCRIPTION_OAUTH", "api_key_present": False, "paid_fallback_used": False,
                "response": None, "cage_closed": caged == "0"}
    return {"packet_hash": packet["packet_hash"][:16], "identity_contract_hash": packet["identity_contract_hash"],
            "final_state": summary.get("final_state"), "response": resp,
            "response_chars": wr.get("response_chars"), "returncode": wr.get("returncode"),
            "auth": wr.get("auth"), "api_key_present": wr.get("api_key_present"),
            "verifier_result": vr.get("result"), "out_of_scope": summary.get("out_of_scope"),
            "forbidden": summary.get("forbidden"), "cage_closed": caged == "0", "caged_procs_final": caged,
            "unit_result": result_state, "paid_fallback_used": False}


def wren_review(requester_id, question, mode):
    task = ("Governor scope review. Requester=%s asks (mode=%s): %r. It will run CHAT_ONLY in the OS cage: "
            "tools+MCP disabled, subscription OAuth, no API key, output confined to the job dir, verified by a "
            "deterministic check, cannot be self-accepted. Give a one-line scope note and a verdict from "
            "{CLAIM_VERIFIED, CLAIM_PARTIAL, CLAIM_UNSUPPORTED, OUT_OF_SCOPE_CHANGE, MANUAL_ROSS_TEST_REQUIRED}."
            % (requester_id, mode, question))
    try:
        out = subprocess.run(["python3", str(WREN_AGENT), "--task", task], capture_output=True, text=True,
                             timeout=90, cwd=str(ROOT)).stdout
        lines = [l for l in out.splitlines() if l.strip() and not l.strip().startswith(("━", "session", "turns"))]
        vd = next((v for v in ("CLAIM_VERIFIED", "CLAIM_PARTIAL", "CLAIM_UNSUPPORTED", "OUT_OF_SCOPE_CHANGE",
                               "MANUAL_ROSS_TEST_REQUIRED") if v in out), "CLAIM_PARTIAL")
        return " ".join(lines).strip()[:400] or "Wren reviewed.", vd
    except Exception as e:
        return "Wren offline: %s" % e, "MANUAL_ROSS_TEST_REQUIRED"


def provider_view():
    try:
        p = json.loads(CAGED_PROVIDERS.read_text())["providers"]["CLAUDE_MAX_CAGE_OAUTH"]
    except Exception:
        p = {}
    return p


# ================= HTTP =================
class H(BaseHTTPRequestHandler):
    server_version = "qsb-brain-cage-adapter/1"

    def log_message(self, *a):
        pass

    def _ip(self):
        return self.client_address[0]

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if origin in TRUSTED_ORIGINS:                 # explicit allowlist, NO wildcard
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(b)

    def _rate_ok(self):
        now = time.time(); ip = self._ip()
        RATE.setdefault(ip, [])
        RATE[ip] = [t for t in RATE[ip] if now - t < 60]
        if len(RATE[ip]) >= 40:
            return False
        RATE[ip].append(now); return True

    def _auth_ok(self):
        # bearer token + CSRF header on state-changing routes
        tok = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if not secrets.compare_digest(tok, ADAPTER_TOKEN):
            return False, "bad or missing bearer token"
        if not self.headers.get("X-Requested-By"):
            return False, "missing X-Requested-By (CSRF) header"
        origin = self.headers.get("Origin")
        if origin and origin not in TRUSTED_ORIGINS:
            return False, "origin not allowlisted"
        return True, ""

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > MAX_BODY:
            return None
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode())
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204); self._cors()
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-By")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def _ip_allowed(self):
        return (not ALLOWED_IPS) or (self._ip() in ALLOWED_IPS)

    def do_GET(self):
        if not self._ip_allowed():
            return self._send(403, {"error": "source ip not allowlisted"})
        p = self.path.split("?")[0]
        if p == "/health":
            return self._send(200, {"ok": True, "service": "qsb_brain_cage_adapter", "bind": "localhost-first",
                                    "ts": utc(), "live_router_8860": "untouched"})
        ro = {
            "/api/brain-cage/provider": provider_view,
            "/api/brain-cage/status": lambda: {"provider": provider_view(), "jobs": len(load_jobs()),
                                               "usage_state": "OK", "ts": utc()},
            "/api/brain-cage/jobs": load_jobs,
            "/api/brain-cage/requesters": lambda: {"allowed": sorted(ALLOWED_REQUESTERS),
                                                   "physical": PHYSICAL, "retired": RETIRED,
                                                   "surrogate_rejected_as_physical": True},
            "/api/brain-cage/usage-state": lambda: {"state": "OK", "sentinel": "MAX_USAGE_LIMIT_REACHED_NO_PAID_FALLBACK",
                                                    "paid_fallback": False, "api_key_present": False},
            "/api/brain-cage/evidence": lambda: {"audit_rows": AUDIT.exists() and len(AUDIT.read_text().splitlines()) or 0},
        }
        if p in ro:
            try:
                return self._send(200, ro[p]())
            except Exception as e:
                return self._send(500, {"error": str(e)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._ip_allowed():
            return self._send(403, {"error": "source ip not allowlisted"})
        p = self.path.split("?")[0]
        if not self._rate_ok():
            return self._send(429, {"error": "rate limited"})
        ok, why = self._auth_ok()
        if not ok:
            return self._send(401, {"error": why})
        b = self._body()
        if b is None:
            return self._send(413, {"error": "body too large or malformed"})
        jobs = load_jobs()
        ip = self._ip()

        if p == "/api/brain-cage/draft":
            rid = str(b.get("requester_id", ""))
            q = str(b.get("question", "")).strip()
            mode = str(b.get("mode", "CHAT_ONLY"))
            if mode not in MODES:
                return self._send(400, {"error": "bad mode"})
            if not q:
                return self._send(400, {"error": "empty question"})
            ok2, cls, reason = classify(rid, ip, str(b.get("requester_origin", "")))
            if not ok2:
                audit({"event": "requester_rejected", "requester": rid, "ip": ip, "reason": reason})
                return self._send(403, {"error": "requester rejected", "reason": reason, "classification": cls})
            job = "%s_%d" % (PREFIX[rid], int(time.time()))
            if not JOB_RX.match(job):
                return self._send(500, {"error": "job id build failed"})
            rec = {"job_id": job, "requester_id": rid, "classification": cls, "requester_ip": ip,
                   "hostname": HOSTNAMES.get(rid, ""), "question": q, "mode": mode, "risk": "low" if mode in ("CHAT_ONLY", "READ_ONLY_REVIEW") else "medium",
                   "state": "DRAFT", "created": utc(), "wren_verdict": None, "ross_approval": "PENDING",
                   "policy_checksum": (sha(POLICY) or "")[:16], "verifier_checksum": (sha(VERIFIER) or "")[:16]}
            jobs[job] = rec; save_jobs(jobs)
            # real Task Council record (DRAFT) — never auto-completed
            council_write({"task_id": "brain_" + job, "title": "[brain-cage] %s: %s" % (rid, q[:60]),
                           "owner": rid, "peer": "claude_hq", "verifier": "qsb_governor_verifier",
                           "state": "DRAFT", "verdict": None, "source": "brain_cage_adapter", "ts": utc()})
            audit({"event": "draft", "job": job, "requester": rid, "ip": ip, "mode": mode})
            return self._send(200, {"ok": True, "job": rec, "event_id": "draft_" + job})

        job = str(b.get("job", ""))
        if not JOB_RX.match(job):
            return self._send(400, {"error": "bad job id"})
        rec = jobs.get(job)
        if not rec:
            return self._send(404, {"error": "no such job"})

        if p == "/api/brain-cage/send-to-wren":
            note, vd = wren_review(rec["requester_id"], rec["question"], rec["mode"])
            rec.update({"state": "WREN_REVIEW", "wren_note": note, "wren_verdict": vd,
                        "state_after_wren": "AWAITING_ROSS"}); save_jobs(jobs)
            council_write({"task_id": "brain_" + job, "state": "WREN_REVIEW", "verdict": vd, "ts": utc(), "source": "brain_cage_adapter"})
            audit({"event": "wren_review", "job": job, "verdict": vd})
            return self._send(200, {"ok": True, "wren_verdict": vd, "wren_note": note, "job": rec})

        if p == "/api/brain-cage/approve":
            # ROSS approval only (commissioning). Requester may NOT self-approve.
            actor = str(b.get("actor", ""))
            if actor != "ross":
                return self._send(403, {"error": "only Ross may approve during commissioning", "actor": actor})
            if rec.get("state") != "WREN_REVIEW":
                return self._send(409, {"error": "must be Wren-reviewed first"})
            rec.update({"state": "APPROVED", "ross_approval": "APPROVED", "approved_ts": utc()}); save_jobs(jobs)
            council_write({"task_id": "brain_" + job, "state": "APPROVED", "ts": utc(), "source": "brain_cage_adapter", "approver": "ross"})
            audit({"event": "ross_approved", "job": job})
            return self._send(200, {"ok": True, "job": rec})

        if p == "/api/brain-cage/launch":
            if rec.get("state") != "APPROVED":
                return self._send(409, {"error": "job not Ross-approved"})
            sim = bool(b.get("simulate_max_exhausted", False))
            rec["state"] = "RUNNING"; save_jobs(jobs)
            res = run_cage(job, rec["requester_id"], rec["question"], rec["mode"], simulate_max_exhausted=sim)
            if res.get("sentinel"):
                rec.update({"state": "WAITING_FOR_MAX_RESET", "sentinel": res["sentinel"], "result": res}); save_jobs(jobs)
                council_write({"task_id": "brain_" + job, "state": "WAITING_FOR_MAX_RESET", "ts": utc(), "source": "brain_cage_adapter"})
                audit({"event": "max_exhausted_sentinel", "job": job})
                return self._send(200, {"ok": False, "sentinel": res["sentinel"], "job": rec, "result": res})
            rec.update({"state": res.get("final_state") or "READY_FOR_ROSS", "result": res,
                        "response": res.get("response")}); save_jobs(jobs)
            council_write({"task_id": "brain_" + job, "state": "READY_FOR_ROSS",
                           "verdict": res.get("verifier_result"), "ts": utc(), "source": "brain_cage_adapter"})
            audit({"event": "launched", "job": job, "verifier": res.get("verifier_result"),
                   "cage_closed": res.get("cage_closed"), "auth": res.get("auth")})
            return self._send(200, {"ok": bool(res.get("response")), "job": rec, "result": res})

        if p in ("/api/brain-cage/freeze", "/api/brain-cage/stop"):
            cage_ctl("stop", job)
            rec["state"] = "FROZEN"; save_jobs(jobs)
            audit({"event": p.rsplit("/", 1)[-1], "job": job})
            return self._send(200, {"ok": True, "job": rec})

        if p == "/api/brain-cage/request-evidence":
            rec["evidence_requested"] = utc(); save_jobs(jobs)
            return self._send(200, {"ok": True, "job": rec})

        if p == "/api/brain-cage/prepare-review":
            return self._send(200, {"ok": True, "note": "Only Ross may ACCEPT. Requesters/Wren/Claude cannot final-accept.",
                                    "ready": [v for v in jobs.values() if v.get("state") == "READY_FOR_ROSS"]})
        return self._send(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8859)
    ap.add_argument("--host", default="127.0.0.1")     # localhost-first
    ap.add_argument("--allow-ips", default="")          # comma list; when set, ONLY these source IPs are served
    a = ap.parse_args()
    global ALLOWED_IPS
    if a.allow_ips.strip():
        ALLOWED_IPS = set(x.strip() for x in a.allow_ips.split(",") if x.strip()) | {"127.0.0.1", "::1"}
    print("Brain Cage Adapter on http://%s:%d — token at %s — allow_ips=%s — live router :8860 untouched"
          % (a.host, a.port, TOKEN_FILE, sorted(ALLOWED_IPS) or "localhost-only"))
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()


if __name__ == "__main__":
    main()
