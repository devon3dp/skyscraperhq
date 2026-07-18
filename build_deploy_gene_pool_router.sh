#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
PORT="8860"
RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_gene_pool_router_build"
REPORT="$RUN_DIR/reports/gene_pool_router_build_report.txt"

APP="$PROJECT/tools/skyscraper_gene_pool_router.py"
STARTER="$PROJECT/run_gene_pool_router.sh"
LOG_DIR="$PROJECT/logs"
LOG="$LOG_DIR/gene_pool_router_8860.log"
PIDFILE="$PROJECT/runtime/gene_pool_router_8860.pid"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/logs" "$SEND" "$LOG_DIR" "$PROJECT/runtime" "$PROJECT/data/registries"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — BUILD / INSTALL / DEPLOY / OPEN / SMOKE TEST"
echo "Brain Router Gene Pool Dashboard"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "Port: $PORT"
echo "Run folder: $RUN_DIR"
echo "Report: $REPORT"
echo "============================================================"
echo
echo "RULES:"
echo " - Brain Router lives inside SkyscraperHQ."
echo " - This does not build free-cloud worker nodes."
echo " - CEOs use API Gene Pool only."
echo " - No local model fallback for CEOs."
echo " - Ren/GPU side is not touched."
echo " - Claude HQ is the only correct visible name."
echo " - API keys are masked. Full secrets are never printed."
echo

cd "$PROJECT" || exit 1

if [ -f "$APP" ]; then
  cp -a "$APP" "$RUN_DIR/backups/skyscraper_gene_pool_router.py.bak_$STAMP"
fi

if [ -f "$STARTER" ]; then
  cp -a "$STARTER" "$RUN_DIR/backups/run_gene_pool_router.sh.bak_$STAMP"
fi

echo "===== 1. WRITE GENE POOL ROUTER DASHBOARD APP ====="

cat > "$APP" <<'PY'
#!/usr/bin/env python3
import os
import re
import ssl
import json
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PROJECT = Path("/vaults/nvme0/qsb_tower_v1")
PORT = int(os.environ.get("GENE_POOL_ROUTER_PORT", "8860"))
HOST = os.environ.get("GENE_POOL_ROUTER_HOST", "0.0.0.0")

DATA_DIR = PROJECT / "data" / "registries"
LOG_JSONL = DATA_DIR / "skyscraper_gene_pool_router_calls.jsonl"
STATE_JSON = DATA_DIR / "skyscraper_gene_pool_router_state.json"

SEARCH_ROOTS = [
    Path("/home/ross/.skyscraper_secrets"),
    Path("/home/ross/.claude"),
    PROJECT / "vaults",
    PROJECT / "floors",
    PROJECT / "config",
    PROJECT / "data",
    PROJECT / "tools",
]

SKIP_PARTS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".cache", "cache", "models", "ollama", "huggingface",
    "external_oss"
}

PROVIDERS = {
    "claude": {
        "label": "Claude",
        "env_names": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
        "regexes": [r"sk-ant-[A-Za-z0-9_\-]{20,}"],
        "role": "deep reasoning / Claude HQ preferred when funded",
        "default_model": "claude-haiku-4-5-20251001",
        "cost_tier": "premium",
    },
    "openai": {
        "label": "OpenAI",
        "env_names": ["OPENAI_API_KEY"],
        "regexes": [r"sk-proj-[A-Za-z0-9_\-]{20,}", r"sk-[A-Za-z0-9_\-]{32,}"],
        "role": "structured reasoning / planning / code review",
        "default_model": "gpt-4.1-mini",
        "cost_tier": "medium",
    },
    "deepseek": {
        "label": "DeepSeek",
        "env_names": ["DEEPSEEK_API_KEY"],
        "regexes": [r"sk-[A-Za-z0-9_\-]{32,}"],
        "role": "coding / cheap reasoning",
        "default_model": "deepseek-chat",
        "cost_tier": "low",
    },
    "gemini": {
        "label": "Gemini",
        "env_names": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"],
        "regexes": [r"AIza[A-Za-z0-9_\-]{20,}"],
        "role": "long context / document reasoning",
        "default_model": "gemini-1.5-flash",
        "cost_tier": "low-medium",
    },
    "cohere": {
        "label": "Cohere",
        "env_names": ["COHERE_API_KEY"],
        "regexes": [r"[A-Za-z0-9_\-]{40,}"],
        "role": "retrieval / summaries / classification",
        "default_model": "command-r7b-12-2024",
        "cost_tier": "low-medium",
    },
    "kimi": {
        "label": "Kimi",
        "env_names": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
        "regexes": [r"sk-[A-Za-z0-9_\-]{32,}"],
        "role": "long document reasoning / alternate executive brain",
        "default_model": "moonshot-v1-8k",
        "cost_tier": "low-medium",
    },
    "grok": {
        "label": "Grok / xAI",
        "env_names": ["GROK_API_KEY", "XAI_API_KEY"],
        "regexes": [r"xai-[A-Za-z0-9_\-]{20,}", r"sk-[A-Za-z0-9_\-]{32,}"],
        "role": "alternate reasoning perspective",
        "default_model": "grok-2-latest",
        "cost_tier": "medium",
    },
    "groq": {
        "label": "Groq",
        "env_names": ["GROQ_API_KEY"],
        "regexes": [r"gsk_[A-Za-z0-9_\-]{20,}"],
        "role": "fast cheap hosted inference",
        "default_model": "llama-3.1-8b-instant",
        "cost_tier": "low",
    },
}

