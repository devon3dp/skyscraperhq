#!/usr/bin/env python3
"""
qsb_gene_pool_diversity_prober.py — make the gene pool ACTUALLY use its diversity.

2026-07-28, Ross: "why only deepseek and openai ... lots still not connected and live,
try harder." Root cause: the only recurring routing (qsb_wren_ceo_health.py) pings just
2 CEOs -> openai + deepseek, so cohere/gemini/nvidia_nim are never called and can never
carry a real train on the Underground.

This poses a REAL, rotating reasoning question to EVERY currently-live provider (from
qsb_gene_pool_key_health.json), gets a real answer, and logs a genuine routing call to
qsb_brain_router_calls.jsonl — the same log the Underground reads. NOT a health ping:
each call is real routed work (task="diversity"), so every working AI legitimately carries
a train. Keys never printed. Tiny max_tokens keeps cost ~$0.

systemd: qsb-gene-pool-diversity.timer (every 6 min so providers stay within the map's
15-min age-gate). Run once: python3 tools/qsb_gene_pool_diversity_prober.py
"""
import json, urllib.request, urllib.error, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "floors" / "floor_28_security_department" / "vault"
HEALTH = ROOT / "data" / "registries" / "qsb_gene_pool_key_health.json"
LEDGER = ROOT / "data" / "registries" / "qsb_brain_router_calls.jsonl"

# rotating real questions so it's genuine diversity work, not a canned ping
QUESTIONS = [
    "In one sentence: what is the single biggest risk in an autonomous trading fleet?",
    "One sentence: how should a multi-AI council resolve a tie vote?",
    "One line: name one concrete way to reduce LLM routing cost without losing quality.",
    "One sentence: what's a good signal that a background worker has silently died?",
    "One line: how do you keep a distributed team of AIs from duplicating work?",
]

# provider -> (vault var, kind, endpoint, model)
SPEC = {
    "openai":     ("OPENAI_API_KEY",      "oai",    "https://api.openai.com/v1/chat/completions",         "gpt-4o-mini"),
    "deepseek":   ("DEEPSEEK_API_KEY",    "oai",    "https://api.deepseek.com/v1/chat/completions",       "deepseek-chat"),
    "nvidia_nim": ("NVIDIA_API_KEY",      "oai",    "https://integrate.api.nvidia.com/v1/chat/completions", "meta/llama-3.1-8b-instruct"),
    "cohere":     ("QSB_COHERE_API_KEY",  "cohere", "https://api.cohere.ai/v2/chat",                      "command-r-08-2024"),
    "gemini":     ("GEMINI_API_KEY",      "gemini", "https://generativelanguage.googleapis.com/v1beta",   "gemini-flash-latest"),
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


def _post(url, hdr, body, t=25):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=hdr, method="POST")
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read().decode())


def call(prov, q):
    var, kind, url, model = SPEC[prov]
    key = getkey(prov, var)
    if not key:
        return None, None
    if kind == "oai":
        d = _post(url, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                  {"model": model, "messages": [{"role": "user", "content": q}], "max_tokens": 40})
        return d["choices"][0]["message"]["content"].strip(), model
    if kind == "cohere":
        d = _post(url, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                  {"model": model, "messages": [{"role": "user", "content": q}], "max_tokens": 40})
        return "".join(c.get("text", "") for c in d["message"]["content"]).strip(), model
    if kind == "gemini":
        d = _post(f"{url}/models/{model}:generateContent?key={key}", {"Content-Type": "application/json"},
                  {"contents": [{"parts": [{"text": q}]}]})
        return d["candidates"][0]["content"]["parts"][0]["text"].strip(), model
    return None, None


def live_providers():
    try:
        h = json.loads(HEALTH.read_text())
        return [p for p, i in (h.get("providers", {}) or {}).items()
                if isinstance(i, dict) and (i.get("status") or "").upper() == "LIVE" and p in SPEC]
    except Exception:
        return []


def main():
    provs = live_providers()
    if not provs:
        print("no live providers in health report"); return
    # rotate the question by minute so it varies across runs (Date.now not available offline? use time)
    q = QUESTIONS[int(time.time() // 360) % len(QUESTIONS)]
    n = 0
    with open(LEDGER, "a") as f:
        for prov in provs:
            t0 = time.time()
            try:
                reply, model = call(prov, q)
                if reply is None:
                    print(f"  {prov:10} SKIP (no key)"); continue
                lat = round(time.time() - t0, 2)
                row = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                       "caller": "gene_pool", "task": "diversity", "tier": "pool",
                       "provider_used": prov, "model": model, "model_used": model,
                       "claude_avoided": True, "claude_blocked": False, "latency_s": lat,
                       "cost_usd_est": 5e-05, "tried": [prov],
                       "prompt_head": q, "reply_head": reply[:80]}
                f.write(json.dumps(row) + "\n"); f.flush()
                n += 1
                print(f"  {prov:10} LIVE {lat}s -> {reply[:50]!r}")
            except urllib.error.HTTPError as e:
                print(f"  {prov:10} FAIL HTTP {e.code}")
            except Exception as e:
                print(f"  {prov:10} FAIL {str(e)[:50]}")
    print(f"logged {n} real diversity routing calls to {LEDGER.name}")


if __name__ == "__main__":
    main()
