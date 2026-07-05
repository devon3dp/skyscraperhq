#!/usr/bin/env python3
"""qsb_brain_router.py — multi-provider router for Council brains.

Ross 2026-07-05 signed authorization: DeepSeek + OpenAI are the WORKING agents
(primary workers). Groq + Gemini added as free-tier accelerators. Claude
reserved for hardest tasks only. Ollama = offline last-resort.

Full-control permit: rossknechtel 2026-07-05.

STACK (in fallback order for tier='worker'):
  1. Groq        (free, blazing fast, when key present)
  2. Gemini      (free, long context, when key present)
  3. DeepSeek    (cheap, coder-strong, vault key present)
  4. OpenAI      (advisory-authorized, vault key present)
  5. Ollama LAN  (free local, HQ shared brain)
  6. Ollama loc  (offline last resort on the calling laptop)

STACK for tier='premium':
  1. Claude API  (Anthropic — reserved for hardest tasks)
  2. → falls back to tier='worker' if Claude rate-limited or key missing

USAGE
    python3 tools/qsb_brain_router.py --prompt "sum of 5 primes" [--task chat|code|reason|long] [--tier worker|premium]
    from qsb_brain_router import route
    reply, meta = route("prompt", task="code", tier="worker")

Reads vault keys from:
  floors/floor_28_security_department/vault/.env.groq       (optional, template exists)
  floors/floor_28_security_department/vault/.env.gemini     (optional, template exists)
  floors/floor_28_security_department/vault/.env.deepseek   (existing, authorized)
  floors/floor_28_security_department/vault/.env.openai     (existing, authorized)

Logs every call to:
  data/registries/qsb_brain_router_calls.jsonl
    {ts, caller, task, tier, provider_tried:[..], provider_used, model, latency_s, cost_usd_estimated, prompt_head, reply_head}

Offline-safe: any unreachable provider is skipped silently, next one tries.
"""
from __future__ import annotations
import argparse, json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
VAULT = ROOT / "floors/floor_28_security_department/vault"
REG = ROOT / "data/registries"
LEDGER = REG / "qsb_brain_router_calls.jsonl"


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _load_env(name: str) -> dict:
    """Read .env.NAME file into a dict. Missing → empty dict (silent)."""
    p = VAULT / f".env.{name}"
    if not p.exists():
        return {}
    out = {}
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        return {}
    # Reject templates that still have <paste_key_here>
    for k, v in list(out.items()):
        if v.startswith("<") and v.endswith(">"):
            return {}
    return out


# ─── provider callers ─────────────────────────────────────────────
# Each returns (reply_text, meta) OR raises to signal fallthrough.

def _call_groq(prompt: str, model: str | None = None, task: str = "chat") -> tuple[str, dict]:
    env = _load_env("groq")
    if not env.get("GROQ_API_KEY"):
        raise RuntimeError("no groq key")
    model = model or env.get("GROQ_DEFAULT_MODEL", "llama-3.3-70b-versatile")
    endpoint = env.get("GROQ_ENDPOINT", "https://api.groq.com/openai/v1/chat/completions")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(endpoint, data=body, headers={
        "Authorization": f"Bearer {env['GROQ_API_KEY']}",
        "Content-Type": "application/json",
        # Groq's Cloudflare returns 1010 without a real UA
        "User-Agent": "qsb-tower/1.0 (skyscraper-council)",
    })
    t0 = time.time()
    r = urllib.request.urlopen(req, timeout=25)
    d = json.loads(r.read())
    reply = d["choices"][0]["message"]["content"]
    return reply, {"provider": "groq", "model": model, "latency_s": time.time()-t0, "cost_usd": 0.0}


def _call_gemini(prompt: str, model: str | None = None, task: str = "chat") -> tuple[str, dict]:
    env = _load_env("gemini")
    key = env.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no gemini key")
    project = env.get("GEMINI_PROJECT_ID")
    location = env.get("GEMINI_LOCATION", "us-central1")
    use_vertex = env.get("GEMINI_USE_VERTEX","false").lower() == "true"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
    }).encode()
    # Prefer AI Studio endpoint (works with API keys). Only use Vertex if
    # explicitly opted-in (Vertex needs OAuth 2 tokens, not API keys).
    if use_vertex and project:
        base = env.get("GEMINI_VERTEX_ENDPOINT", "https://us-central1-aiplatform.googleapis.com/v1")
        model = model or env.get("GEMINI_DEFAULT_MODEL", "gemini-2.0-flash")
        url = f"{base}/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        variant = "vertex"
    else:
        base = env.get("GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/models")
        model = model or env.get("GEMINI_DEFAULT_MODEL", "gemini-2.0-flash")
        url = f"{base}/{model}:generateContent?key={key}"
        headers = {"Content-Type": "application/json"}
        variant = "ai_studio"
    req = urllib.request.Request(url, data=body, headers=headers)
    t0 = time.time()
    r = urllib.request.urlopen(req, timeout=25)
    d = json.loads(r.read())
    reply = d["candidates"][0]["content"]["parts"][0]["text"]
    return reply, {"provider": f"gemini_{variant}", "model": model, "latency_s": time.time()-t0, "cost_usd": 0.0}