CEOS = [
    {"name": "Claude HQ", "policy": "API Gene Pool only; Claude preferred when funded; never local GPU fallback."},
    {"name": "CEO 2", "policy": "API Gene Pool only; provider selected by Brain Router."},
    {"name": "CEO 3", "policy": "API Gene Pool only; provider selected by Brain Router."},
]

ROUTING_POLICY = {
    "architecture": ["claude", "openai", "kimi", "gemini", "deepseek", "grok", "groq", "cohere"],
    "coding": ["deepseek", "openai", "claude", "kimi", "groq", "gemini", "grok", "cohere"],
    "summary": ["cohere", "gemini", "kimi", "openai", "deepseek", "groq", "claude", "grok"],
    "cheap": ["groq", "deepseek", "gemini", "cohere", "kimi", "openai", "claude", "grok"],
    "default": ["openai", "deepseek", "kimi", "gemini", "claude", "groq", "grok", "cohere"],
}

LAST_STATUS = {}
LAST_SCAN = {"ts": None, "providers": {}}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def sha16(text):
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]

def mask_key(k):
    if not k:
        return ""
    if len(k) <= 18:
        return k[:5] + "..." + k[-4:]
    return k[:12] + "..." + k[-8:]

def safe_text(s, limit=900):
    s = str(s or "")
    for rx in [r"sk-ant-[A-Za-z0-9_\-]{20,}", r"sk-proj-[A-Za-z0-9_\-]{20,}", r"gsk_[A-Za-z0-9_\-]{20,}", r"xai-[A-Za-z0-9_\-]{20,}", r"AIza[A-Za-z0-9_\-]{20,}", r"sk-[A-Za-z0-9_\-]{32,}"]:
        s = re.sub(rx, lambda m: mask_key(m.group(0)), s)
    s = s.replace("\n", " ")
    return s[:limit]

def write_log(obj):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    obj["ts"] = now_iso()
    with LOG_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def read_json_body(handler):
    n = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(n) if n else b"{}"
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return {}

def response_json(handler, obj, status=200):
    raw = json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)

def response_html(handler, html):
    raw = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)

def extract_env_line_keys(text, source_path):
    hits = []
    for provider, cfg in PROVIDERS.items():
        for env_name in cfg["env_names"]:
            pat = re.compile(rf"(^|\n)\s*(?:export\s+)?{re.escape(env_name)}\s*=\s*['\"]?([^'\"\n\r #]+)", re.I)
            for m in pat.finditer(text):
                key = m.group(2).strip()
                if len(key) >= 16:
                    hits.append((provider, key, f"{source_path}:{env_name}"))
    return hits

