#!/usr/bin/env python3
"""
QSB LOCAL BRAIN ROUTER  (action_id=FEDERATED-PHYSICAL-BRAIN-ROUTERS-V1)

A self-contained, localhost-only federated brain node that runs ON each physical
worker laptop (Acer-Cass, TP-Pip). It makes the laptop an INDEPENDENT SkyscraperHQ
node: it routes ordinary inference to the LOCAL model first, keeps a durable local
task queue and an append-only hash-chained evidence ledger, enforces an OFFLINE
governance policy, and reports whether HQ is reachable (ONLINE_FEDERATED) or not
(OFFLINE_INDEPENDENT) -- continuing to serve local work either way.

HARD GUARANTEES (by construction):
  * Binds 127.0.0.1 only. Never 0.0.0.0.
  * NO central secrets: no Claude OAuth, no adapter bearer, no ANTHROPIC_API_KEY,
    no provider keys. The local gene pool lists central providers only as
    UNAVAILABLE_GOVERNED pointers with no credentials.
  * Ordinary local inference NEVER depends on HQ: it goes straight to the local
    ollama at 127.0.0.1:11434. HQ is consulted only for federated sync/escalation
    and its absence downgrades to OFFLINE_INDEPENDENT, it does not block local work.
  * A worker can NEVER final-accept / approve / launch its own work, spend real
    money, place orders, flip gates, read secrets, or make paid provider calls.
    Those task classes are QUEUED for Ross/Wren, never executed locally.
  * Reads worker identity from a local per-worker config; never mixes identities.

Config (per laptop, no secrets), under <qsb>/config/:
  local_gene_pool.json        local model registry + governed central pointers
  local_governor_policy.json  offline governance policy (allow/escalate classes)
  <worker>_node.json          {worker_id,name,floor,hq_status_url,hq_sync_url}
Data (per laptop, append-only), under <qsb>/data/:
  local_task_queue.jsonl      durable task lifecycle transitions
  local_evidence.jsonl        hash-chained evidence ledger
Runtime:
  runtime/local_service_token  locally-generated bearer for POSTs (0600), NOT central
"""
import os, sys, json, time, hashlib, secrets, argparse, urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

QSB = Path(os.environ.get("QSB_HOME", str(Path.home() / "qsb")))
CFG = QSB / "config"
DAT = QSB / "data"
RUN = QSB / "runtime"
for d in (CFG, DAT, RUN):
    d.mkdir(parents=True, exist_ok=True)

GENE_POOL = CFG / "local_gene_pool.json"
POLICY = CFG / "local_governor_policy.json"
QUEUE = DAT / "local_task_queue.jsonl"
EVIDENCE = DAT / "local_evidence.jsonl"
TOKEN_FILE = RUN / "local_service_token"

LOCAL_OLLAMA = os.environ.get("QSB_LOCAL_OLLAMA", "http://127.0.0.1:11434")

