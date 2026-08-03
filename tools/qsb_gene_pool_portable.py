#!/usr/bin/env python3
"""qsb_gene_pool — portable multi-provider brain-router (a copy of Bill's Floor-47 gene pool).

A "second opinion" engine for any node (TP-Pip, Acer-Cass, Wren, …): it routes a question,
via a brain-router, to the best LIVE provider for the task, with auto-failover + a healer.
Keep your own model as the primary brain — use this for second opinions / hard questions.

USAGE
  python3 gene_pool.py "your question"          # ask (routes to best live provider)
  python3 gene_pool.py --health                 # ping every provider, show live/down + latency
  python3 gene_pool.py --serve 8790             # run as an HTTP service: GET /ask?q=... , /health

KEYS  (0600, never commit): put them in gene_pool_keys.json next to this file, OR the env:
  { "OPENAI_API_KEY":"…","DEEPSEEK_API_KEY":"…","OPENROUTER_API_KEY":"…","ZAI_API_KEY":"…",
    "NVIDIA_API_KEY":"…","SAMBANOVA_API_KEY":"…","COHERE_API_KEY":"…","GROQ_API_KEY":"…","GEMINI_API_KEY":"…" }

Every provider is an OpenAI-compatible /chat/completions endpoint. Built on Floor 47, 2026-08.
"""
import json, os, sys, time, urllib.request, urllib.parse, http.server, socketserver

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_keys():
    d = dict(os.environ)
    try:
        d.update(json.load(open(os.path.join(HERE, "gene_pool_keys.json"))))
    except Exception:
        pass
    return d


KEYS = _load_keys()