def scan_keys():
    found = {p: {} for p in PROVIDERS.keys()}

    for provider, cfg in PROVIDERS.items():
        for env_name in cfg["env_names"]:
            val = os.environ.get(env_name, "").strip()
            if val:
                found[provider].setdefault(val, set()).add(f"process_env:{env_name}")

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue

        for p in root.rglob("*"):
            try:
                if not p.is_file():
                    continue
                if any(part in SKIP_PARTS for part in p.parts):
                    continue
                if p.stat().st_size > 3_000_000:
                    continue

                low = str(p).lower()
                if not any(x in low for x in ["env", "key", "secret", "vault", "token", "credential", "claude", "openai", "deepseek", "gemini", "cohere", "kimi", "moonshot", "grok", "groq", "xai"]):
                    continue

                text = p.read_text(errors="ignore")
            except Exception:
                continue

            for provider, key, src in extract_env_line_keys(text, str(p)):
                found[provider].setdefault(key, set()).add(src)

            # Provider-specific fallback regex only if provider name appears near file path/content.
            low_text_sample = text[:5000].lower()
            for provider, cfg in PROVIDERS.items():
                if provider not in low and provider not in low_text_sample and cfg["label"].lower().split()[0] not in low_text_sample:
                    continue
                for rx in cfg["regexes"]:
                    for m in re.finditer(rx, text):
                        key = m.group(0).strip()
                        if len(key) >= 16:
                            found[provider].setdefault(key, set()).add(str(p))

    result = {}
    for provider, keymap in found.items():
        keys = []
        for key, sources in keymap.items():
            keys.append({
                "masked": mask_key(key),
                "fingerprint": sha16(key),
                "sources": sorted(sources)[:12],
                "_secret": key,
            })
        result[provider] = {
            "provider": provider,
            "label": PROVIDERS[provider]["label"],
            "role": PROVIDERS[provider]["role"],
            "cost_tier": PROVIDERS[provider]["cost_tier"],
            "default_model": PROVIDERS[provider]["default_model"],
            "key_count": len(keys),
            "keys": keys,
            "last_status": LAST_STATUS.get(provider, {"status": "not_tested"}),
        }

    public = json.loads(json.dumps(result))
    for pdata in public.values():
        for k in pdata["keys"]:
            k.pop("_secret", None)

    LAST_SCAN["ts"] = now_iso()
    LAST_SCAN["providers"] = result
    save_state_public(public)
    return result

def save_state_public(public_providers):
    state = {
        "ts": now_iso(),
        "doctrine": {
            "brain_router": "inside SkyscraperHQ",
            "ceos": "API Gene Pool only",
            "ren": "owns local GPU; no CEO local fallback",
            "visible_name": "Claude HQ",
        },
        "providers": public_providers,
        "last_status": LAST_STATUS,
    }
    STATE_JSON.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

