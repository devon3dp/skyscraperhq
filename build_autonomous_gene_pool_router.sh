#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
PORT="8860"
APP="$PROJECT/tools/skyscraper_gene_pool_router.py"
STARTER="$PROJECT/run_gene_pool_router.sh"
LOG="$PROJECT/logs/gene_pool_router_8860.log"
PIDFILE="$PROJECT/runtime/gene_pool_router_8860.pid"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_autonomous_gene_pool_router"
REPORT="$RUN_DIR/reports/autonomous_gene_pool_router_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$PROJECT/tools" "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries" "$PROJECT/vaults/gene_pool" "$SEND"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — AUTONOMOUS BRAIN ROUTER GENE POOL"
echo "Generated: $(date -Is)"
echo "Port: $PORT"
echo "============================================================"
echo "Rules:"
echo " - No manual dashboard options required."
echo " - Dashboard runs and animates by itself."
echo " - Linux/vault API scan runs automatically."
echo " - API keys are consolidated into local secure gene-pool vault."
echo " - Full keys are NOT printed to screen/report."
echo " - Claude HQ is the correct name."
echo " - Wren owns/protects local GPU."
echo " - CEOs use API Gene Pool only."
echo " - No CEO fallback to Wren/local GPU."
echo "============================================================"

cd "$PROJECT" || exit 1

[ -f "$APP" ] && cp -a "$APP" "$RUN_DIR/backups/skyscraper_gene_pool_router.py.bak_$STAMP"
[ -f "$STARTER" ] && cp -a "$STARTER" "$RUN_DIR/backups/run_gene_pool_router.sh.bak_$STAMP"

echo
echo "===== 1. WRITE AUTONOMOUS ROUTER APP ====="

cat > "$APP" <<'PY'
#!/usr/bin/env python3
import os, re, json, time, hashlib, random, threading, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PROJECT = Path("/vaults/nvme0/qsb_tower_v1")
PORT = int(os.environ.get("GENE_POOL_ROUTER_PORT", "8860"))
HOST = os.environ.get("GENE_POOL_ROUTER_HOST", "0.0.0.0")

DATA = PROJECT / "data" / "registries"
VAULT = PROJECT / "vaults" / "gene_pool"
SECURE_STORE = VAULT / "gene_pool_keys.secure.env"
PUBLIC_STORE = DATA / "gene_pool_keys_public.json"
STATE = DATA / "gene_pool_router_state.json"
LOG = DATA / "gene_pool_router_live_events.jsonl"

SCAN_INTERVAL = 90
ROUTE_INTERVAL = 6
PROVIDER_TEST_INTERVAL = 300

PROVIDERS = {
    "claude": {
        "label": "Claude",
        "env": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
        "patterns": [r"sk-ant-[A-Za-z0-9_\-]{20,}"],
        "role": "deep reasoning / Claude HQ preferred when funded",
        "tier": "premium",
        "model": "claude-haiku-4-5-20251001"
    },
    "openai": {
        "label": "OpenAI",
        "env": ["OPENAI_API_KEY"],
        "patterns": [r"sk-proj-[A-Za-z0-9_\-]{20,}", r"sk-[A-Za-z0-9_\-]{32,}"],
        "role": "structured reasoning / planning",
        "tier": "medium",
        "model": "gpt-4.1-mini"
    },
    "deepseek": {
        "label": "DeepSeek",
        "env": ["DEEPSEEK_API_KEY"],
        "patterns": [r"sk-[A-Za-z0-9_\-]{32,}"],
        "role": "coding / cheap reasoning",
        "tier": "low",
        "model": "deepseek-chat"
    },
    "gemini": {
        "label": "Gemini",
        "env": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"],
        "patterns": [r"AIza[A-Za-z0-9_\-]{20,}"],
        "role": "long context / broad reasoning",
        "tier": "low-medium",
        "model": "gemini-1.5-flash"
    },
    "cohere": {
        "label": "Cohere",
        "env": ["COHERE_API_KEY"],
        "patterns": [r"[A-Za-z0-9_\-]{40,}"],
        "role": "retrieval / ranking / summaries",
        "tier": "low-medium",
        "model": "command-r7b-12-2024"
    },
    "kimi": {
        "label": "Kimi",
        "env": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
        "patterns": [r"sk-[A-Za-z0-9_\-]{32,}"],
        "role": "long document reasoning",
        "tier": "low-medium",
        "model": "moonshot-v1-8k"
    },
    "grok": {
        "label": "Grok / xAI",
        "env": ["GROK_API_KEY", "XAI_API_KEY"],
        "patterns": [r"xai-[A-Za-z0-9_\-]{20,}", r"sk-[A-Za-z0-9_\-]{32,}"],
        "role": "alternate reasoning perspective",
        "tier": "medium",
        "model": "grok-2-latest"
    },
    "groq": {
        "label": "Groq",
        "env": ["GROQ_API_KEY"],
        "patterns": [r"gsk_[A-Za-z0-9_\-]{20,}"],
        "role": "fast hosted inference",
        "tier": "low",
        "model": "llama-3.1-8b-instant"
    }
}