# Priority order = fastest/most-reliable first; each provider gets its own timeout.
PROVIDERS = [
    {"name": "openai",     "key": "OPENAI_API_KEY",     "url": "https://api.openai.com/v1/chat/completions",             "model": "gpt-4o-mini",                 "timeout": 40},
    {"name": "deepseek",   "key": "DEEPSEEK_API_KEY",   "url": "https://api.deepseek.com/chat/completions",              "model": "deepseek-chat",               "timeout": 40},
    {"name": "sambanova",  "key": "SAMBANOVA_API_KEY",  "url": "https://api.sambanova.ai/v1/chat/completions",           "model": "Meta-Llama-3.3-70B-Instruct", "timeout": 40},
    {"name": "openrouter", "key": "OPENROUTER_API_KEY", "url": "https://openrouter.ai/api/v1/chat/completions",          "model": "poolside/laguna-s-2.1:free",  "timeout": 45},
    {"name": "zai",        "key": "ZAI_API_KEY",        "url": "https://api.z.ai/api/paas/v4/chat/completions",          "model": "glm-4.5-flash",               "timeout": 45, "extra": {"thinking": {"type": "disabled"}}},
    {"name": "nvidia",     "key": "NVIDIA_API_KEY",     "url": "https://integrate.api.nvidia.com/v1/chat/completions",   "model": "meta/llama-3.3-70b-instruct", "timeout": 55},
    {"name": "cohere",     "key": "COHERE_API_KEY",     "url": "https://api.cohere.ai/compatibility/v1/chat/completions", "model": "command-r-08-2024",          "timeout": 35},
    {"name": "groq",       "key": "GROQ_API_KEY",       "url": "https://api.groq.com/openai/v1/chat/completions",        "model": "llama-3.3-70b-versatile",     "timeout": 30},
    {"name": "gemini",     "key": "GEMINI_API_KEY",     "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "model": "gemini-2.0-flash", "timeout": 30},
]

# Brain-router: pick providers best-for-the-task first (then default priority).
ROUTES = [
    ("code",      ("code", "function", "python", "javascript", "sql", "regex", "bug", "debug", "api", "json"),
     ["deepseek", "zai", "openai", "openrouter"]),
    ("reasoning", ("prove", "reason", "analyse", "analyze", "step by step", "why does", "in depth", "trade-off", "strategy"),
     ["deepseek", "nvidia", "sambanova", "openai", "zai"]),
    ("math",      ("calculate", "solve", "equation", "probability", "integral", "derivative"),
     ["deepseek", "openai", "zai"]),
]
HEALTH = {}


def _key(p):
    return str(KEYS.get(p["key"], "")).strip()


def _call(p, question, max_tokens=700, timeout=None):
    key = _key(p)
    if not key:
        raise RuntimeError("no key")
    body = {"model": p["model"],
            "messages": [{"role": "system", "content": "You are a precise, factual adviser. Be clear and concise."},
                         {"role": "user", "content": question[:2000]}],
            "max_tokens": max_tokens, "temperature": 0.4}
    body.update(p.get("extra", {}))
    req = urllib.request.Request(p["url"], data=json.dumps(body).encode(), headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
        "HTTP-Referer": "https://skyscraperhq.local", "X-Title": "QSB Gene Pool"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout or p.get("timeout", 40)) as r:
        d = json.load(r)
    m = (d.get("choices") or [{}])[0].get("message", {})
    ans = (m.get("content") or m.get("reasoning_content") or "").strip()
    if not ans:
        raise RuntimeError("empty")
    return ans, time.time() - t0


def _route(q):
    ql = q.lower()
    task, pref = "general", []
    for name, kws, order in ROUTES:
        if any(k in ql for k in kws):
            task, pref = name, order
            break
    by = {p["name"]: p for p in PROVIDERS}
    ordered = [by[n] for n in pref if n in by]
    ordered += [p for p in PROVIDERS if p["name"] not in {x["name"] for x in ordered}]
    return task, ordered


def ask(question):
    task, provs = _route(question)
    tried = []
    for p in provs:
        if not _key(p):
            continue
        h = HEALTH.get(p["name"], {})
        if h.get("ok") is False and time.time() - h.get("checked", 0) < 300:
            tried.append(p["name"] + "(down)"); continue
        try:
            a, dt = _call(p, question)
            return {"ok": True, "answer": a, "provider": p["name"], "model": p["model"],
                    "task": task, "latency_ms": int(dt * 1000)}
        except Exception as e:
            tried.append("%s(%s)" % (p["name"], str(e)[:18]))
    return {"ok": False, "task": task, "reason": "no provider answered — " + (", ".join(tried) or "no keys")}


def heal():
    for p in PROVIDERS:
        if not _key(p):
            HEALTH[p["name"]] = {"ok": None, "has_key": False}; continue
        try:
            _a, dt = _call(p, "Reply with just: OK", max_tokens=5, timeout=20)
            HEALTH[p["name"]] = {"ok": True, "latency_ms": int(dt * 1000), "checked": time.time()}
        except Exception as e:
            HEALTH[p["name"]] = {"ok": False, "error": str(e)[:80], "checked": time.time()}
    return HEALTH


def _serve(port):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path == "/health":
                out = heal()
            elif u.path == "/ask":
                out = ask((q.get("q") or [""])[0])
            else:
                out = {"ok": True, "service": "qsb_gene_pool", "providers": [p["name"] for p in PROVIDERS]}
            b = json.dumps(out).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    print("qsb_gene_pool serving on 0.0.0.0:%d  (GET /ask?q=…  /health)" % port)
    socketserver.ThreadingTCPServer(("0.0.0.0", port), H).serve_forever()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(0)
    if sys.argv[1] == "--serve":
        _serve(int(sys.argv[2]) if len(sys.argv) > 2 else 8790)
    elif sys.argv[1] == "--health":
        for n, h in heal().items():
            st = ("live %sms" % h.get("latency_ms")) if h.get("ok") else ("no key" if h.get("has_key") is False else "down: " + str(h.get("error", "")))
            print("  %-11s %s" % (n, st))
    else:
        r = ask(" ".join(sys.argv[1:]))
        print(r["answer"] + "\n\n— via gene pool (%s · %s · %sms)" % (r["provider"], r["model"], r["latency_ms"]) if r.get("ok") else "gene pool: " + r.get("reason", ""))