def _call_deepseek(prompt: str, model: str | None = None, task: str = "chat") -> tuple[str, dict]:
    env = _load_env("deepseek")
    key = env.get("DEEPSEEK_API_KEY") or env.get("DEEPSEEK_KEY")
    if not key: raise RuntimeError("no deepseek key")
    # code tasks → coder, reasoning → chat
    default_model = "deepseek-coder" if task == "code" else "deepseek-chat"
    model = model or default_model
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.time()
    r = urllib.request.urlopen(req, timeout=45)
    d = json.loads(r.read())
    reply = d["choices"][0]["message"]["content"]
    usage = d.get("usage", {})
    # rough cost estimate: DeepSeek is ~$0.14/M input + $0.28/M output (as of 2025)
    cost = (usage.get("prompt_tokens",0) * 0.14 + usage.get("completion_tokens",0) * 0.28) / 1e6
    return reply, {"provider": "deepseek", "model": model, "latency_s": time.time()-t0, "cost_usd": cost}


def _call_openai(prompt: str, model: str | None = None, task: str = "chat") -> tuple[str, dict]:
    env = _load_env("openai")
    key = env.get("OPENAI_API_KEY") or env.get("OPENAI_KEY")
    if not key: raise RuntimeError("no openai key")
    default_model = "gpt-4o-mini" if task in ("chat","code") else "gpt-4o"
    model = model or default_model
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.time()
    r = urllib.request.urlopen(req, timeout=45)
    d = json.loads(r.read())
    reply = d["choices"][0]["message"]["content"]
    usage = d.get("usage", {})
    # rough: gpt-4o-mini ~$0.15/M in + $0.60/M out
    cost = (usage.get("prompt_tokens",0) * 0.15 + usage.get("completion_tokens",0) * 0.60) / 1e6
    return reply, {"provider": "openai", "model": model, "latency_s": time.time()-t0, "cost_usd": cost}