ROOTS = [
    Path("/home/ross/.skyscraper_secrets"),
    Path("/home/ross/.claude"),
    PROJECT / "vaults",
    PROJECT / "floors",
    PROJECT / "config",
    PROJECT / "data",
    PROJECT / "tools",
]

SKIP = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".cache",
    "cache", "models", "model", "ollama", "huggingface", "external_oss",
    "datasets", "downloads"
}

POLICY = {
    "architecture": ["claude", "openai", "kimi", "gemini", "deepseek", "grok", "groq", "cohere"],
    "coding": ["deepseek", "openai", "claude", "kimi", "groq", "gemini", "grok", "cohere"],
    "summary": ["cohere", "gemini", "kimi", "openai", "deepseek", "groq", "claude", "grok"],
    "cheap": ["groq", "deepseek", "gemini", "cohere", "kimi", "openai", "claude", "grok"],
    "default": ["openai", "deepseek", "kimi", "gemini", "claude", "groq", "grok", "cohere"]
}

CEOS = ["Claude HQ", "CEO 2", "CEO 3"]
TASKS = ["architecture", "coding", "summary", "cheap", "default"]

LOCK = threading.Lock()
BOOT_TS = time.time()
KEYS = {}
PUBLIC = {}
EVENTS = []
STATUS = {}
AUTONOMY = {
    "enabled": True,
    "last_scan": None,
    "last_route": None,
    "last_provider_test": None,
    "scan_count": 0,
    "route_count": 0,
    "stored_key_count": 0
}

def now():
    return datetime.now(timezone.utc).isoformat()

def sha16(s):
    return hashlib.sha256(s.encode("utf-8", "ignore")).hexdigest()[:16]

def mask(k):
    if not k:
        return ""
    if len(k) < 20:
        return k[:4] + "..." + k[-4:]
    return k[:12] + "..." + k[-8:]

def safe(s, n=600):
    s = str(s or "")
    for rx in [
        r"sk-ant-[A-Za-z0-9_\-]{20,}",
        r"sk-proj-[A-Za-z0-9_\-]{20,}",
        r"gsk_[A-Za-z0-9_\-]{20,}",
        r"xai-[A-Za-z0-9_\-]{20,}",
        r"AIza[A-Za-z0-9_\-]{20,}",
        r"sk-[A-Za-z0-9_\-]{32,}"
    ]:
        s = re.sub(rx, lambda m: mask(m.group(0)), s)
    return s.replace("\n", " ")[:n]

def event(obj):
    obj["ts"] = now()
    with LOCK:
        EVENTS.append(obj)
        del EVENTS[:-200]
    DATA.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def classify_source_path(p):
    low = str(p).lower()
    return any(x in low for x in [
        "env", "key", "secret", "vault", "token", "credential", "credentials",
        "claude", "openai", "deepseek", "gemini", "cohere", "kimi",
        "moonshot", "grok", "groq", "xai", "anthropic"
    ])

def scan_linux_for_keys(max_files=90000):
    found = {p: {} for p in PROVIDERS}

    for provider, cfg in PROVIDERS.items():
        for env_name in cfg["env"]:
            val = os.environ.get(env_name, "").strip()
            if val:
                found[provider].setdefault(val, set()).add("process_env:" + env_name)

    files_scanned = 0
    for root in ROOTS:
        if not root.exists():
            continue

        for p in root.rglob("*"):
            if files_scanned >= max_files:
                break

            try:
                if not p.is_file():
                    continue
                if any(part in SKIP for part in p.parts):
                    continue
                if p.stat().st_size > 3_000_000:
                    continue
                if not classify_source_path(p):
                    continue
                txt = p.read_text(errors="ignore")
                files_scanned += 1
            except Exception:
                continue

            for provider, cfg in PROVIDERS.items():
                lowp = str(p).lower()
                lowt = txt[:5000].lower()
                provider_hint = provider in lowp or provider in lowt or cfg["label"].lower().split()[0] in lowt

                for env_name in cfg["env"]:
                    rx = re.compile(rf"(?:export\s+)?{re.escape(env_name)}\s*=\s*['\"]?([^'\"\n\r #]+)", re.I)
                    for m in rx.finditer(txt):
                        k = m.group(1).strip()
                        if len(k) >= 16:
                            found[provider].setdefault(k, set()).add(str(p) + ":" + env_name)

                if provider_hint:
                    for pat in cfg["patterns"]:
                        for m in re.finditer(pat, txt):
                            k = m.group(0).strip()
                            if len(k) >= 16:
                                found[provider].setdefault(k, set()).add(str(p))

    return found, files_scanned

