#!/usr/bin/env python3
"""QSB per-box Brain Router / gene pool.

Runs ON a CEO's OWN box (TP-Pip / Acer-Cass) so the CEO keeps multi-mind gene-pool
routing even when HQ is powered OFF. Offline-first: the box's LOCAL Ollama models
are tried first (work with zero internet — boat/cellular safe); remote gene-pool
providers are a bonus when online. NEVER the Claude account (HQ-only).

Usage:
  python qsb_box_gene_router.py --test "hello"          # one-shot, prints route result
  python qsb_box_gene_router.py --serve --port 8770     # HTTP: POST /route {"prompt":"..."}
"""
import argparse
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OLLAMA = "http://127.0.0.1:11434"

# The box's LOCAL gene pool — whatever ollama models are present. llama3.2 is the
# guaranteed one; more local models = more diversity (pull with `ollama pull`).
LOCAL_MODELS = ["llama3.2:latest"]


def _load_env(fname):
    out = {}
    p = os.path.join(HERE, fname)
    if os.path.exists(p):
        for line in open(p, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _local_models_available():
    try:
        r = urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5)
        j = json.loads(r.read().decode())
        return [m["name"] for m in j.get("models", [])]
    except Exception:
        return []


def _ollama(prompt, model):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "stream": False}).encode()
    req = urllib.request.Request(OLLAMA + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=90)
    j = json.loads(r.read().decode())
    return (j.get("message") or {}).get("content", "")


def _deepseek(prompt):
    env = _load_env(".env.genepool")
    key = env.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("no deepseek key on box")
    body = json.dumps({"model": "deepseek-chat",
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=60)
    j = json.loads(r.read().decode())
    return j["choices"][0]["message"]["content"]


REMOTE = [("deepseek", _deepseek)]


def route(prompt):
    """Offline-first: local ollama models, then remote providers. Never Claude account."""
    t0 = time.time()
    last = ""
    avail = _local_models_available()
    for m in LOCAL_MODELS:
        if avail and m not in avail:
            continue
        try:
            rep = _ollama(prompt, m)
            if rep.strip():
                return {"ok": True, "reply": rep, "mind": f"local:{m}",
                        "offline_capable": True, "latency_s": round(time.time() - t0, 1)}
        except Exception as e:
            last = f"local {m}: {str(e)[:80]}"
    for name, fn in REMOTE:
        try:
            rep = fn(prompt)
            if rep.strip():
                return {"ok": True, "reply": rep, "mind": f"remote:{name}",
                        "offline_capable": False, "latency_s": round(time.time() - t0, 1)}
        except Exception as e:
            last = f"{name}: {str(e)[:80]}"
    return {"ok": False, "error": f"all minds failed: {last}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", default=None)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args()
    if a.test is not None:
        print(json.dumps({"local_models": _local_models_available(),
                          "route": route(a.test)}, indent=2))
        return
    if a.serve:
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

        class H(BaseHTTPRequestHandler):
            def _j(self, obj, code=200):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if self.path.startswith("/health"):
                    self._j({"ok": True, "router": "box_gene_pool",
                             "local_models": _local_models_available(),
                             "offline_capable": True})
                else:
                    self._j({"ok": False}, 404)

            def do_POST(self):
                if self.path.startswith("/route"):
                    n = int(self.headers.get("Content-Length") or 0)
                    p = json.loads(self.rfile.read(n).decode() or "{}") if n else {}
                    self._j(route(p.get("prompt", "")))
                else:
                    self._j({"ok": False}, 404)

            def log_message(self, *a):
                pass

        print(f"[BOX GENE ROUTER] serving :{a.port} — local-first, offline-capable")
        ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
        return
    ap.print_help()


if __name__ == "__main__":
    main()
