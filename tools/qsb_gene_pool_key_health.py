#!/usr/bin/env python3
"""
qsb_gene_pool_key_health.py — LIVE probe of every gene-pool provider's REAL vault key.

2026-07-28, Ross: "in the gene pool there are many ais — why only deepseek and openai?
prove the rest are working ... delete old stale keys? give a notification and options
to change?"

Loads the funded key from floors/floor_28_security_department/vault/.env.<provider>
(the real pasted keys — NOT the harvested gene_pool_keys.secure.env pile, which is mostly
dead fingerprints), fires ONE tiny "reply OK" completion at each provider's real endpoint,
and records the honest status. Keys are never printed or written anywhere.

Writes data/registries/qsb_gene_pool_key_health.json for dashboards/notifications:
  status per provider: LIVE | NO_CREDIT | QUOTA | BLOCKED | ENDPOINT_GONE | NO_KEY | BAD_KEY
Read-only w.r.t. the vault. Run: python3 tools/qsb_gene_pool_key_health.py
"""
import json, urllib.request, urllib.error, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "floors" / "floor_28_security_department" / "vault"
STORE = ROOT / "vaults" / "gene_pool" / "gene_pool_keys.secure.env"
OUT = ROOT / "data" / "registries" / "qsb_gene_pool_key_health.json"
Q = "Reply with exactly: OK"

# provider -> (vault var, kind, endpoint, [models]); kind: oai|cohere|gemini|anthropic
SPEC = {
    "openai":     ("OPENAI_API_KEY",      "oai",    "https://api.openai.com/v1/chat/completions",        ["gpt-4o-mini"]),
    "deepseek":   ("DEEPSEEK_API_KEY",    "oai",    "https://api.deepseek.com/v1/chat/completions",      ["deepseek-chat"]),
    "nvidia_nim": ("NVIDIA_API_KEY",      "oai",    "https://integrate.api.nvidia.com/v1/chat/completions", ["meta/llama-3.1-8b-instruct"]),
    "groq":       ("GROQ_API_KEY",        "oai",    "https://api.groq.com/openai/v1/chat/completions",   ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]),
    "openrouter": ("OPENROUTER_API_KEY",  "oai",    "https://openrouter.ai/api/v1/chat/completions",     ["meta-llama/llama-3.1-8b-instruct"]),
    "sambanova":  ("SAMBANOVA_API_KEY",   "oai",    "https://api.sambanova.ai/v1/chat/completions",      ["Meta-Llama-3.1-8B-Instruct"]),
    "cerebras":   ("CEREBRAS_API_KEY",    "oai",    "https://api.cerebras.ai/v1/chat/completions",       ["llama-3.3-70b", "llama3.1-8b"]),
    "kimi":       ("QSB_KIMI_API_KEY",    "oai",    "https://api.moonshot.ai/v1/chat/completions",       ["moonshot-v1-8k"]),
    "cohere":     ("QSB_COHERE_API_KEY",  "cohere", "https://api.cohere.ai/v2/chat",                     ["command-r-08-2024"]),
    "gemini":     ("GEMINI_API_KEY",      "gemini", "https://generativelanguage.googleapis.com/v1beta",  ["gemini-flash-latest", "gemini-2.0-flash"]),
    "claude":     ("QSB_ANTHROPIC_API_KEY", "anthropic", "https://api.anthropic.com/v1/messages",        ["claude-3-5-haiku-20241022"]),
    "grok":       ("XAI_API_KEY",         "oai",    "https://api.x.ai/v1/chat/completions",              ["grok-2-latest"]),
}


def getkey(prov, var):
    f = VAULT / f".env.{prov}"
    if not f.exists():
        return None
    for l in f.read_text(errors="ignore").splitlines():
        l = l.strip()
        if l.startswith("export "):
            l = l[7:]
        if l.startswith(var + "="):
            return l.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _post(url, hdr, body, t=18):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=hdr, method="POST")
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read().decode())


def classify_http(code):
    if code == 402:
        return "NO_CREDIT"
    if code == 429:
        return "QUOTA"
    if code in (401, 403):
        return "BLOCKED"
    if code == 410:
        return "ENDPOINT_GONE"
    return "BAD_KEY"


def probe(prov, spec):
    var, kind, url, models = spec
    key = getkey(prov, var)
    if not key or len(key) < 20 or "DEL=" in key:
        return {"status": "NO_KEY", "detail": "no funded key in vault"}
    t0 = time.time()
    last = ""
    for m in models:
        try:
            if kind == "oai":
                d = _post(url, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          {"model": m, "messages": [{"role": "user", "content": Q}], "max_tokens": 8})
                txt = d["choices"][0]["message"]["content"].strip()
            elif kind == "cohere":
                d = _post(url, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          {"model": m, "messages": [{"role": "user", "content": Q}], "max_tokens": 8})
                txt = "".join(c.get("text", "") for c in d["message"]["content"]).strip()
            elif kind == "gemini":
                d = _post(f"{url}/models/{m}:generateContent?key={key}", {"Content-Type": "application/json"},
                          {"contents": [{"parts": [{"text": Q}]}]})
                txt = d["candidates"][0]["content"]["parts"][0]["text"].strip()
            elif kind == "anthropic":
                d = _post(url, {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                          {"model": m, "max_tokens": 8, "messages": [{"role": "user", "content": Q}]})
                txt = d["content"][0]["text"].strip()
            return {"status": "LIVE", "detail": f"{txt!r} via {m}", "latency_ms": int((time.time() - t0) * 1000)}
        except urllib.error.HTTPError as e:
            st = classify_http(e.code)
            if st != "BAD_KEY":       # a definitive account state — stop trying more models
                return {"status": st, "detail": f"HTTP {e.code} on {m}"}
            last = f"HTTP {e.code} on {m}"
        except Exception as e:
            last = str(e)[:60]
    return {"status": "BAD_KEY", "detail": last}


def stale_store_counts():
    """How many harvested keys sit in the gene_pool store per provider (the 'old stale' pile)."""
    counts = {}
    try:
        for l in STORE.read_text(errors="ignore").splitlines():
            l = l.strip()
            if not l or l.startswith("#") or "=" not in l:
                continue
            name = l.split("=", 1)[0].lower()
            for p in SPEC:
                if p in name or (p == "claude" and "claude" in name):
                    counts[p] = counts.get(p, 0) + 1
                    break
    except Exception:
        pass
    return counts


def main():
    results = {}
    for prov, spec in SPEC.items():
        results[prov] = probe(prov, spec)
    out = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "providers": results,
        "harvested_store_counts": stale_store_counts(),
        "live": sorted([p for p, r in results.items() if r["status"] == "LIVE"]),
        "needs_new_key": sorted([p for p, r in results.items()
                                 if r["status"] in ("NO_CREDIT", "QUOTA", "BLOCKED", "BAD_KEY", "NO_KEY")]),
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}")
    for p, r in results.items():
        print(f"  {p:12} {r['status']:14} {r.get('detail','')}")
    print("LIVE:", out["live"])
    return out


if __name__ == "__main__":
    main()
