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


def _call_claude(prompt: str, model: str | None = None, task: str = "chat") -> tuple[str, dict]:
    env = _load_env("anthropic")
    key = env.get("QSB_ANTHROPIC_API_KEY")
    if not key: raise RuntimeError("no anthropic key")
    if task in ("critical","reason","code"):
        default_model = env.get("QSB_ANTHROPIC_PREMIUM_MODEL", "claude-opus-4-7")
    else:
        default_model = env.get("QSB_ANTHROPIC_DEFAULT_MODEL", "claude-haiku-4-5-20251001")
    model = model or default_model
    body = json.dumps({
        "model": model,
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        env.get("QSB_ANTHROPIC_ENDPOINT", "https://api.anthropic.com/v1/messages"),
        data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
    t0 = time.time()
    r = urllib.request.urlopen(req, timeout=45)
    d = json.loads(r.read())
    content = d.get("content", [])
    reply = "".join(c.get("text","") for c in content if c.get("type") == "text")
    usage = d.get("usage", {})
    # haiku 4.5 ~$1/M in + $5/M out; opus ~$15/M in + $75/M out
    is_opus = "opus" in model
    cost = (usage.get("input_tokens",0) * (15 if is_opus else 1) + usage.get("output_tokens",0) * (75 if is_opus else 5)) / 1e6
    return reply, {"provider": "claude", "model": model, "latency_s": time.time()-t0, "cost_usd": cost}


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
        "http://192.168.1.72:11434/api/generate",
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


def _call_local_14b(prompt: str, model: str | None = None, task: str = "chat") -> tuple[str, dict]:
    """Ross 2026-07-07: explicit local-14B route (qwen2.5:14b on the 16GB GPU).
    Wren's primary local reasoning route. Provider label = local_14b (never claude)."""
    model = model or "qwen2.5:14b"
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    r = urllib.request.urlopen(req, timeout=120)
    d = json.loads(r.read())
    return d.get("response","").strip(), {"provider": "local_14b", "model": model, "latency_s": time.time()-t0, "cost_usd": 0.0}


# ─── router ───────────────────────────────────────────────────────
WORKER_ORDER = [_call_groq, _call_gemini, _call_cohere, _call_deepseek, _call_openai, _call_kimi, _call_claude, _call_ollama_lan, _call_ollama_local]
PREMIUM_ORDER = [_call_claude, _call_openai, _call_deepseek, _call_gemini, _call_groq, _call_ollama_lan]

# Ross 2026-07-05 #178: per-CEO "first mind" architecture.
# SUPERSEDED for Acer/TP/Wren by Ross 2026-07-07 credit-protection order (below).
# Kept only for HQ controller judgement via HQ_CONTROLLER_ORDER.
CLAUDE_FIRST_ORDER = [_call_claude, _call_cohere, _call_deepseek, _call_groq, _call_gemini, _call_openai, _call_kimi, _call_ollama_lan, _call_ollama_local]

# ─── Ross 2026-07-07 credit-protection routing (unhook Acer + TP from Claude) ───
# NOTE: Ross's allow-lists include "mistral" but this router has NO _call_mistral
# (no vault key). Mistral is therefore ABSENT from the runtime chains and reported
# unavailable — it will be added here the moment a mistral caller + key exist.
ACER_NON_CLAUDE_ORDER = [_call_deepseek, _call_openai, _call_cohere, _call_kimi, _call_gemini, _call_groq, _call_ollama_lan, _call_ollama_local]
TP_NON_CLAUDE_ORDER   = [_call_openai, _call_deepseek, _call_cohere, _call_kimi, _call_gemini, _call_groq, _call_ollama_lan, _call_ollama_local]
LOCAL_FIRST_ORDER     = [_call_local_14b, _call_ollama_lan, _call_ollama_local, _call_deepseek, _call_openai, _call_groq]
HQ_LOCAL_NON_CLAUDE_ORDER = [_call_local_14b, _call_ollama_lan, _call_ollama_local, _call_deepseek, _call_groq, _call_openai]
HQ_CONTROLLER_ORDER   = [_call_claude, _call_openai, _call_deepseek, _call_gemini, _call_cohere, _call_kimi, _call_groq, _call_ollama_lan, _call_ollama_local]
WREN_ORDER            = LOCAL_FIRST_ORDER   # Ross 2026-07-07: Wren local-first, Claude blocked

# Callers that must NEVER be Claude-first / Claude-at-all for worker tasks unless Ross override.
CLAUDE_RESTRICTED_ALIASES = ('acer', 'asa', 'cass', 'thinkpad', 'tp_pip', 'tp', 'pip', 'wren', 'hq_claude', 'claude_hq', 'hq')


def _is_claude_restricted(caller: str) -> bool:
    c = (caller or "").lower().replace("-", "_")
    return any(x in c for x in CLAUDE_RESTRICTED_ALIASES)


def _caller_order(caller: str, tier: str, task: str = "chat"):
    """Ross 2026-07-07: route by WHO is calling. Acer/TP/Wren are Claude-free."""
    c = (caller or "").lower().replace("-", "_")
    if "wren" in c:
        return LOCAL_FIRST_ORDER
    if any(x in c for x in ("acer", "asa", "cass")):
        return ACER_NON_CLAUDE_ORDER
    if any(x in c for x in ("thinkpad", "tp_pip", "tp", "pip")):
        return TP_NON_CLAUDE_ORDER
    if any(x in c for x in ("hq_claude", "claude_hq", "hq")):
        # Ross 2026-07-07: HQ-Claude Local Mode.
        # Keep HQ-Claude identity/persona, but route non-Claude unless ross_override=True.
        return HQ_LOCAL_NON_CLAUDE_ORDER
    return PREMIUM_ORDER if tier == "premium" else WORKER_ORDER




def _is_hq_claude_caller(caller: str) -> bool:
    c = (caller or "").lower().replace("-", "_")
    return any(x in c for x in ("hq_claude", "claude_hq", "hq"))

def _load_hq_claude_persona() -> dict:
    try:
        p = REG / "hq_claude_local_persona.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "display_name": "HQ-Claude",
        "role": "Boardroom architect and council controller",
        "truth_label": "HQ-Claude local role powered by Brain Router",
        "normal_provider_policy": "Use Brain Router; avoid Claude API unless Ross explicitly overrides.",
        "default_model": "qwen2.5:14b",
        "core_rules": [
            "Do not claim Claude API unless provider_used is claude.",
            "Do not invent tool proof.",
            "Speak as HQ-Claude local shell, not raw model."
        ],
        "local_memory_anchors": []
    }

def _wrap_hq_claude_prompt(caller: str, prompt: str) -> str:
    if not _is_hq_claude_caller(caller):
        return prompt
    if "QSB-HQ-CLAUDE-LOCAL-PERSONA" in str(prompt):
        return prompt

    persona = _load_hq_claude_persona()
    rules = "\n".join(f"- {x}" for x in persona.get("core_rules", []))
    anchors = "\n".join(f"- {x}" for x in persona.get("local_memory_anchors", []))

    return f"""QSB-HQ-CLAUDE-LOCAL-PERSONA

You are {persona.get('display_name','HQ-Claude')}, the local Boardroom HQ role.

Role:
{persona.get('role','Boardroom architect and council controller')}

Truth label:
{persona.get('truth_label','HQ-Claude local role powered by Brain Router')}

Provider policy:
{persona.get('normal_provider_policy','Use Brain Router; avoid Claude API unless Ross explicitly overrides.')}

Default local model:
{persona.get('default_model','qwen2.5:14b')}

Core rules:
{rules}

Local memory anchors:
{anchors}

Important:
You are the HQ-Claude local shell/persona. The engine underneath may be qwen, ollama_lan, deepseek, groq, or another provider. Do not claim to be Claude API unless the router metadata says provider_used=claude.

Ross request:
{prompt}
"""

def route(prompt: str, task: str = "chat", tier: str = "worker",
          caller: str = "unknown", model: str | None = None,
          ross_override: bool = False) -> tuple[str, dict]:
    """Route the prompt through provider fallback chain. Returns (reply, meta)."""
    prompt = _wrap_hq_claude_prompt(caller, prompt)
    restricted = _is_claude_restricted(caller) and not ross_override
    claude_blocked = False
    # Ross 2026-07-07 hard guard: a Claude-restricted caller explicitly asking for
    # a claude/anthropic model gets blocked + logged + rerouted to non-Claude.
    if restricted and model and any(k in str(model).lower() for k in ("claude", "anthropic")):
        _log_claude_block(caller, task, "claude", "claude-restricted caller requested a claude model", "(auto non-claude)")
        model = None
        claude_blocked = True

    order = _caller_order(caller, tier, task)
    # Structural guarantee: never let a restricted caller reach _call_claude.
    if restricted:
        order = [fn for fn in order if fn is not _call_claude]

    tried = []
    last_err = None
    for fn in order:
        pname = fn.__name__.replace("_call_", "")
        try:
            reply, meta = fn(prompt, model=model, task=task)
            meta["tried"] = tried + [pname]
            meta["tier"] = tier
            meta["task"] = task
            meta["claude_avoided"] = bool(restricted)
            meta["claude_blocked"] = bool(claude_blocked)
            _log_call(caller, task, tier, meta, prompt, reply)
            return reply, meta
        except Exception as e:
            tried.append(f"{pname}:{str(e)[:40]}")
            last_err = e
            continue
    err_meta = {"tried": tried, "error": str(last_err)[:200],
                "claude_avoided": bool(restricted), "claude_blocked": bool(claude_blocked)}
    _log_call(caller, task, tier, err_meta, prompt, "")
    raise RuntimeError(f"all providers failed. tried={tried}")


BLOCK_LOG = REG / "qsb_claude_block_log.jsonl"


def _log_claude_block(caller: str, task: str, attempted: str, reason: str, fallback: str):
    row = {
        "ts": _utc(), "kind": "claude_block",
        "requester": caller, "machine": os.environ.get("QSB_MACHINE", "hq"),
        "task": task, "attempted_provider": attempted, "reason": reason,
        "fallback_provider": fallback, "claude_avoided": True, "claude_blocked": True,
    }
    try:
        BLOCK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with BLOCK_LOG.open("a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


def _log_call(caller: str, task: str, tier: str, meta: dict, prompt: str, reply: str):
    row = {
        "ts": _utc(), "caller": caller, "task": task, "tier": tier,
        "provider_used": meta.get("provider","?"),
        "model": meta.get("model","?"),
        "model_used": meta.get("model","?"),
        "claude_avoided": bool(meta.get("claude_avoided", False)),
        "claude_blocked": bool(meta.get("claude_blocked", False)),
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


def claude_health() -> dict:
    """Ross 2026-07-07 addendum: real health probe for Claude API.

    Fires a tiny request against Anthropic to detect: rate-limit, token-blocked,
    expired, offline, or slow. Returns safe metadata only — no key values.
    """
    import time as _t
    t0 = _t.time()
    env = _load_env("anthropic")
    key = env.get("QSB_ANTHROPIC_API_KEY") or env.get("ANTHROPIC_API_KEY")
    if not key:
        return {"healthy": False, "reason": "no_key_in_vault", "latency_ms": 0}
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "hi"}],
            }).encode(),
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=8)
        dt = int((_t.time() - t0) * 1000)
        _ = resp.read()
        healthy = resp.status == 200
        slow = dt > 5000
        return {"healthy": healthy and not slow,
                "reason": "slow" if slow else "ok",
                "http": resp.status, "latency_ms": dt}
    except urllib.error.HTTPError as e:
        dt = int((_t.time() - t0) * 1000)
        reason = {401: "auth_failed", 403: "forbidden",
                  429: "rate_limited", 500: "server_err",
                  502: "bad_gateway", 503: "unavailable"}.get(e.code, f"http_{e.code}")
        return {"healthy": False, "reason": reason,
                "http": e.code, "latency_ms": dt}
    except Exception as e:
        dt = int((_t.time() - t0) * 1000)
        return {"healthy": False, "reason": f"exception:{type(e).__name__}",
                "latency_ms": dt}