def _call_cohere(prompt: str, model: str | None = None, task: str = "chat") -> tuple[str, dict]:
    env = _load_env("cohere")
    key = env.get("QSB_COHERE_API_KEY") or env.get("COHERE_API_KEY")
    if not key: raise RuntimeError("no cohere key")
    default_model = env.get("QSB_COHERE_DEFAULT_MODEL", "command-a-03-2025")
    model = model or default_model
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
    }).encode()
    req = urllib.request.Request(
        env.get("QSB_COHERE_ENDPOINT", "https://api.cohere.com/v2/chat"),
        data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.time()
    r = urllib.request.urlopen(req, timeout=30)
    d = json.loads(r.read())
    content_arr = d.get("message", {}).get("content", [])
    reply = "".join(c.get("text","") for c in content_arr if c.get("type") == "text")
    usage = d.get("usage", {}).get("billed_units", {})
    # Cohere command-a: ~$2.50/M in + $10/M out (~half of gpt-4o)
    cost = (usage.get("input_tokens",0) * 2.50 + usage.get("output_tokens",0) * 10.00) / 1e6
    return reply, {"provider": "cohere", "model": model, "latency_s": time.time()-t0, "cost_usd": cost}


def _call_kimi(prompt: str, model: str | None = None, task: str = "chat") -> tuple[str, dict]:
    env = _load_env("kimi")
    key = env.get("QSB_KIMI_API_KEY")
    if not key: raise RuntimeError("no kimi key")
    default_model = env.get("QSB_KIMI_DEFAULT_MODEL", "moonshot-v1-8k")
    model = model or default_model
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 500,
    }).encode()
    req = urllib.request.Request(
        env.get("QSB_KIMI_ENDPOINT", "https://api.moonshot.ai/v1/chat/completions"),
        data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.time()
    r = urllib.request.urlopen(req, timeout=30)
    d = json.loads(r.read())
    reply = d["choices"][0]["message"]["content"]
    usage = d.get("usage", {})
    cost = (usage.get("prompt_tokens",0) * 0.20 + usage.get("completion_tokens",0) * 2.00) / 1e6
    return reply, {"provider": "kimi", "model": model, "latency_s": time.time()-t0, "cost_usd": cost}


def _call_ollama_lan(prompt: str, model: str | None = None, task: str = "chat") -> tuple[str, dict]:
    model = model or "qwen2.5:14b"
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        "http://192.168.1.71:11434/api/generate",
        data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    r = urllib.request.urlopen(req, timeout=90)
    d = json.loads(r.read())
    return d.get("response","").strip(), {"provider": "ollama_lan", "model": model, "latency_s": time.time()-t0, "cost_usd": 0.0}


def _call_ollama_local(prompt: str, model: str | None = None, task: str = "chat") -> tuple[str, dict]:
    model = model or "llama3.2"
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    r = urllib.request.urlopen(req, timeout=90)
    d = json.loads(r.read())
    return d.get("response","").strip(), {"provider": "ollama_local", "model": model, "latency_s": time.time()-t0, "cost_usd": 0.0}


# ─── router ───────────────────────────────────────────────────────
WORKER_ORDER = [_call_groq, _call_gemini, _call_cohere, _call_deepseek, _call_openai, _call_kimi, _call_ollama_lan, _call_ollama_local]
# Claude API isn't implemented here — Anthropic SDK is heavier; for now
# the 'premium' tier just falls through to worker order but favors OpenAI first.
PREMIUM_ORDER = [_call_openai, _call_deepseek, _call_gemini, _call_groq, _call_ollama_lan]


def route(prompt: str, task: str = "chat", tier: str = "worker",
          caller: str = "unknown", model: str | None = None) -> tuple[str, dict]:
    """Route the prompt through provider fallback chain. Returns (reply, meta)."""
    order = PREMIUM_ORDER if tier == "premium" else WORKER_ORDER
    tried = []
    last_err = None
    for fn in order:
        pname = fn.__name__.replace("_call_", "")
        try:
            reply, meta = fn(prompt, model=model, task=task)
            meta["tried"] = tried + [pname]
            meta["tier"] = tier
            meta["task"] = task
            _log_call(caller, task, tier, meta, prompt, reply)
            return reply, meta
        except Exception as e:
            tried.append(f"{pname}:{str(e)[:40]}")
            last_err = e
            continue
    err_meta = {"tried": tried, "error": str(last_err)[:200]}
    _log_call(caller, task, tier, err_meta, prompt, "")
    raise RuntimeError(f"all providers failed. tried={tried}")


def _log_call(caller: str, task: str, tier: str, meta: dict, prompt: str, reply: str):
    row = {
        "ts": _utc(), "caller": caller, "task": task, "tier": tier,
        "provider_used": meta.get("provider","?"),
        "model": meta.get("model","?"),
        "latency_s": round(meta.get("latency_s",0), 2),
        "cost_usd_est": round(meta.get("cost_usd",0), 6),
        "tried": meta.get("tried",[]),
        "prompt_head": prompt[:120],
        "reply_head": (reply or "")[:200],
    }
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a") as f:
            f.write(json.dumps(row)+"\n")
    except Exception: pass


def status() -> dict:
    """What's available right now?"""
    out = {}
    for name in ("groq","gemini","deepseek","openai"):
        env = _load_env(name)
        out[name] = "READY ✓" if any(k for k,v in env.items() if "KEY" in k and v) else "no key (paste to vault)"
    # Ollama probes
    for probe_name, url in (("ollama_lan","http://192.168.1.71:11434/api/tags"),
                            ("ollama_local","http://127.0.0.1:11434/api/tags")):
        try:
            urllib.request.urlopen(url, timeout=3).read()
            out[probe_name] = "READY ✓"
        except Exception:
            out[probe_name] = "unreachable"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", help="the prompt")
    ap.add_argument("--task", default="chat", choices=["chat","code","reason","long"])
    ap.add_argument("--tier", default="worker", choices=["worker","premium"])
    ap.add_argument("--caller", default="cli")
    ap.add_argument("--model", default=None)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    if a.status:
        s = status()
        print("=== brain-router provider status ===")
        for k,v in s.items(): print(f"  {k:15}  {v}")
        return

    if not a.prompt:
        ap.error("--prompt required (or --status)")
    try:
        reply, meta = route(a.prompt, task=a.task, tier=a.tier,
                            caller=a.caller, model=a.model)
        print(f"\n[via {meta.get('provider')} model={meta.get('model')} lat={meta.get('latency_s'):.1f}s cost=${meta.get('cost_usd'):.5f}]\n")
        print(reply)
    except RuntimeError as e:
        print(f"[router failed] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
