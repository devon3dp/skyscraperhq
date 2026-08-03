#!/usr/bin/env python3
"""QSB per-box GENE POOL — a live resource / info-collection service.

IMPORTANT (Ross 2026-07-24): this is a GENE POOL, NOT a brain router. It has
NOTHING to do with the resident's brain. The resident's BRAIN is its local
Ollama model (llama3.2 / qwen), served by the cockpit (:9120) and ollama
(:11434) — that is the mind that thinks, decides and owns the answer.

The GENE POOL is a RESOURCE the brain USES: it goes out to EXTERNAL / diverse
providers (DeepSeek now, extensible) to COLLECT live information, second
opinions and specialist material. It never speaks AS the resident and it never
routes to the local brain. When offline it honestly has no live resources to
collect — the brain still works standalone via the cockpit.

Endpoints:
  GET  /health                      -> status + which providers are reachable
  GET  /recent?n=10                 -> recent collection results (for the dash)
  POST /collect  {"query":"..."}    -> collect live info from external providers,
                                       log it, and return the labelled material
Usage:
  python qsb_box_gene_pool.py --collect "latest on X"    # one-shot
  python qsb_box_gene_pool.py --serve --port 8770        # HTTP service
"""
import argparse, json, os, time, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "gene_pool_results.jsonl")   # rolling log the dash reads
MAX_LOG = 200


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


# ---- EXTERNAL providers = the gene pool. NOT the local brain, NEVER Claude account. ----
def _deepseek(query):
    key = _load_env(".env.genepool").get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("no deepseek key on box")
    body = json.dumps({"model": "deepseek-chat",
                       "messages": [{"role": "user", "content": query}]}).encode()
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=body,
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"}, method="POST")
    j = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
    return j["choices"][0]["message"]["content"]


PROVIDERS = [("deepseek", "deepseek-chat", _deepseek)]


def _providers_reachable():
    """A provider is 'available' if its key is present (real reachability proven on collect)."""
    env = _load_env(".env.genepool")
    return [name for name, _model, _fn in PROVIDERS
            if (name == "deepseek" and env.get("DEEPSEEK_API_KEY"))]


def _log(rec):
    try:
        lines = []
        if os.path.exists(RESULTS):
            lines = open(RESULTS, encoding="utf-8").read().splitlines()[-(MAX_LOG - 1):]
        lines.append(json.dumps(rec))
        open(RESULTS, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    except Exception:
        pass


def collect(query):
    """Collect live info from EXTERNAL providers (the gene pool). Returns labelled
    material for the brain to judge — this is a RESOURCE, not the resident's voice."""
    t0 = time.time()
    for name, model, fn in PROVIDERS:
        try:
            material = fn(query)
            if material and material.strip():
                rec = {"ts": _utc(), "kind": "gene_pool_resource", "ok": True,
                       "query": query[:200], "provider": name, "model": model,
                       "material": material.strip(),
                       "label": "advice/info collected by the gene pool for the resident to judge — NOT the resident's own answer",
                       "latency_s": round(time.time() - t0, 1)}
                _log(rec)
                return rec
        except Exception as e:
            last = name + ": " + str(e)[:100]
            continue
    rec = {"ts": _utc(), "kind": "gene_pool_resource", "ok": False, "query": query[:200],
           "error": "no live resources (offline or all providers failed) — brain works standalone via the cockpit",
           "detail": locals().get("last", ""), "latency_s": round(time.time() - t0, 1)}
    _log(rec)
    return rec


def recent(n=10):
    if not os.path.exists(RESULTS):
        return []
    rows = open(RESULTS, encoding="utf-8").read().splitlines()[-n:]
    out = []
    for r in reversed(rows):
        try:
            out.append(json.loads(r))
        except Exception:
            pass
    return out


def health():
    return {"ok": True, "service": "box_gene_pool",
            "is_a": "live resource / info collector — NOT a brain, NOT a brain router",
            "brain_is_separate": "resident brain = local ollama via cockpit :9120 / :11434",
            "providers_available": _providers_reachable(),
            "results_logged": len(recent(999))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", default=None)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args()
    if a.collect is not None:
        print(json.dumps(collect(a.collect), indent=2)); return
    if a.serve:
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
        from urllib.parse import urlparse, parse_qs

        class H(BaseHTTPRequestHandler):
            def _j(self, obj, code=200):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers(); self.wfile.write(b)

            def do_GET(self):
                u = urlparse(self.path)
                if u.path.startswith("/health"):
                    self._j(health())
                elif u.path.startswith("/recent"):
                    n = int((parse_qs(u.query).get("n", ["10"]))[0])
                    self._j({"ok": True, "results": recent(n)})
                else:
                    self._j({"ok": False}, 404)

            def do_POST(self):
                if self.path.startswith("/collect") or self.path.startswith("/route"):
                    n = int(self.headers.get("Content-Length") or 0)
                    p = json.loads(self.rfile.read(n).decode() or "{}") if n else {}
                    self._j(collect(p.get("query") or p.get("prompt", "")))
                else:
                    self._j({"ok": False}, 404)

            def log_message(self, *a):
                pass

        print("[BOX GENE POOL] serving :%d — live resource collection (external providers), NOT the brain" % a.port)
        ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever(); return
    ap.print_help()


if __name__ == "__main__":
    main()