def status() -> dict:
    """Provider readiness. Safe metadata only — never prints raw keys.

    Ross 2026-07-07 upgrade: covers all 9 providers (added cohere, kimi, anthropic).
    Each entry is a dict with capability + configured + intended_use.
    """
    PROVIDER_META = {
        "groq":      {"use": "fast free-tier general chat"},
        "gemini":    {"use": "free long-context + broad research"},
        "deepseek":  {"use": "cheap coding, debugging, refactor, first-pass code"},
        "openai":    {"use": "strong general reasoning, structured outputs, planning"},
        "anthropic": {"use": "Claude API — CEO judgement, rule interp, final review"},
        "cohere":    {"use": "embeddings, reranking, classification, semantic search"},
        "kimi":      {"use": "long-context reading, large document analysis"},
    }
    out = {}
    for name, meta in PROVIDER_META.items():
        env = _load_env(name)
        has_key = any(k for k, v in env.items() if "KEY" in k and v)
        out[name] = {
            "configured": has_key,
            "status":     "READY ✓" if has_key else "no key (paste to vault)",
            "use":        meta["use"],
        }
    for probe_name, url in (("ollama_lan",   "http://192.168.1.72:11434/api/tags"),
                            ("ollama_local", "http://127.0.0.1:11434/api/tags")):
        try:
            urllib.request.urlopen(url, timeout=3).read()
            out[probe_name] = {"configured": True, "status": "READY ✓",
                               "use": "free local models — offline last resort"}
        except Exception:
            out[probe_name] = {"configured": False, "status": "unreachable",
                               "use": "free local models — offline last resort"}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", help="the prompt")
    ap.add_argument("--task", default="chat", choices=["chat","code","reason","long"])
    ap.add_argument("--tier", default="worker", choices=["worker","premium"])
    ap.add_argument("--caller", default="cli")
    ap.add_argument("--model", default=None)
    ap.add_argument("--ross-override", dest="ross_override", action="store_true",
                    help="Ross override: allow Claude even for restricted callers")
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
                            caller=a.caller, model=a.model, ross_override=a.ross_override)
        print(f"\n[via provider_used={meta.get('provider')} model_used={meta.get('model')} "
              f"claude_avoided={meta.get('claude_avoided', False)} claude_blocked={meta.get('claude_blocked', False)} "
              f"lat={meta.get('latency_s'):.1f}s cost=${meta.get('cost_usd'):.5f}]\n")
        print(reply)
    except RuntimeError as e:
        print(f"[router failed] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
