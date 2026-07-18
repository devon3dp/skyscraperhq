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
RUN_DIR="$RUN_ROOT/${STAMP}_animated_gene_pool_router"
REPORT="$RUN_DIR/reports/animated_gene_pool_router_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$PROJECT/tools" "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries" "$SEND"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — ANIMATED BRAIN ROUTER GENE POOL DASHBOARD"
echo "Generated: $(date -Is)"
echo "Port: $PORT"
echo "Rules:"
echo " - Claude HQ is the correct name."
echo " - Wren owns/protects the GPU."
echo " - CEOs use API Gene Pool only."
echo " - No CEO local model fallback."
echo " - This is visual/control-room mode; it does not rewrite vault keys."
echo "============================================================"

cd "$PROJECT" || exit 1

[ -f "$APP" ] && cp -a "$APP" "$RUN_DIR/backups/skyscraper_gene_pool_router.py.bak_$STAMP"
[ -f "$STARTER" ] && cp -a "$STARTER" "$RUN_DIR/backups/run_gene_pool_router.sh.bak_$STAMP"

echo
echo "===== 1. WRITE ANIMATED DASH APP ====="

cat > "$APP" <<'PY'
#!/usr/bin/env python3
import os, re, json, time, hashlib, random, socket
from pathlib import Path
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PROJECT = Path("/vaults/nvme0/qsb_tower_v1")
PORT = int(os.environ.get("GENE_POOL_ROUTER_PORT", "8860"))
HOST = os.environ.get("GENE_POOL_ROUTER_HOST", "0.0.0.0")
DATA = PROJECT / "data" / "registries"
LOG = DATA / "skyscraper_gene_pool_router_calls.jsonl"
STATE = DATA / "skyscraper_gene_pool_router_state.json"

PROVIDERS = {
    "claude":   {"label":"Claude",      "patterns":[r"sk-ant-[A-Za-z0-9_\-]{20,}"], "env":["ANTHROPIC_API_KEY","CLAUDE_API_KEY"], "tier":"premium", "role":"deep reasoning / Claude HQ preferred"},
    "openai":   {"label":"OpenAI",      "patterns":[r"sk-proj-[A-Za-z0-9_\-]{20,}", r"sk-[A-Za-z0-9_\-]{32,}"], "env":["OPENAI_API_KEY"], "tier":"medium", "role":"structured reasoning / planning"},
    "deepseek": {"label":"DeepSeek",    "patterns":[r"sk-[A-Za-z0-9_\-]{32,}"], "env":["DEEPSEEK_API_KEY"], "tier":"low", "role":"coding / cheap reasoning"},
    "gemini":   {"label":"Gemini",      "patterns":[r"AIza[A-Za-z0-9_\-]{20,}"], "env":["GEMINI_API_KEY","GOOGLE_API_KEY"], "tier":"low-medium", "role":"long context / broad reasoning"},
    "cohere":   {"label":"Cohere",      "patterns":[r"[A-Za-z0-9_\-]{40,}"], "env":["COHERE_API_KEY"], "tier":"low-medium", "role":"retrieval / ranking / summaries"},
    "kimi":     {"label":"Kimi",        "patterns":[r"sk-[A-Za-z0-9_\-]{32,}"], "env":["KIMI_API_KEY","MOONSHOT_API_KEY"], "tier":"low-medium", "role":"long document reasoning"},
    "grok":     {"label":"Grok / xAI",   "patterns":[r"xai-[A-Za-z0-9_\-]{20,}", r"sk-[A-Za-z0-9_\-]{32,}"], "env":["GROK_API_KEY","XAI_API_KEY"], "tier":"medium", "role":"alternate reasoning perspective"},
    "groq":     {"label":"Groq",        "patterns":[r"gsk_[A-Za-z0-9_\-]{20,}"], "env":["GROQ_API_KEY"], "tier":"low", "role":"fast hosted inference"},
}

ROOTS = [
    Path("/home/ross/.skyscraper_secrets"),
    Path("/home/ross/.claude"),
    PROJECT / "vaults",
    PROJECT / "floors",
    PROJECT / "config",
    PROJECT / "data",
]
SKIP = {".git",".venv","venv","node_modules","__pycache__",".cache","cache","models","ollama","huggingface","external_oss"}