def write_secure_store(found):
    VAULT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    secure_lines = [
        "# SkyscraperHQ Brain Router API Gene Pool secure store",
        "# Full keys are kept local only. Do not paste this file into chat.",
        "# Generated: " + now(),
        ""
    ]

    public = {}
    total = 0

    for provider, keymap in found.items():
        cfg = PROVIDERS[provider]
        public[provider] = {
            "provider": provider,
            "label": cfg["label"],
            "role": cfg["role"],
            "tier": cfg["tier"],
            "model": cfg["model"],
            "key_count": 0,
            "keys": [],
            "status": "missing"
        }

        idx = 0
        for key, sources in keymap.items():
            idx += 1
            total += 1
            var = f"GENE_POOL_{provider.upper()}_{idx}"
            secure_lines.append(f'{var}="{key}"')
            secure_lines.append(f'# {var}_FINGERPRINT="{sha16(key)}"')
            secure_lines.append(f'# {var}_MASKED="{mask(key)}"')
            secure_lines.append("")

            public[provider]["keys"].append({
                "masked": mask(key),
                "fingerprint": sha16(key),
                "sources": sorted(list(sources))[:10]
            })

        public[provider]["key_count"] = len(public[provider]["keys"])
        public[provider]["status"] = "stored" if public[provider]["key_count"] else "missing"

    SECURE_STORE.write_text("\n".join(secure_lines) + "\n", encoding="utf-8")
    os.chmod(SECURE_STORE, 0o600)

    PUBLIC_STORE.write_text(json.dumps({
        "ts": now(),
        "secure_store": str(SECURE_STORE),
        "full_keys_printed": False,
        "providers": public
    }, indent=2), encoding="utf-8")

    return public, total

def load_store():
    global KEYS, PUBLIC
    KEYS = {p: [] for p in PROVIDERS}
    PUBLIC = {p: {
        "provider": p,
        "label": PROVIDERS[p]["label"],
        "role": PROVIDERS[p]["role"],
        "tier": PROVIDERS[p]["tier"],
        "model": PROVIDERS[p]["model"],
        "key_count": 0,
        "keys": [],
        "status": "missing"
    } for p in PROVIDERS}

    if not SECURE_STORE.exists():
        return

    txt = SECURE_STORE.read_text(errors="ignore")
    for provider in PROVIDERS:
        rx = re.compile(rf'GENE_POOL_{provider.upper()}_(\d+)="([^"]+)"')
        for m in rx.finditer(txt):
            key = m.group(2)
            KEYS[provider].append(key)
            PUBLIC[provider]["keys"].append({
                "masked": mask(key),
                "fingerprint": sha16(key),
                "sources": ["secure_store"]
            })

        PUBLIC[provider]["key_count"] = len(KEYS[provider])
        PUBLIC[provider]["status"] = "stored" if KEYS[provider] else "missing"

def auto_scan():
    found, scanned = scan_linux_for_keys()
    public, total = write_secure_store(found)
    load_store()
    AUTONOMY["last_scan"] = now()
    AUTONOMY["scan_count"] += 1
    AUTONOMY["stored_key_count"] = total
    event({
        "event": "auto_scan",
        "from": "Linux vault scanner",
        "to": "Brain Router secure store",
        "provider": "all",
        "status": "stored",
        "detail": f"scanned {scanned} files; stored {total} API key entries locally"
    })

def choose_provider(task):
    load_store()
    pref = POLICY.get(task, POLICY["default"])
    for p in pref:
        if KEYS.get(p):
            return p
    return None

def auto_route_once():
    ceo = CEOS[AUTONOMY["route_count"] % len(CEOS)]
    task = TASKS[AUTONOMY["route_count"] % len(TASKS)]
    provider = choose_provider(task)

    event({
        "event": "request",
        "from": ceo,
        "to": "Brain Router",
        "provider": provider or "none",
        "task": task,
        "status": "received",
        "detail": "autonomous CEO cycle entered router"
    })

    if not provider:
        event({
            "event": "blocked",
            "from": "Brain Router",
            "to": ceo,
            "provider": "none",
            "task": task,
            "status": "blocked",
            "detail": "no API Gene Pool key available; CEOs do not fall back to Wren/local GPU"
        })
        AUTONOMY["route_count"] += 1
        AUTONOMY["last_route"] = now()
        return

    label = PROVIDERS[provider]["label"]

    event({
        "event": "dispatch",
        "from": "Brain Router",
        "to": label,
        "provider": provider,
        "task": task,
        "status": "selected",
        "detail": "provider selected from API Gene Pool by autonomous policy"
    })

    event({
        "event": "return",
        "from": label,
        "to": ceo,
        "provider": provider,
        "task": task,
        "status": "visual_live",
        "detail": "live autonomous visual route completed"
    })

    AUTONOMY["route_count"] += 1
    AUTONOMY["last_route"] = now()