# Task classes that MUST be escalated to Ross/Wren and never executed locally.
ESCALATE_CLASSES = {
    "approve", "final_accept", "self_accept", "launch", "start_approved_job",
    "real_money", "order_execution", "gate_flip", "secret_access",
    "paid_provider_call", "cross_worker_identity", "account_management",
}
# Task classes a worker may fully serve locally, offline, with no human.
LOCAL_CLASSES = {
    "local_inference", "draft", "summarise", "self_reflection", "memory_recall",
    "local_analysis", "competition_artifact_draft", "review_own_notes", "chat",
}


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def _service_token():
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    tok = secrets.token_urlsafe(32)
    TOKEN_FILE.write_text(tok, encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except Exception:
        pass
    return tok


# ------------------------------------------------------------------ evidence
def _last_evidence_hash():
    if not EVIDENCE.exists():
        return "GENESIS"
    last = "GENESIS"
    with open(EVIDENCE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line).get("row_hash", last)
            except Exception:
                pass
    return last


def append_evidence(kind, payload):
    """Append-only, hash-chained. row_hash = sha256(prev_hash + canonical(body))."""
    prev = _last_evidence_hash()
    body = {"ts": utc(), "kind": kind, "prev_hash": prev, "payload": payload}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["row_hash"] = hashlib.sha256((prev + canonical).encode()).hexdigest()
    with open(EVIDENCE, "a", encoding="utf-8") as f:
        f.write(json.dumps(body) + "\n")
    return body["row_hash"]


def verify_evidence_chain():
    prev = "GENESIS"
    n = 0
    if not EVIDENCE.exists():
        return True, 0
    with open(EVIDENCE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            body = {k: row[k] for k in ("ts", "kind", "prev_hash", "payload")}
            canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
            expect = hashlib.sha256((prev + canonical).encode()).hexdigest()
            if row.get("prev_hash") != prev or row.get("row_hash") != expect:
                return False, n
            prev = row["row_hash"]
            n += 1
    return True, n


# ------------------------------------------------------------------ queue
def append_queue(task_id, state, extra=None):
    row = {"ts": utc(), "task_id": task_id, "state": state}
    if extra:
        row.update(extra)
    with open(QUEUE, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def queue_snapshot():
    """Latest state per task_id from the append-only log."""
    latest = {}
    if QUEUE.exists():
        with open(QUEUE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    latest[r["task_id"]] = r
                except Exception:
                    pass
    return list(latest.values())


# ------------------------------------------------------------------ HQ status
def hq_status(node_cfg, timeout=1.5):
    url = node_cfg.get("hq_status_url")
    if not url:
        return {"mode": "OFFLINE_INDEPENDENT", "hq_reachable": False, "reason": "no hq_status_url"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "qsb-local-node"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ok = 200 <= r.status < 500
        return {"mode": "ONLINE_FEDERATED" if ok else "OFFLINE_INDEPENDENT",
                "hq_reachable": ok, "hq_url": url}
    except Exception as e:
        return {"mode": "OFFLINE_INDEPENDENT", "hq_reachable": False,
                "hq_url": url, "reason": type(e).__name__}


# ------------------------------------------------------------------ local model
def local_infer(prompt, model, timeout=60):
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(LOCAL_OLLAMA + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return data.get("response", "")


# ------------------------------------------------------------------ routing
def classify(task_class, text):
    tc = (task_class or "").strip().lower()
    if tc in ESCALATE_CLASSES:
        return "ESCALATE", tc
    if tc in LOCAL_CLASSES:
        return "LOCAL", tc
    # unknown class: safe default is escalate unless it is plainly local chat/inference
    low = (text or "").lower()
    if any(w in low for w in ("approve", "launch", "final accept", "real money",
                              "place order", "flip gate", "secret", "credential", "api key")):
        return "ESCALATE", tc or "unknown_highrisk"
    return "LOCAL", tc or "local_inference"


def route_local_task(node_cfg, gene_pool, task_class, text):
    tid = "lt_" + secrets.token_hex(6)
    decision, norm = classify(task_class, text)
    append_queue(tid, "submitted", {"class": norm, "decision": decision})
    if decision == "ESCALATE":
        append_queue(tid, "WAITING_FOR_ROSS_WREN",
                     {"class": norm, "reason": "requires human authority; not executable locally"})
        ev = append_evidence("task_escalated",
                             {"task_id": tid, "class": norm, "worker": node_cfg.get("worker_id")})
        return {"task_id": tid, "decision": "ESCALATED",
                "state": "WAITING_FOR_ROSS_WREN", "evidence": ev,
                "note": "A worker cannot approve/launch/final-accept/real-money/secret/gate locally."}
    # LOCAL path: use the local active model from the gene pool, offline-capable
    model = None
    for prov in gene_pool.get("providers", []):
        if prov.get("locus") == "local" and prov.get("status") == "ACTIVE":
            model = prov.get("model")
            break
    model = model or "llama3.2"
    append_queue(tid, "running_local", {"class": norm, "model": model})
    try:
        out = local_infer(text, model)
        append_queue(tid, "done_local", {"class": norm, "model": model})
        ev = append_evidence("task_local_done",
                             {"task_id": tid, "class": norm, "model": model,
                              "worker": node_cfg.get("worker_id"), "chars": len(out)})
        return {"task_id": tid, "decision": "LOCAL", "state": "done_local",
                "model": model, "endpoint": LOCAL_OLLAMA, "evidence": ev, "output": out}
    except Exception as e:
        append_queue(tid, "error_local", {"class": norm, "error": type(e).__name__})
        ev = append_evidence("task_local_error",
                             {"task_id": tid, "class": norm, "error": type(e).__name__})
        return {"task_id": tid, "decision": "LOCAL", "state": "error_local",
                "error": type(e).__name__, "evidence": ev}


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "qsb-local-node/1.0"

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _authed(self):
        got = self.headers.get("X-Service-Token", "")
        return bool(got) and secrets.compare_digest(got, self.server.token)

    def do_GET(self):
        p = self.path.split("?", 1)[0]
        cfg = self.server.node_cfg
        gp = _load_json(GENE_POOL, {"providers": []})
        if p == "/health":
            ok, n = verify_evidence_chain()
            self._send(200, {"ok": True, "worker_id": cfg.get("worker_id"),
                             "name": cfg.get("name"), "floor": cfg.get("floor"),
                             "bind": "127.0.0.1:%d" % self.server.server_port,
                             "evidence_chain_ok": ok, "evidence_rows": n, "ts": utc()})
        elif p == "/providers":
            self._send(200, {"worker_id": cfg.get("worker_id"),
                             "local_ollama": LOCAL_OLLAMA, "gene_pool": gp})
        elif p == "/status":
            hs = hq_status(cfg)
            ok, n = verify_evidence_chain()
            self._send(200, {"worker_id": cfg.get("worker_id"), "name": cfg.get("name"),
                             "federation_mode": hs["mode"], "hq": hs,
                             "local_first": True, "offline_capable": True,
                             "evidence_chain_ok": ok, "evidence_rows": n,
                             "queue_depth": len(queue_snapshot()), "ts": utc()})
        elif p == "/queue":
            self._send(200, {"tasks": queue_snapshot()})
        elif p == "/evidence":
            ok, n = verify_evidence_chain()
            tail = []
            if EVIDENCE.exists():
                lines = [l for l in EVIDENCE.read_text(encoding="utf-8").splitlines() if l.strip()]
                tail = [json.loads(l) for l in lines[-20:]]
            self._send(200, {"chain_ok": ok, "rows": n, "tail": tail})
        elif p == "/sync-status":
            hs = hq_status(cfg)
            self._send(200, {"federation_mode": hs["mode"], "hq_reachable": hs["hq_reachable"],
                             "pending_escalations": [t for t in queue_snapshot()
                                                     if t.get("state") == "WAITING_FOR_ROSS_WREN"],
                             "ts": utc()})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        p = self.path.split("?", 1)[0]
        cfg = self.server.node_cfg
        if not self._authed():
            self._send(401, {"error": "unauthorized (X-Service-Token required)"})
            return
        ln = int(self.headers.get("Content-Length", "0") or "0")
        if ln > 256 * 1024:
            self._send(413, {"error": "too large"})
            return
        try:
            data = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            self._send(400, {"error": "bad json"})
            return
        gp = _load_json(GENE_POOL, {"providers": []})
        if p == "/submit-local-task":
            res = route_local_task(cfg, gp, data.get("class"), data.get("text", ""))
            self._send(200, res)
        elif p == "/queue-for-hq":
            tid = "hq_" + secrets.token_hex(6)
            append_queue(tid, "queued_for_hq", {"reason": data.get("reason", ""),
                                                "class": data.get("class", "")})
            ev = append_evidence("queued_for_hq", {"task_id": tid, "worker": cfg.get("worker_id"),
                                                   "reason": data.get("reason", "")})
            self._send(200, {"task_id": tid, "state": "queued_for_hq", "evidence": ev})
        else:
            self._send(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node-config", required=True, help="path to <worker>_node.json")
    ap.add_argument("--port", type=int, default=9130)
    a = ap.parse_args()
    node_cfg = _load_json(a.node_config, {})
    if not node_cfg.get("worker_id"):
        print("FATAL: node config missing worker_id:", a.node_config)
        sys.exit(2)
    token = _service_token()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    srv.token = token
    srv.node_cfg = node_cfg
    append_evidence("node_start", {"worker": node_cfg.get("worker_id"),
                                   "port": a.port, "bind": "127.0.0.1"})
    print("QSB local brain router: worker=%s bind=127.0.0.1:%d local_ollama=%s"
          % (node_cfg.get("worker_id"), a.port, LOCAL_OLLAMA))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