POLICY = {
    "architecture": ["claude","openai","kimi","gemini","deepseek","grok","groq","cohere"],
    "coding":       ["deepseek","openai","claude","kimi","groq","gemini","grok","cohere"],
    "summary":      ["cohere","gemini","kimi","openai","deepseek","groq","claude","grok"],
    "cheap":        ["groq","deepseek","gemini","cohere","kimi","openai","claude","grok"],
    "default":      ["openai","deepseek","kimi","gemini","claude","groq","grok","cohere"],
}

LAST_SCAN = {}
LAST_EVENTS = []
BOOT_TS = time.time()

def now():
    return datetime.now(timezone.utc).isoformat()

def fp(s):
    return hashlib.sha256(s.encode()).hexdigest()[:16]

def mask(k):
    return k[:10] + "..." + k[-7:] if len(k) > 20 else k[:4] + "..." + k[-4:]

def log_event(obj):
    DATA.mkdir(parents=True, exist_ok=True)
    obj["ts"] = now()
    LAST_EVENTS.append(obj)
    del LAST_EVENTS[:-80]
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def public_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"

def scan_keys(max_files=40000):
    out = {k: {"provider":k, "label":v["label"], "role":v["role"], "tier":v["tier"], "key_count":0, "keys":[], "status":"unknown"} for k,v in PROVIDERS.items()}
    seen = {k:{} for k in PROVIDERS}

    for provider,cfg in PROVIDERS.items():
        for e in cfg["env"]:
            val = os.environ.get(e,"").strip()
            if val:
                seen[provider].setdefault(val,set()).add("process_env:"+e)

    files = 0
    for root in ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if files >= max_files:
                break
            try:
                if not p.is_file() or p.stat().st_size > 2500000:
                    continue
                if any(x in SKIP for x in p.parts):
                    continue
                low = str(p).lower()
                if not any(x in low for x in ["env","key","token","secret","vault","credential","claude","openai","deepseek","gemini","cohere","kimi","moonshot","grok","groq","xai"]):
                    continue
                txt = p.read_text(errors="ignore")
                files += 1
            except Exception:
                continue

            for provider,cfg in PROVIDERS.items():
                low_txt = txt[:3000].lower()
                if provider not in low and provider not in low_txt and cfg["label"].lower().split()[0] not in low_txt:
                    continue

                for e in cfg["env"]:
                    rx = re.compile(rf"(?:export\s+)?{re.escape(e)}\s*=\s*['\"]?([^'\"\n\r #]+)", re.I)
                    for m in rx.finditer(txt):
                        seen[provider].setdefault(m.group(1),set()).add(str(p)+":"+e)

                for pat in cfg["patterns"]:
                    for m in re.finditer(pat, txt):
                        seen[provider].setdefault(m.group(0),set()).add(str(p))

    for provider, keymap in seen.items():
        keys = []
        for key, sources in keymap.items():
            keys.append({"masked":mask(key), "fingerprint":fp(key), "sources":sorted(sources)[:6]})
        out[provider]["keys"] = keys
        out[provider]["key_count"] = len(keys)
        out[provider]["status"] = "key_found" if keys else "missing"
    global LAST_SCAN
    LAST_SCAN = out
    STATE.write_text(json.dumps({"ts":now(),"providers":out}, indent=2), encoding="utf-8")
    log_event({"event":"scan","from":"Vault","to":"Brain Router","provider":"all","status":"ok","detail":f"providers scanned; files limited to {max_files}"})
    return out

def classify(prompt, explicit=None):
    if explicit in POLICY:
        return explicit
    s=(prompt or "").lower()
    if any(x in s for x in ["code","script","python","bash","bug","traceback","patch","compile"]): return "coding"
    if any(x in s for x in ["architecture","router","kernel","system","ceo","strategy","design"]): return "architecture"
    if any(x in s for x in ["summarise","summarize","recap","report"]): return "summary"
    if any(x in s for x in ["cheap","fast","quick"]): return "cheap"
    return "default"

def choose(task):
    if not LAST_SCAN:
        scan_keys(max_files=25000)
    for p in POLICY.get(task, POLICY["default"]):
        if LAST_SCAN.get(p,{}).get("key_count",0) > 0:
            return p
    return None