def provider_health_visual():
    load_store()
    for provider, keys in KEYS.items():
        if keys:
            STATUS[provider] = {
                "provider": provider,
                "label": PROVIDERS[provider]["label"],
                "status": "key_available",
                "key_count": len(keys),
                "latency_ms": random.randint(80, 900),
                "rev": random.randint(35, 95),
                "tested_at": now()
            }
        else:
            STATUS[provider] = {
                "provider": provider,
                "label": PROVIDERS[provider]["label"],
                "status": "missing_key",
                "key_count": 0,
                "latency_ms": None,
                "rev": 0,
                "tested_at": now()
            }

    AUTONOMY["last_provider_test"] = now()
    event({
        "event": "health",
        "from": "Brain Router",
        "to": "API Gene Pool",
        "provider": "all",
        "status": "checked",
        "detail": "provider availability refreshed from secure key store"
    })

def background():
    time.sleep(1)
    try:
        auto_scan()
    except Exception as e:
        event({"event": "scan_error", "from": "Linux vault scanner", "to": "Brain Router", "provider": "all", "status": "error", "detail": safe(e)})

    try:
        provider_health_visual()
    except Exception as e:
        event({"event": "health_error", "from": "Brain Router", "to": "API Gene Pool", "provider": "all", "status": "error", "detail": safe(e)})

    last_scan = time.time()
    last_health = time.time()

    while True:
        try:
            auto_route_once()
        except Exception as e:
            event({"event": "route_error", "from": "Autonomy", "to": "Brain Router", "provider": "all", "status": "error", "detail": safe(e)})

        if time.time() - last_scan > SCAN_INTERVAL:
            try:
                auto_scan()
            except Exception as e:
                event({"event": "scan_error", "from": "Linux vault scanner", "to": "Brain Router", "provider": "all", "status": "error", "detail": safe(e)})
            last_scan = time.time()

        if time.time() - last_health > PROVIDER_TEST_INTERVAL:
            try:
                provider_health_visual()
            except Exception as e:
                event({"event": "health_error", "from": "Brain Router", "to": "API Gene Pool", "provider": "all", "status": "error", "detail": safe(e)})
            last_health = time.time()

        save_state()
        time.sleep(ROUTE_INTERVAL)

def recent(n=160):
    if LOG.exists():
        rows = []
        for line in LOG.read_text(errors="ignore").splitlines()[-n:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
        return rows
    return EVENTS[-n:]

def metrics():
    logs = recent(240)
    counts = {}
    for e in logs:
        p = e.get("provider", "unknown")
        counts[p] = counts.get(p, 0) + 1

    active_keys = sum(1 for p in PUBLIC.values() if p.get("key_count", 0) > 0)
    return {
        "uptime_s": int(time.time() - BOOT_TS),
        "events": len(logs),
        "stored_key_count": AUTONOMY["stored_key_count"],
        "active_provider_count": active_keys,
        "provider_counts": counts,
        "autonomy": AUTONOMY,
        "active": logs[-1] if logs else {},
        "rev": {
            "router": min(100, 25 + (AUTONOMY["route_count"] % 70)),
            "api_pool": min(100, active_keys * 12),
            "ceo_load": random.randint(30, 88),
            "wren_guard": 100
        }
    }

def save_state():
    DATA.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "ts": now(),
        "doctrine": {
            "brain_router": "inside SkyscraperHQ",
            "ceos": "API Gene Pool only",
            "wren": "owns/protects local GPU; no CEO local fallback",
            "claude_hq": "correct visible name"
        },
        "metrics": metrics(),
        "providers": PUBLIC,
        "status": STATUS
    }, indent=2), encoding="utf-8")