def http_request(url, method="POST", headers=None, payload=None, timeout=45):
    headers = headers or {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return e.code, raw
    except Exception as e:
        return 0, repr(e)

def classify_http(code, raw):
    s = (raw or "").lower()
    if 200 <= code < 300:
        return "ok"
    if code in (401, 403) or "invalid api key" in s or "invalid x-api-key" in s or "authentication" in s:
        return "auth_failed"
    if "credit" in s or "billing" in s or "quota" in s or "balance" in s or code == 402:
        return "billing_or_quota"
    if code == 429 or "rate limit" in s or "rate_limit" in s:
        return "rate_limited"
    if code == 0:
        return "network_or_timeout"
    return f"http_{code}"

def test_provider(provider, key, prompt="Reply exactly: OK"):
    cfg = PROVIDERS[provider]
    model = cfg["default_model"]
    t0 = time.time()
    status = "not_tested"
    code = 0
    raw = ""
    parsed_preview = ""

    try:
        if provider == "claude":
            code, raw = http_request(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
                payload={
                    "model": model,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=45
            )

        elif provider == "openai":
            code, raw = http_request(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {key}"},
                payload={
                    "model": model,
                    "input": prompt,
                    "max_output_tokens": 8,
                },
                timeout=45
            )

        elif provider == "deepseek":
            code, raw = http_request(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                payload={
                    "model": model,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=45
            )

        elif provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            code, raw = http_request(
                url,
                payload={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 8},
                },
                timeout=45
            )

        elif provider == "cohere":
            code, raw = http_request(
                "https://api.cohere.com/v2/chat",
                headers={"Authorization": f"Bearer {key}"},
                payload={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 8,
                },
                timeout=45
            )

        elif provider == "kimi":
            code, raw = http_request(
                "https://api.moonshot.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                payload={
                    "model": model,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=45
            )

        elif provider == "grok":
            code, raw = http_request(
                "https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                payload={
                    "model": model,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=45
            )

        elif provider == "groq":
            code, raw = http_request(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                payload={
                    "model": model,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=45
            )

    except Exception as e:
        raw = repr(e)
        code = 0

    latency = round(time.time() - t0, 3)
    status = classify_http(code, raw)

    result = {
        "provider": provider,
        "label": cfg["label"],
        "status": status,
        "http": code,
        "latency_s": latency,
        "model": model,
        "key_fingerprint": sha16(key),
        "key_masked": mask_key(key),
        "preview": safe_text(raw, 650),
        "tested_at": now_iso(),
    }

    LAST_STATUS[provider] = result
    write_log({"event": "provider_test", **result})
    return result

def test_all():
    scanned = scan_keys()
    results = []
    for provider, pdata in scanned.items():
        if not pdata["keys"]:
            res = {
                "provider": provider,
                "label": PROVIDERS[provider]["label"],
                "status": "missing_key",
                "http": None,
                "latency_s": None,
                "model": PROVIDERS[provider]["default_model"],
                "preview": "No key found in vault/env scan.",
                "tested_at": now_iso(),
            }
            LAST_STATUS[provider] = res
            results.append(res)
            write_log({"event": "provider_test", **res})
            continue

        provider_results = []
        for k in pdata["keys"][:3]:
            provider_results.append(test_provider(provider, k["_secret"]))

        ok = [r for r in provider_results if r["status"] == "ok"]
        chosen = ok[0] if ok else provider_results[0]
        chosen["tested_keys"] = len(provider_results)
        results.append(chosen)

    public_scan = json.loads(json.dumps(LAST_SCAN["providers"]))
    for pdata in public_scan.values():
        for k in pdata["keys"]:
            k.pop("_secret", None)
    save_state_public(public_scan)
    return results

def available_providers():
    scanned = scan_keys()
    available = []
    for provider, pdata in scanned.items():
        st = LAST_STATUS.get(provider, {})
        if st.get("status") == "ok" and pdata["keys"]:
            available.append(provider)
    return available

def classify_task(text, explicit=None):
    if explicit and explicit in ROUTING_POLICY:
        return explicit
    low = (text or "").lower()
    if any(x in low for x in ["code", "script", "python", "bash", "bug", "error", "traceback", "compile", "patch"]):
        return "coding"
    if any(x in low for x in ["architecture", "design", "kernel", "system", "brain router", "ceo", "strategy"]):
        return "architecture"
    if any(x in low for x in ["summarise", "summarize", "recap", "report"]):
        return "summary"
    if any(x in low for x in ["cheap", "fast", "small", "quick"]):
        return "cheap"
    return "default"

def select_provider(task_type, ceo_name="Claude HQ"):
    scanned = scan_keys()

    # If no statuses yet, choose by key existence only but mark as untested.
    preference = ROUTING_POLICY.get(task_type, ROUTING_POLICY["default"])

    for provider in preference:
        pdata = scanned.get(provider)
        if not pdata or not pdata["keys"]:
            continue
        st = LAST_STATUS.get(provider, {})
        if st.get("status") in ("ok", None, "not_tested") or not st:
            return {
                "provider": provider,
                "label": PROVIDERS[provider]["label"],
                "model": PROVIDERS[provider]["default_model"],
                "key": pdata["keys"][0]["_secret"],
                "key_masked": pdata["keys"][0]["masked"],
                "key_fingerprint": pdata["keys"][0]["fingerprint"],
                "reason": f"{ceo_name} task={task_type}; selected first suitable API Gene Pool provider by policy.",
                "tested_status": st.get("status", "not_tested"),
            }

    return None

def route_prompt(payload):
    ceo = payload.get("ceo") or payload.get("speaker") or payload.get("caller") or "Claude HQ"
    prompt = payload.get("prompt") or payload.get("message") or payload.get("text") or ""
    task_type = classify_task(prompt, payload.get("task_type") or payload.get("task"))
    dry_run = bool(payload.get("dry_run", False))

    decision = select_provider(task_type, ceo)

    base = {
        "ceo": ceo,
        "task_type": task_type,
        "doctrine": "CEO request uses API Gene Pool only. No local GPU fallback.",
        "dry_run": dry_run,
    }

    if not decision:
        out = {
            **base,
            "ok": False,
            "error": "No API Gene Pool provider with a detected key is available.",
            "selected": None,
        }
        write_log({"event": "route", **out})
        return out

    selected_public = {k: v for k, v in decision.items() if k != "key"}

    if dry_run:
        out = {
            **base,
            "ok": True,
            "selected": selected_public,
            "answer": "DRY_RUN_OK: Brain Router selected an API Gene Pool provider without calling the model.",
        }
        write_log({"event": "route", **out})
        return out

    provider = decision["provider"]
    key = decision["key"]

    identity_prefix = (
        f"You are answering as {ceo}, a SkyscraperHQ CEO identity. "
        "You are powered through the Brain Router API Gene Pool. "
        "Do not claim to be Ren or a local GPU fallback. "
        "Keep the answer direct.\n\n"
    )

    res = test_provider(provider, key, identity_prefix + prompt)
    ok = res["status"] == "ok"

    out = {
        **base,
        "ok": ok,
        "selected": selected_public,
        "provider_result": res,
        "answer": "Provider call completed. See preview/provider_result. Full extraction can be added in V2.",
    }
    write_log({"event": "route", **out})
    return out

def last_logs(limit=50):
    if not LOG_JSONL.exists():
        return []
    lines = LOG_JSONL.read_text(errors="ignore").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"raw": safe_text(line)})
    return out

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SkyscraperHQ Brain Router · API Gene Pool</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --bg:#071019; --panel:#0d1b2a; --panel2:#12263a; --text:#ecf7ff; --muted:#99aec2;
  --ok:#32d583; --bad:#ff5c7a; --warn:#fdb022; --line:#24435f; --blue:#7dd3fc;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at top,#12263a,#071019 60%);color:var(--text);font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif}
header{padding:20px;border-bottom:1px solid var(--line);background:rgba(0,0,0,.25);position:sticky;top:0;backdrop-filter:blur(8px);z-index:2}
h1{margin:0;font-size:24px}
.sub{color:var(--muted);margin-top:6px}
.wrap{padding:18px;display:grid;gap:16px}
.row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.card{background:linear-gradient(180deg,var(--panel),#091521);border:1px solid var(--line);border-radius:16px;padding:14px;box-shadow:0 8px 24px rgba(0,0,0,.24)}
.card h3{margin:0 0 8px;font-size:17px}
.badge{display:inline-block;border-radius:999px;padding:4px 9px;font-size:12px;border:1px solid var(--line);color:var(--muted);margin-right:6px}
.ok{color:var(--ok);border-color:rgba(50,213,131,.5)}
.bad{color:var(--bad);border-color:rgba(255,92,122,.5)}
.warn{color:var(--warn);border-color:rgba(253,176,34,.5)}
button{background:#174568;color:white;border:1px solid #2e668e;border-radius:10px;padding:9px 12px;font-weight:700;cursor:pointer}
button:hover{background:#1d567f}
textarea,input,select{width:100%;background:#06111c;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px}
pre{white-space:pre-wrap;word-break:break-word;background:#06111c;border:1px solid var(--line);border-radius:12px;padding:12px;max-height:360px;overflow:auto}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.small{font-size:12px;color:var(--muted)}
.provider{position:relative;overflow:hidden}
.provider:before{content:"";position:absolute;inset:0 0 auto 0;height:4px;background:var(--line)}
.provider.status-ok:before{background:var(--ok)}
.provider.status-billing_or_quota:before,.provider.status-rate_limited:before{background:var(--warn)}
.provider.status-auth_failed:before,.provider.status-missing_key:before,.provider.status-network_or_timeout:before{background:var(--bad)}
@media(max-width:1000px){.row{grid-template-columns:1fr 1fr}.grid2{grid-template-columns:1fr}}
@media(max-width:650px){.row{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <h1>🧠 SkyscraperHQ Brain Router · API Gene Pool</h1>
  <div class="sub">Internal SkyscraperHQ router. CEOs use API Gene Pool only. Ren/GPU stays protected. Claude HQ is the correct name.</div>
</header>

<div class="wrap">
  <div class="card">
    <button onclick="scan()">Scan Vault</button>
    <button onclick="testAll()">Test All Providers</button>
    <button onclick="routeDry()">Dry Route Test</button>
    <button onclick="routeReal()">Tiny Real Route Test</button>
    <span id="status" class="badge">idle</span>
  </div>

  <div class="row" id="providers"></div>

  <div class="grid2">
    <div class="card">
      <h3>CEO Route Test</h3>
      <label class="small">CEO identity</label>
      <select id="ceo">
        <option>Claude HQ</option>
        <option>CEO 2</option>
        <option>CEO 3</option>
      </select>
      <br><br>
      <label class="small">Task type</label>
      <select id="task">
        <option value="architecture">architecture</option>
        <option value="coding">coding</option>
        <option value="summary">summary</option>
        <option value="cheap">cheap</option>
        <option value="default">default</option>
      </select>
      <br><br>
      <textarea id="prompt" rows="7">Explain in one sentence what the Brain Router API Gene Pool is doing.</textarea>
    </div>

    <div class="card">
      <h3>Router Result</h3>
      <pre id="result">No route yet.</pre>
    </div>
  </div>

  <div class="card">
    <h3>Doctrine</h3>
    <pre>Brain Router = internal SkyscraperHQ intelligence switchboard.
API Gene Pool = Claude, OpenAI, DeepSeek, Gemini, Cohere, Kimi, Grok/xAI, Groq, and other vault APIs.
CEOs = API Gene Pool only.
No automatic local model fallback for CEOs.
Ren owns the local GPU side and is not consumed by CEO routing.
Local SkyscraperHQ owns identity, memory, logs, permissions, and dashboard control.</pre>
  </div>

  <div class="card">
    <h3>Last Router Logs</h3>
    <pre id="logs">Loading...</pre>
  </div>
</div>

<script>
async function jget(u){ const r=await fetch(u); return await r.json(); }
async function jpost(u,o){ const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)}); return await r.json(); }
function setStatus(s){ document.getElementById('status').textContent=s; }
function esc(x){ return String(x??'').replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function providerCard(p){
  const st=(p.last_status&&p.last_status.status)||'not_tested';
  const cls='provider status-'+st;
  const badge = st==='ok' ? 'ok' : (st==='not_tested'?'warn':(st==='missing_key'?'bad':'warn'));
  const keys = (p.keys||[]).map(k=>`${k.masked} · ${k.fingerprint}`).join('\n') || 'No key found';
  return `<div class="card ${cls}">
    <h3>${esc(p.label)}</h3>
    <span class="badge ${badge}">${esc(st)}</span>
    <span class="badge">${esc(p.cost_tier)}</span>
    <p class="small">${esc(p.role)}</p>
    <p><b>Keys:</b> ${p.key_count}</p>
    <pre>${esc(keys)}</pre>
    <p class="small">Model: ${esc(p.default_model)}</p>
    <p class="small">Last: ${esc((p.last_status&&p.last_status.preview)||'')}</p>
  </div>`;
}

async function scan(){
  setStatus('scanning...');
  const data=await jget('/api/providers');
  const arr=Object.values(data.providers||{});
  document.getElementById('providers').innerHTML=arr.map(providerCard).join('');
  setStatus('scan complete');
  await loadLogs();
}

async function testAll(){
  setStatus('testing providers...');
  const data=await jpost('/api/test_all',{});
  document.getElementById('result').textContent=JSON.stringify(data,null,2);
  await scan();
  setStatus('provider test complete');
}

async function routeDry(){
  setStatus('dry routing...');
  const data=await jpost('/api/route',{
    ceo:document.getElementById('ceo').value,
    task_type:document.getElementById('task').value,
    prompt:document.getElementById('prompt').value,
    dry_run:true
  });
  document.getElementById('result').textContent=JSON.stringify(data,null,2);
  await loadLogs();
  setStatus('dry route complete');
}

async function routeReal(){
  setStatus('real tiny route...');
  const data=await jpost('/api/route',{
    ceo:document.getElementById('ceo').value,
    task_type:document.getElementById('task').value,
    prompt:document.getElementById('prompt').value,
    dry_run:false
  });
  document.getElementById('result').textContent=JSON.stringify(data,null,2);
  await loadLogs();
  await scan();
  setStatus('real route complete');
}

async function loadLogs(){
  const data=await jget('/api/logs');
  document.getElementById('logs').textContent=JSON.stringify(data.logs||[],null,2);
}

scan();
loadLogs();
setInterval(loadLogs, 8000);
</script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    server_version = "SkyscraperGenePoolRouter/1.0"

    def log_message(self, fmt, *args):
        return

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/dashboard"):
            return response_html(self, HTML)

        if path == "/health":
            return response_json(self, {
                "ok": True,
                "service": "SkyscraperHQ Brain Router API Gene Pool Dashboard",
                "port": PORT,
                "ts": now_iso(),
                "doctrine": "CEOs use API Gene Pool only. Ren/GPU untouched.",
            })

        if path == "/api/providers":
            providers = scan_keys()
            public = json.loads(json.dumps(providers))
            for pdata in public.values():
                for k in pdata["keys"]:
                    k.pop("_secret", None)
            return response_json(self, {"ok": True, "ts": now_iso(), "providers": public, "ceos": CEOS})

        if path == "/api/logs":
            return response_json(self, {"ok": True, "logs": last_logs(80)})

        if path == "/api/state":
            if STATE_JSON.exists():
                try:
                    return response_json(self, json.loads(STATE_JSON.read_text(errors="ignore")))
                except Exception:
                    pass
            return response_json(self, {"ok": False, "error": "state not ready"}, 404)

        return response_json(self, {"ok": False, "error": "not found", "path": path}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = read_json_body(self)

        if path == "/api/test_all":
            results = test_all()
            return response_json(self, {"ok": True, "ts": now_iso(), "results": results})

        if path == "/api/route":
            result = route_prompt(body)
            return response_json(self, result, 200 if result.get("ok") else 503)

        return response_json(self, {"ok": False, "error": "not found", "path": path}, 404)

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[BOOT] SkyscraperHQ Brain Router API Gene Pool Dashboard on {HOST}:{PORT}", flush=True)
    print("[BOOT] CEOs use API Gene Pool only. Ren/GPU untouched.", flush=True)
    scan_keys()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.serve_forever()

if __name__ == "__main__":
    main()
PY

chmod +x "$APP"

echo "[OK] wrote $APP"

echo
echo "===== 2. WRITE STARTER SCRIPT ====="

cat > "$STARTER" <<EOF2
#!/usr/bin/env bash
set -u
cd "$PROJECT" || exit 1
mkdir -p "$LOG_DIR" "$PROJECT/runtime"
export GENE_POOL_ROUTER_HOST="0.0.0.0"
export GENE_POOL_ROUTER_PORT="$PORT"

# Load known env vaults if present. Missing files are fine.
for f in \\
  "/home/ross/.skyscraper_secrets/anthropic_api.env" \\
  "$PROJECT/vaults/keys/anthropic_api.env" \\
  "$PROJECT/floors/floor_28_security_department/vault/.env.anthropic" \\
  "$PROJECT/vaults/keys/openai_api.env" \\
  "$PROJECT/vaults/keys/deepseek_api.env" \\
  "$PROJECT/vaults/keys/gemini_api.env" \\
  "$PROJECT/vaults/keys/cohere_api.env" \\
  "$PROJECT/vaults/keys/kimi_api.env" \\
  "$PROJECT/vaults/keys/grok_api.env" \\
  "$PROJECT/vaults/keys/groq_api.env"
do
  if [ -f "\$f" ]; then
    set -a
    . "\$f"
    set +a
  fi
done

exec python3 -u "$APP"
EOF2

chmod +x "$STARTER"
echo "[OK] wrote $STARTER"

echo
echo "===== 3. COMPILE CHECK ====="
python3 -m py_compile "$APP" && echo "[OK] app compiles" || exit 2

echo
echo "===== 4. STOP OLD GENE POOL ROUTER ON PORT $PORT ====="
if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ]; then
    kill "$OLD" 2>/dev/null || true
  fi
fi

pkill -f "skyscraper_gene_pool_router.py" 2>/dev/null || true
sleep 2

echo
echo "===== 5. DEPLOY DASHBOARD ====="
nohup "$STARTER" >> "$LOG" 2>&1 &
PID="$!"
echo "$PID" > "$PIDFILE"
echo "[OK] started pid=$PID"
echo "Log: $LOG"

echo
echo "===== 6. WAIT FOR PORT ====="
OK="NO"
for i in $(seq 1 20); do
  if curl -sS --max-time 2 "http://127.0.0.1:$PORT/health" >/tmp/gene_pool_health.json 2>/dev/null; then
    OK="YES"
    break
  fi
  sleep 1
done

if [ "$OK" != "YES" ]; then
  echo "[FAIL] Dashboard did not come online."
  echo "--- log tail ---"
  tail -n 120 "$LOG" || true
  cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
  exit 3
fi

echo "[OK] dashboard online"

echo
echo "===== 7. OPEN DASHBOARD ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
LOCAL_URL="http://127.0.0.1:$PORT"
LAN_URL="http://${LAN_IP:-127.0.0.1}:$PORT"

echo "Local URL: $LOCAL_URL"
echo "LAN URL:   $LAN_URL"

if command -v wslview >/dev/null 2>&1; then
  wslview "$LOCAL_URL" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$LOCAL_URL" >/dev/null 2>&1 || true
elif command -v python3 >/dev/null 2>&1; then
  python3 - <<PYOPEN >/dev/null 2>&1 || true
import webbrowser
webbrowser.open("$LOCAL_URL")
PYOPEN
fi

echo
echo "===== 8. LINUX SMOKE TESTS ====="

echo "--- health"
curl -sS --max-time 10 "$LOCAL_URL/health" | python3 -m json.tool || true

echo
echo "--- providers scan"
curl -sS --max-time 25 "$LOCAL_URL/api/providers" > "$RUN_DIR/reports/providers_scan.json"
python3 - <<PYSHOW
import json
p="$RUN_DIR/reports/providers_scan.json"
data=json.load(open(p))
print("ok:", data.get("ok"))
for name, info in data.get("providers",{}).items():
    print(f"{name:8s} keys={info.get('key_count')} status={info.get('last_status',{}).get('status')}")
PYSHOW

echo
echo "--- dry route test"
curl -sS --max-time 20 \
  -H 'Content-Type: application/json' \
  -d '{"ceo":"Claude HQ","task_type":"architecture","prompt":"Explain the API Gene Pool in one sentence.","dry_run":true}' \
  "$LOCAL_URL/api/route" > "$RUN_DIR/reports/dry_route_test.json"
python3 -m json.tool "$RUN_DIR/reports/dry_route_test.json" || cat "$RUN_DIR/reports/dry_route_test.json"

echo
echo "--- provider real ping tests"
echo "This makes tiny provider calls only where keys are detected."
curl -sS --max-time 180 \
  -H 'Content-Type: application/json' \
  -d '{}' \
  "$LOCAL_URL/api/test_all" > "$RUN_DIR/reports/provider_real_ping_tests.json"
python3 - <<PYTEST
import json
p="$RUN_DIR/reports/provider_real_ping_tests.json"
try:
    data=json.load(open(p))
except Exception as e:
    print("Could not parse provider test JSON:", e)
    print(open(p).read()[:2000])
    raise SystemExit
print("ok:", data.get("ok"))
for r in data.get("results",[]):
    print(f"{r.get('provider','?'):8s} {r.get('status','?'):22s} http={r.get('http')} latency={r.get('latency_s')} model={r.get('model')}")
PYTEST

echo
echo "--- logs endpoint"
curl -sS --max-time 20 "$LOCAL_URL/api/logs" > "$RUN_DIR/reports/router_logs.json"
python3 - <<PYLOGS
import json
p="$RUN_DIR/reports/router_logs.json"
data=json.load(open(p))
print("log entries:", len(data.get("logs",[])))
for x in data.get("logs",[])[-8:]:
    print(x.get("ts"), x.get("event"), x.get("provider"), x.get("status"))
PYLOGS

echo
echo "===== 9. LISTENING PORTS ====="
ss -ltnp | grep -E ":$PORT|:8850|:8852|:11434" || true

echo
echo "===== 10. RECENT APP LOG ====="
tail -n 80 "$LOG" || true

echo
echo "============================================================"
echo "DONE — GENE POOL ROUTER DASHBOARD IS DEPLOYED"
echo "Open:"
echo "$LOCAL_URL"
echo "$LAN_URL"
echo
echo "Report:"
echo "$REPORT"
echo
echo "Send this back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$RUN_DIR/reports/providers_scan.json" "$SEND/providers_scan.json"
cp -a "$RUN_DIR/reports/provider_real_ping_tests.json" "$SEND/provider_real_ping_tests.json"
cp -a "$RUN_DIR/reports/dry_route_test.json" "$SEND/dry_route_test.json"