def route(body):
    ceo = body.get("ceo") or "Claude HQ"
    prompt = body.get("prompt") or body.get("text") or body.get("message") or ""
    task = classify(prompt, body.get("task_type") or body.get("task"))
    provider = choose(task)
    if not provider:
        ev={"event":"route","from":ceo,"to":"Brain Router","provider":"none","status":"blocked","task":task,"detail":"no API Gene Pool key found"}
        log_event(ev)
        return {"ok":False, "route":ev, "answer":"No API Gene Pool provider key found. CEOs do not fall back to Wren/local GPU."}
    label = PROVIDERS[provider]["label"]
    ev1={"event":"route","from":ceo,"to":"Brain Router","provider":provider,"status":"received","task":task,"detail":"CEO request entered Brain Router"}
    ev2={"event":"dispatch","from":"Brain Router","to":label,"provider":provider,"status":"selected","task":task,"detail":"selected from API Gene Pool by policy"}
    ev3={"event":"return","from":label,"to":ceo,"provider":provider,"status":"visual_only","task":task,"detail":"visual route complete; model call wiring comes next"}
    log_event(ev1); log_event(ev2); log_event(ev3)
    return {
        "ok":True,
        "ceo":ceo,
        "task":task,
        "selected_provider":provider,
        "selected_label":label,
        "doctrine":"CEOs use API Gene Pool only. Wren/GPU is protected and separate.",
        "answer":"VISUAL_ROUTE_OK: connection animated from CEO to Brain Router to API Gene Pool and back."
    }

def recent_logs(limit=70):
    if LOG.exists():
        rows=[]
        for line in LOG.read_text(errors="ignore").splitlines()[-limit:]:
            try: rows.append(json.loads(line))
            except Exception: pass
        return rows
    return LAST_EVENTS[-limit:]

def metrics():
    logs = recent_logs(120)
    counts = {}
    for e in logs:
        p=e.get("provider","unknown")
        counts[p]=counts.get(p,0)+1
    active = logs[-1] if logs else {}
    uptime = int(time.time()-BOOT_TS)
    return {
        "uptime_s": uptime,
        "events": len(logs),
        "provider_counts": counts,
        "active": active,
        "rev": {
            "router": min(100, 18 + len(logs)*3),
            "api_pool": min(100, 12 + len([x for x in LAST_SCAN.values() if x.get("key_count",0)>0])*11),
            "ceo_load": random.randint(18,76),
            "wren_guard": 100
        }
    }