HTML = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>SkyscraperHQ · Autonomous Brain Router</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#020610;--panel:#071426;--panel2:#0c2035;--line:#1e4566;--text:#e8f7ff;--muted:#8ca9bd;--cyan:#42d9ff;--green:#45f59b;--amber:#ffc857;--red:#ff5d7d;--purple:#b987ff}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at 50% 0,#173655 0,#06101d 48%,#02050b 100%);color:var(--text);font-family:system-ui,Segoe UI,Arial,sans-serif;overflow-x:hidden}
header{padding:16px 20px;border-bottom:1px solid var(--line);background:rgba(0,0,0,.35);backdrop-filter:blur(10px);position:sticky;top:0;z-index:10}
h1{margin:0;font-size:24px}.sub{color:var(--muted);font-size:13px;margin-top:4px}
.main{display:grid;grid-template-columns:1.2fr .8fr;gap:14px;padding:14px}
.card{background:linear-gradient(180deg,rgba(13,32,54,.94),rgba(4,12,23,.94));border:1px solid var(--line);border-radius:18px;padding:14px;box-shadow:0 12px 34px rgba(0,0,0,.34)}
.flow{height:610px;position:relative;overflow:hidden}
.node{position:absolute;width:145px;height:76px;border:1px solid var(--line);border-radius:18px;background:rgba(5,18,32,.88);display:grid;place-items:center;text-align:center;box-shadow:0 0 22px rgba(66,217,255,.08)}
.node b{display:block}.node small{color:var(--muted)}
.router{left:50%;top:255px;transform:translateX(-50%);width:180px;height:102px;border-color:var(--cyan);box-shadow:0 0 30px rgba(66,217,255,.28)}
.claude{left:34px;top:58px}.ceo2{left:34px;top:252px}.ceo3{left:34px;top:446px}
.wren{right:34px;bottom:28px;border-color:var(--green);box-shadow:0 0 26px rgba(69,245,155,.24)}
.provider{right:36px;width:142px;height:60px}.p0{top:18px}.p1{top:86px}.p2{top:154px}.p3{top:222px}.p4{top:290px}.p5{top:358px}.p6{top:426px}.p7{top:494px}
svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.line{stroke:#1d5f86;stroke-width:2;opacity:.5;stroke-dasharray:7 8;animation:dash 1.8s linear infinite}
.line.wrenline{stroke:#246b49;opacity:.35}
@keyframes dash{to{stroke-dashoffset:-30}}
.packet{position:absolute;width:11px;height:11px;border-radius:50%;background:var(--cyan);box-shadow:0 0 18px var(--cyan);opacity:0;z-index:5}
.packet.go{animation:move 1.15s linear forwards}
@keyframes move{0%{opacity:0;transform:translate(var(--x1),var(--y1)) scale(.55)}12%{opacity:1}100%{opacity:0;transform:translate(var(--x2),var(--y2)) scale(1.2)}}
.gauges{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.gauge{height:122px;display:grid;place-items:center;border-radius:16px;background:#061426;border:1px solid var(--line);position:relative}
.dial{width:84px;height:84px;border-radius:50%;background:conic-gradient(var(--green) calc(var(--v)*1%),#10263a 0);display:grid;place-items:center;transition:.5s}
.dial:after{content:attr(data-v) '%';width:60px;height:60px;border-radius:50%;background:#061426;display:grid;place-items:center;font-weight:900}
.gauge span{position:absolute;bottom:9px;color:var(--muted);font-size:12px}
.providers{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.prov{padding:10px;border:1px solid var(--line);border-radius:14px;background:#061426;min-height:100px}
.prov.ok{border-color:rgba(69,245,155,.75);box-shadow:0 0 14px rgba(69,245,155,.08)}
.prov.bad{border-color:rgba(255,93,125,.55)}
.prov b{display:block}.prov small{color:var(--muted)}
.stream{height:325px;overflow:auto;background:#040b14;border:1px solid var(--line);border-radius:14px;padding:10px;font-family:ui-monospace,monospace;font-size:12px}
.event{padding:6px;border-bottom:1px solid rgba(255,255,255,.05)}.ok{color:var(--green)}.warn{color:var(--amber)}.bad{color:var(--red)}
.statusgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.statusbox{background:#061426;border:1px solid var(--line);border-radius:14px;padding:10px}
.big{font-size:26px;font-weight:900}
.autopulse{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--green);box-shadow:0 0 16px var(--green);animation:pulse 1s infinite}
@keyframes pulse{50%{opacity:.25;transform:scale(.65)}}
@media(max-width:1050px){.main{grid-template-columns:1fr}.providers,.gauges,.statusgrid{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<header>
<h1>🧠 SkyscraperHQ Autonomous Brain Router · API Gene Pool <span class="autopulse"></span></h1>
<div class="sub">No buttons required. Linux/vault scanner runs automatically. Claude HQ + CEOs route through API Gene Pool. Wren/GPU protected.</div>
</header>

<div class="main">
  <section class="card flow" id="flow">
    <svg id="wires"></svg>
    <div class="node claude" data-node="Claude HQ"><b>Claude HQ</b><small>CEO identity</small></div>
    <div class="node ceo2" data-node="CEO 2"><b>CEO 2</b><small>API only</small></div>
    <div class="node ceo3" data-node="CEO 3"><b>CEO 3</b><small>API only</small></div>
    <div class="node router" data-node="Brain Router"><b>Brain Router</b><small>autonomous selector</small></div>
    <div class="node provider p0" data-provider="claude"><b>Claude</b><small>provider</small></div>
    <div class="node provider p1" data-provider="openai"><b>OpenAI</b><small>provider</small></div>
    <div class="node provider p2" data-provider="deepseek"><b>DeepSeek</b><small>provider</small></div>
    <div class="node provider p3" data-provider="gemini"><b>Gemini</b><small>provider</small></div>
    <div class="node provider p4" data-provider="cohere"><b>Cohere</b><small>provider</small></div>
    <div class="node provider p5" data-provider="kimi"><b>Kimi</b><small>provider</small></div>
    <div class="node provider p6" data-provider="grok"><b>Grok/xAI</b><small>provider</small></div>
    <div class="node provider p7" data-provider="groq"><b>Groq</b><small>provider</small></div>
    <div class="node wren" data-node="Wren"><b>Wren</b><small>GPU guardian</small></div>
  </section>

  <section class="card">
    <div class="gauges">
      <div class="gauge"><div class="dial" id="g_router" style="--v:0" data-v="0"></div><span>Router rev</span></div>
      <div class="gauge"><div class="dial" id="g_pool" style="--v:0" data-v="0"></div><span>API pool</span></div>
      <div class="gauge"><div class="dial" id="g_ceo" style="--v:0" data-v="0"></div><span>CEO load</span></div>
      <div class="gauge"><div class="dial" id="g_wren" style="--v:100" data-v="100"></div><span>Wren guard</span></div>
    </div>
    <br>
    <div class="statusgrid">
      <div class="statusbox"><small>Stored API keys</small><div class="big" id="keycount">0</div></div>
      <div class="statusbox"><small>Active providers</small><div class="big" id="providerscount">0</div></div>
      <div class="statusbox"><small>Autonomous routes</small><div class="big" id="routecount">0</div></div>
    </div>
    <br>
    <h3>Live autonomy state</h3>
    <div class="stream" id="statebox">Loading...</div>
  </section>
</div>

<div class="main">
  <section class="card">
    <h3>API Gene Pool</h3>
    <div class="providers" id="providers"></div>
  </section>
  <section class="card">
    <h3>Rolling live flow graph</h3>
    <div class="stream" id="stream"></div>
  </section>
</div>

<script>
const $=q=>document.querySelector(q);
let lastSeen=0;

function centre(el){
  const f=$("#flow").getBoundingClientRect(), r=el.getBoundingClientRect();
  return {x:r.left-f.left+r.width/2, y:r.top-f.top+r.height/2};
}
function drawWires(){
  const svg=$("#wires"); svg.innerHTML="";
  const router=centre($('[data-node="Brain Router"]'));
  const nodes=[...document.querySelectorAll(".claude,.ceo2,.ceo3,.provider")];
  for(const n of nodes){
    const c=centre(n);
    const l=document.createElementNS("http://www.w3.org/2000/svg","line");
    l.setAttribute("x1",c.x); l.setAttribute("y1",c.y); l.setAttribute("x2",router.x); l.setAttribute("y2",router.y);
    l.setAttribute("class","line");
    svg.appendChild(l);
  }
  const w=centre($('[data-node="Wren"]'));
  const l=document.createElementNS("http://www.w3.org/2000/svg","line");
  l.setAttribute("x1",w.x); l.setAttribute("y1",w.y); l.setAttribute("x2",router.x); l.setAttribute("y2",router.y);
  l.setAttribute("class","line wrenline");
  svg.appendChild(l);
}
function packet(aSel,bSel,color){
  const aEl=$(aSel), bEl=$(bSel); if(!aEl||!bEl)return;
  const a=centre(aEl), b=centre(bEl);
  const p=document.createElement("div");
  p.className="packet";
  if(color){p.style.background=color;p.style.boxShadow=`0 0 18px ${color}`;}
  p.style.setProperty("--x1",(a.x-5)+"px"); p.style.setProperty("--y1",(a.y-5)+"px");
  p.style.setProperty("--x2",(b.x-5)+"px"); p.style.setProperty("--y2",(b.y-5)+"px");
  $("#flow").appendChild(p);
  setTimeout(()=>p.classList.add("go"),20);
  setTimeout(()=>p.remove(),1500);
}
function ceoSel(name){return name==="Claude HQ"?".claude":name==="CEO 2"?".ceo2":".ceo3";}
function provSel(p){return `[data-provider="${p}"]`;}
function setGauge(id,v){v=Math.max(0,Math.min(100,Math.round(v||0)));const e=$(id);e.style.setProperty("--v",v);e.setAttribute("data-v",v);}
async function getJSON(u){const r=await fetch(u);return await r.json();}

function renderProviders(ps){
  $("#providers").innerHTML=Object.values(ps||{}).map(p=>{
    const ok=(p.key_count||0)>0;
    return `<div class="prov ${ok?'ok':'bad'}">
      <b>${p.label}</b>
      <small>${p.role}</small><br>
      <small>keys: ${p.key_count||0} · ${p.tier}</small><br>
      <small>${(p.keys||[]).slice(0,1).map(k=>k.masked+" · "+k.fingerprint).join("")}</small>
    </div>`;
  }).join("");
}
function renderEvents(logs){
  $("#stream").innerHTML=(logs||[]).slice(-70).reverse().map(e=>{
    const cls=e.status==="blocked"||e.status==="error"?"bad":e.status==="selected"||e.status==="stored"?"ok":"warn";
    return `<div class="event"><span class="${cls}">●</span> ${e.ts||""}<br>${e.from||"?"} → ${e.to||"?"} · ${e.provider||""} · ${e.task||""}<br><small>${e.detail||""}</small></div>`;
  }).join("");
}
function animateEvent(e){
  if(!e)return;
  if(e.event==="request") packet(ceoSel(e.from),'[data-node="Brain Router"]');
  if(e.event==="dispatch" && e.provider && e.provider!=="none") packet('[data-node="Brain Router"]',provSel(e.provider),'#42d9ff');
  if(e.event==="return" && e.provider && e.provider!=="none") {
    packet(provSel(e.provider),'[data-node="Brain Router"]','#45f59b');
    setTimeout(()=>packet('[data-node="Brain Router"]',ceoSel(e.to),'#45f59b'),500);
  }
  if(e.event==="auto_scan") packet('[data-node="Wren"]','[data-node="Brain Router"]','#45f59b');
}
async function live(){
  const d=await getJSON("/api/live");
  const m=d.metrics||{};
  const rev=m.rev||{};
  setGauge("#g_router",rev.router);
  setGauge("#g_pool",rev.api_pool);
  setGauge("#g_ceo",rev.ceo_load);
  setGauge("#g_wren",rev.wren_guard);
  $("#keycount").textContent=m.stored_key_count||0;
  $("#providerscount").textContent=m.active_provider_count||0;
  $("#routecount").textContent=(m.autonomy&&m.autonomy.route_count)||0;
  renderProviders(d.providers||{});
  renderEvents(d.logs||[]);
  $("#statebox").textContent=JSON.stringify(m.autonomy||{},null,2);
  const logs=d.logs||[];
  if(logs.length>lastSeen){
    logs.slice(lastSeen).forEach((e,i)=>setTimeout(()=>animateEvent(e),i*250));
    lastSeen=logs.length;
  }
}
drawWires();
window.addEventListener("resize",drawWires);
live();
setInterval(live,1500);
</script>
</body>
</html>'''

def send_json(h, obj, status=200):
    raw = json.dumps(obj, indent=2, ensure_ascii=False).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")
    h.send_header("Content-Length", str(len(raw)))
    h.end_headers()
    h.wfile.write(raw)

def send_html(h):
    raw = HTML.encode()
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Content-Length", str(len(raw)))
    h.end_headers()
    h.wfile.write(raw)

class H(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ["/", "/dashboard"]:
            return send_html(self)
        if p == "/health":
            return send_json(self, {
                "ok": True,
                "service": "SkyscraperHQ Autonomous Brain Router Gene Pool",
                "port": PORT,
                "claude_hq": "correct",
                "wren": "protected",
                "ceos": "api_gene_pool_only",
                "secure_store": str(SECURE_STORE),
                "ts": now()
            })
        if p == "/api/live":
            load_store()
            return send_json(self, {
                "ok": True,
                "metrics": metrics(),
                "providers": PUBLIC,
                "status": STATUS,
                "logs": recent(180)
            })
        if p == "/api/providers":
            load_store()
            return send_json(self, {"ok": True, "providers": PUBLIC, "status": STATUS})
        if p == "/api/logs":
            return send_json(self, {"ok": True, "logs": recent(240)})
        if p == "/api/state":
            if STATE.exists():
                try:
                    return send_json(self, json.loads(STATE.read_text(errors="ignore")))
                except Exception:
                    pass
            return send_json(self, {"ok": False, "error": "state not ready"}, 404)
        return send_json(self, {"ok": False, "error": "not found", "path": p}, 404)

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    VAULT.mkdir(parents=True, exist_ok=True)
    print(f"[BOOT] autonomous Gene Pool Router on {HOST}:{PORT}", flush=True)
    print("[BOOT] Wren/GPU protected. CEOs use API Gene Pool only.", flush=True)
    print(f"[SECURE_STORE] {SECURE_STORE}", flush=True)
    load_store()
    threading.Thread(target=background, daemon=True).start()
    print(f"[READY] http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()

if __name__ == "__main__":
    main()
PY

chmod +x "$APP"
echo "[OK] wrote $APP"

echo
echo "===== 2. WRITE STARTER ====="
cat > "$STARTER" <<EOF2
#!/usr/bin/env bash
set -u
cd "$PROJECT" || exit 1
mkdir -p "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries" "$PROJECT/vaults/gene_pool"

export GENE_POOL_ROUTER_HOST="0.0.0.0"
export GENE_POOL_ROUTER_PORT="$PORT"

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
echo "===== 3. COMPILE ====="
python3 -m py_compile "$APP" && echo "[OK] compiles" || exit 2

echo
echo "===== 4. RESTART AUTONOMOUS ROUTER ====="
[ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null || true
pkill -f "skyscraper_gene_pool_router.py" 2>/dev/null || true
sleep 2

nohup "$STARTER" >> "$LOG" 2>&1 &
PID="$!"
echo "$PID" > "$PIDFILE"
echo "[OK] started pid=$PID"

echo
echo "===== 5. WAIT FOR DASHBOARD ====="
OK=NO
for i in $(seq 1 25); do
  if curl -sS --max-time 2 "http://127.0.0.1:$PORT/health" >/tmp/gene_pool_health.json 2>/dev/null; then
    OK=YES
    break
  fi
  sleep 1
done

if [ "$OK" != YES ]; then
  echo "[FAIL] dashboard did not come online"
  tail -n 160 "$LOG" || true
  cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
  exit 3
fi

echo "[OK] dashboard online"

echo
echo "===== 6. LET AUTONOMY RUN 12 SECONDS ====="
sleep 12

echo
echo "===== 7. SMOKE TEST HEALTH ====="
curl -sS --max-time 10 "http://127.0.0.1:$PORT/health" | python3 -m json.tool || true

echo
echo "===== 8. SMOKE TEST LIVE STATE ====="
curl -sS --max-time 20 "http://127.0.0.1:$PORT/api/live" > "$RUN_DIR/reports/live.json"
python3 - <<PYSHOW
import json
p="$RUN_DIR/reports/live.json"
d=json.load(open(p))
print("ok:", d.get("ok"))
m=d.get("metrics",{})
print("stored_key_count:", m.get("stored_key_count"))
print("active_provider_count:", m.get("active_provider_count"))
print("route_count:", m.get("autonomy",{}).get("route_count"))
print("last_scan:", m.get("autonomy",{}).get("last_scan"))
print("last_route:", m.get("autonomy",{}).get("last_route"))
print("events:", len(d.get("logs",[])))
for name,pv in (d.get("providers") or {}).items():
    print(f"{name:8s} keys={pv.get('key_count')} status={pv.get('status')}")
PYSHOW

echo
echo "===== 9. SECURE STORE CHECK ====="
echo "Secure key store exists:"
ls -l "$PROJECT/vaults/gene_pool/gene_pool_keys.secure.env" 2>/dev/null || true
echo
echo "Public masked store:"
ls -l "$PROJECT/data/registries/gene_pool_keys_public.json" 2>/dev/null || true
echo
echo "Public masked summary:"
python3 - <<PYPUB
import json, pathlib
p=pathlib.Path("$PROJECT/data/registries/gene_pool_keys_public.json")
if p.exists():
    d=json.loads(p.read_text())
    for name,pv in d.get("providers",{}).items():
        print(f"{name:8s} keys={pv.get('key_count')} status={pv.get('status')}")
else:
    print("missing")
PYPUB

echo
echo "===== 10. OPEN DASHBOARD ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
LOCAL="http://127.0.0.1:$PORT"
LAN="http://${LAN_IP:-127.0.0.1}:$PORT"
echo "Local: $LOCAL"
echo "LAN:   $LAN"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$LOCAL" >/dev/null 2>&1 || true
fi

echo
echo "===== 11. LOG TAIL ====="
tail -n 80 "$LOG" || true

echo
echo "============================================================"
echo "DONE — AUTONOMOUS GENE POOL ROUTER RUNNING"
echo "Open:"
echo "$LOCAL"
echo "$LAN"
echo
echo "Secure key store:"
echo "$PROJECT/vaults/gene_pool/gene_pool_keys.secure.env"
echo
echo "Masked public registry:"
echo "$PROJECT/data/registries/gene_pool_keys_public.json"
echo
echo "Report:"
echo "$REPORT"
echo
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$RUN_DIR/reports/live.json" "$SEND/live.json"
cp -a "$PROJECT/data/registries/gene_pool_keys_public.json" "$SEND/gene_pool_keys_public.json" 2>/dev/null || true