HTML = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>SkyscraperHQ · Brain Router Live Flow</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#030711;--panel:#071426;--panel2:#0d2036;--line:#1e4566;--text:#e8f7ff;--muted:#8ca9bd;--cyan:#42d9ff;--green:#45f59b;--amber:#ffc857;--red:#ff5d7d;--purple:#b987ff}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at 50% 0,#123251 0,#06101d 45%,#02050b 100%);color:var(--text);font-family:system-ui,Segoe UI,Arial,sans-serif;overflow-x:hidden}
header{padding:16px 20px;border-bottom:1px solid var(--line);background:rgba(0,0,0,.35);backdrop-filter:blur(10px);position:sticky;top:0;z-index:5}
h1{margin:0;font-size:24px;letter-spacing:.3px}.sub{color:var(--muted);font-size:13px;margin-top:4px}
.main{display:grid;grid-template-columns:1.15fr .85fr;gap:14px;padding:14px}
.card{background:linear-gradient(180deg,rgba(13,32,54,.94),rgba(4,12,23,.94));border:1px solid var(--line);border-radius:18px;padding:14px;box-shadow:0 12px 34px rgba(0,0,0,.34)}
.flow{height:560px;position:relative;overflow:hidden}
.node{position:absolute;width:140px;height:74px;border:1px solid var(--line);border-radius:18px;background:rgba(5,18,32,.86);display:grid;place-items:center;text-align:center;box-shadow:0 0 22px rgba(66,217,255,.08)}
.node b{display:block}.node small{color:var(--muted)}
.router{left:50%;top:235px;transform:translateX(-50%);width:170px;height:95px;border-color:var(--cyan);box-shadow:0 0 28px rgba(66,217,255,.22)}
.claude{left:36px;top:52px}.ceo2{left:36px;top:226px}.ceo3{left:36px;top:400px}
.wren{right:32px;bottom:30px;border-color:var(--green);box-shadow:0 0 24px rgba(69,245,155,.18)}
.provider{right:36px;width:136px;height:62px}.p0{top:26px}.p1{top:94px}.p2{top:162px}.p3{top:230px}.p4{top:298px}.p5{top:366px}.p6{top:434px}.p7{top:502px}
svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.line{stroke:#1d5f86;stroke-width:2;opacity:.55;stroke-dasharray:7 8;animation:dash 1.8s linear infinite}
.line.hot{stroke:var(--cyan);stroke-width:3;opacity:.95;filter:drop-shadow(0 0 6px var(--cyan))}
@keyframes dash{to{stroke-dashoffset:-30}}
.packet{position:absolute;width:10px;height:10px;border-radius:50%;background:var(--cyan);box-shadow:0 0 16px var(--cyan);opacity:0;z-index:4}
.packet.go{animation:move 1.2s linear forwards}
@keyframes move{0%{opacity:0;transform:translate(var(--x1),var(--y1)) scale(.6)}12%{opacity:1}100%{opacity:0;transform:translate(var(--x2),var(--y2)) scale(1.2)}}
.controls{display:grid;grid-template-columns:1fr 1fr;gap:10px}
button,select,input,textarea{background:#061426;color:var(--text);border:1px solid var(--line);border-radius:12px;padding:10px}
button{cursor:pointer;font-weight:800;background:#12385a}button:hover{background:#18507e}
textarea{height:92px;grid-column:1/-1}
.gauges{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.gauge{height:118px;display:grid;place-items:center;border-radius:16px;background:#061426;border:1px solid var(--line);position:relative}
.dial{width:82px;height:82px;border-radius:50%;background:conic-gradient(var(--green) calc(var(--v)*1%),#10263a 0);display:grid;place-items:center}
.dial:after{content:attr(data-v) '%';width:58px;height:58px;border-radius:50%;background:#061426;display:grid;place-items:center;font-weight:900}
.gauge span{position:absolute;bottom:9px;color:var(--muted);font-size:12px}
.providers{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.prov{padding:10px;border:1px solid var(--line);border-radius:14px;background:#061426;min-height:92px}
.prov.ok{border-color:rgba(69,245,155,.7)}.prov.bad{border-color:rgba(255,93,125,.6)}
.prov b{display:block}.prov small{color:var(--muted)}
.stream{height:260px;overflow:auto;background:#040b14;border:1px solid var(--line);border-radius:14px;padding:10px;font-family:ui-monospace,monospace;font-size:12px}
.event{padding:5px;border-bottom:1px solid rgba(255,255,255,.05)}.event .ok{color:var(--green)}.event .warn{color:var(--amber)}.event .bad{color:var(--red)}
pre{white-space:pre-wrap;word-break:break-word;background:#040b14;border:1px solid var(--line);border-radius:14px;padding:10px;max-height:220px;overflow:auto}
@media(max-width:1050px){.main{grid-template-columns:1fr}.providers,.gauges{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<header>
<h1>🧠 SkyscraperHQ Brain Router · Live API Gene Pool Flow</h1>
<div class="sub">Claude HQ + CEOs → Brain Router → API Gene Pool. Wren/GPU protected. No CEO local fallback.</div>
</header>

<div class="main">
  <section class="card flow" id="flow">
    <svg id="wires"></svg>
    <div class="node claude" data-node="Claude HQ"><b>Claude HQ</b><small>CEO identity</small></div>
    <div class="node ceo2" data-node="CEO 2"><b>CEO 2</b><small>API only</small></div>
    <div class="node ceo3" data-node="CEO 3"><b>CEO 3</b><small>API only</small></div>
    <div class="node router" data-node="Brain Router"><b>Brain Router</b><small>gene selector</small></div>
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
    <div class="controls">
      <button onclick="scan()">Scan vault</button>
      <button onclick="fireVisual()">Fire visual route</button>
      <select id="ceo"><option>Claude HQ</option><option>CEO 2</option><option>CEO 3</option></select>
      <select id="task"><option>architecture</option><option>coding</option><option>summary</option><option>cheap</option><option>default</option></select>
      <textarea id="prompt">Show the Brain Router choosing the best API Gene Pool provider for this CEO request.</textarea>
    </div>
    <br>
    <h3>Route result</h3>
    <pre id="result">Waiting.</pre>
  </section>
</div>

<div class="main">
  <section class="card">
    <h3>API Gene Pool</h3>
    <div class="providers" id="providers"></div>
  </section>
  <section class="card">
    <h3>Rolling live stream</h3>
    <div class="stream" id="stream"></div>
  </section>
</div>

<script>
const $=q=>document.querySelector(q);
let lastEventCount=0;

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
}
function packet(fromSel,toSel){
  const a=centre($(fromSel)), b=centre($(toSel));
  const p=document.createElement("div");
  p.className="packet";
  p.style.setProperty("--x1",(a.x-5)+"px"); p.style.setProperty("--y1",(a.y-5)+"px");
  p.style.setProperty("--x2",(b.x-5)+"px"); p.style.setProperty("--y2",(b.y-5)+"px");
  $("#flow").appendChild(p);
  setTimeout(()=>p.classList.add("go"),20);
  setTimeout(()=>p.remove(),1500);
}
function providerSel(p){ return `[data-provider="${p}"]`; }
function setGauge(id,v){ v=Math.max(0,Math.min(100,Math.round(v||0))); const e=$(id); e.style.setProperty("--v",v); e.setAttribute("data-v",v); }

async function getJSON(url){ const r=await fetch(url); return await r.json(); }
async function postJSON(url,obj){ const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(obj)}); return await r.json(); }

async function scan(){
  $("#result").textContent="Scanning vault...";
  const d=await getJSON("/api/providers");
  renderProviders(d.providers||{});
  $("#result").textContent=JSON.stringify({ok:true, scan:"complete"},null,2);
  await live();
}
function renderProviders(ps){
  $("#providers").innerHTML=Object.values(ps).map(p=>{
    const ok=p.key_count>0;
    return `<div class="prov ${ok?'ok':'bad'}"><b>${p.label}</b><small>${p.role}</small><br><small>keys: ${p.key_count} · ${p.tier}</small><br><small>${(p.keys||[]).slice(0,1).map(k=>k.masked+" · "+k.fingerprint).join("")}</small></div>`;
  }).join("");
}
async function fireVisual(){
  const body={ceo:$("#ceo").value,task_type:$("#task").value,prompt:$("#prompt").value};
  packet(`.${body.ceo==="Claude HQ"?"claude":body.ceo==="CEO 2"?"ceo2":"ceo3"}`,'[data-node="Brain Router"]');
  const d=await postJSON("/api/route",body);
  $("#result").textContent=JSON.stringify(d,null,2);
  if(d.selected_provider){
    setTimeout(()=>packet('[data-node="Brain Router"]',providerSel(d.selected_provider)),350);
    setTimeout(()=>packet(providerSel(d.selected_provider),'[data-node="Brain Router"]'),900);
    setTimeout(()=>packet('[data-node="Brain Router"]',`.${body.ceo==="Claude HQ"?"claude":body.ceo==="CEO 2"?"ceo2":"ceo3"}`),1300);
  }
  await live();
}
async function live(){
  const d=await getJSON("/api/live");
  setGauge("#g_router",d.metrics.rev.router);
  setGauge("#g_pool",d.metrics.rev.api_pool);
  setGauge("#g_ceo",d.metrics.rev.ceo_load);
  setGauge("#g_wren",d.metrics.rev.wren_guard);
  const logs=d.logs||[];
  $("#stream").innerHTML=logs.slice(-50).reverse().map(e=>{
    const cls=e.status==="blocked"?"bad":e.status==="selected"?"ok":"warn";
    return `<div class="event"><span class="${cls}">●</span> ${e.ts||""}<br>${e.from||"?"} → ${e.to||"?"} · ${e.provider||""} · ${e.task||""}<br><small>${e.detail||""}</small></div>`;
  }).join("");
  if(logs.length>lastEventCount){
    const e=logs[logs.length-1];
    if(e && e.provider && e.provider!=="all" && e.provider!=="none" && document.querySelector(providerSel(e.provider))){
      packet('[data-node="Brain Router"]', providerSel(e.provider));
    }
    lastEventCount=logs.length;
  }
}
drawWires();
window.addEventListener("resize",drawWires);
scan();
setInterval(live,1800);
</script>
</body>
</html>'''

def send_json(h, obj, status=200):
    raw=json.dumps(obj, indent=2, ensure_ascii=False).encode()
    h.send_response(status)
    h.send_header("Content-Type","application/json; charset=utf-8")
    h.send_header("Access-Control-Allow-Origin","*")
    h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
    h.send_header("Access-Control-Allow-Headers","Content-Type")
    h.send_header("Content-Length",str(len(raw)))
    h.end_headers()
    h.wfile.write(raw)

def send_html(h):
    raw=HTML.encode()
    h.send_response(200)
    h.send_header("Content-Type","text/html; charset=utf-8")
    h.send_header("Access-Control-Allow-Origin","*")
    h.send_header("Content-Length",str(len(raw)))
    h.end_headers()
    h.wfile.write(raw)

def body(h):
    n=int(h.headers.get("Content-Length","0") or 0)
    if not n: return {}
    try: return json.loads(h.rfile.read(n).decode())
    except Exception: return {}

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.end_headers()
    def do_GET(self):
        p=urlparse(self.path).path
        if p in ["/","/dashboard"]: return send_html(self)
        if p=="/health": return send_json(self,{"ok":True,"service":"animated_gene_pool_router","port":PORT,"wren":"protected","ceos":"api_gene_pool_only","ts":now()})
        if p=="/api/providers": return send_json(self,{"ok":True,"providers":scan_keys()})
        if p=="/api/live": return send_json(self,{"ok":True,"metrics":metrics(),"logs":recent_logs(80),"providers":LAST_SCAN})
        if p=="/api/logs": return send_json(self,{"ok":True,"logs":recent_logs(120)})
        return send_json(self,{"ok":False,"error":"not found","path":p},404)
    def do_POST(self):
        p=urlparse(self.path).path
        if p=="/api/route": return send_json(self,route(body(self)))
        if p=="/api/seed":
            log_event({"event":"seed","from":"Claude HQ","to":"Brain Router","provider":"openai","status":"selected","task":"architecture","detail":"manual seed visual event"})
            return send_json(self,{"ok":True})
        return send_json(self,{"ok":False,"error":"not found","path":p},404)

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    print(f"[BOOT] animated Gene Pool Router on {HOST}:{PORT}", flush=True)
    print("[BOOT] Wren/GPU protected. CEOs use API Gene Pool only.", flush=True)
    print(f"[READY] http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer((HOST,PORT),H).serve_forever()

if __name__=="__main__":
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
mkdir -p "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries"
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
echo "===== 4. RESTART PORT $PORT ====="
[ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null || true
pkill -f "skyscraper_gene_pool_router.py" 2>/dev/null || true
sleep 2

nohup "$STARTER" >> "$LOG" 2>&1 &
PID="$!"
echo "$PID" > "$PIDFILE"
echo "[OK] started pid=$PID"

echo
echo "===== 5. WAIT FOR DASH ====="
OK=NO
for i in $(seq 1 20); do
  if curl -sS --max-time 2 "http://127.0.0.1:$PORT/health" >/tmp/gene_pool_health.json 2>/dev/null; then
    OK=YES
    break
  fi
  sleep 1
done

if [ "$OK" != YES ]; then
  echo "[FAIL] dashboard did not come online"
  tail -n 120 "$LOG" || true
  cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
  exit 3
fi

echo "[OK] online"

echo
echo "===== 6. SMOKE TESTS ====="
echo "--- health"
curl -sS --max-time 10 "http://127.0.0.1:$PORT/health" | python3 -m json.tool || true

echo
echo "--- visual route"
curl -sS --max-time 20 \
  -H 'Content-Type: application/json' \
  -d '{"ceo":"Claude HQ","task_type":"architecture","prompt":"Animate Claude HQ through the Brain Router to the API Gene Pool."}' \
  "http://127.0.0.1:$PORT/api/route" > "$RUN_DIR/reports/visual_route.json"
python3 -m json.tool "$RUN_DIR/reports/visual_route.json" || cat "$RUN_DIR/reports/visual_route.json"

echo
echo "--- live"
curl -sS --max-time 20 "http://127.0.0.1:$PORT/api/live" > "$RUN_DIR/reports/live.json"
python3 - <<PYSHOW
import json
p="$RUN_DIR/reports/live.json"
d=json.load(open(p))
print("ok:", d.get("ok"))
print("events:", len(d.get("logs",[])))
print("active:", d.get("metrics",{}).get("active",{}))
print("rev:", d.get("metrics",{}).get("rev",{}))
PYSHOW

echo
echo "===== 7. OPEN DASHBOARD ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
LOCAL="http://127.0.0.1:$PORT"
LAN="http://${LAN_IP:-127.0.0.1}:$PORT"
echo "Local: $LOCAL"
echo "LAN:   $LAN"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$LOCAL" >/dev/null 2>&1 || true
fi

echo
echo "===== 8. LOG TAIL ====="
tail -n 60 "$LOG" || true

echo
echo "============================================================"
echo "DONE — ANIMATED DASHBOARD DEPLOYED"
echo "Open:"
echo "$LOCAL"
echo "$LAN"
echo
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$RUN_DIR/reports/visual_route.json" "$SEND/visual_route.json"
cp -a "$RUN_DIR/reports/live.json" "$SEND/live.json"
