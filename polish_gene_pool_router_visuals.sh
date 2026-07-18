#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
APP="$PROJECT/tools/skyscraper_gene_pool_router.py"
PORT="8860"
LOG="$PROJECT/logs/gene_pool_router_8860.log"
PIDFILE="$PROJECT/runtime/gene_pool_router_8860.pid"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_polish_gene_pool_visuals"
REPORT="$RUN_DIR/reports/polish_gene_pool_visuals_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$SEND"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — POLISH GENE POOL ROUTER VISUALS"
echo "Generated: $(date -Is)"
echo "Port: $PORT"
echo "============================================================"
echo "Rules:"
echo " - Visual polish only."
echo " - No API key changes."
echo " - No vault key rewrites."
echo " - No routing doctrine changes."
echo " - Claude HQ remains correct name."
echo " - Wren remains protected GPU guardian."
echo "============================================================"

cd "$PROJECT" || exit 1

if [ ! -f "$APP" ]; then
  echo "[FAIL] Missing app: $APP"
  exit 1
fi

cp -a "$APP" "$RUN_DIR/backups/skyscraper_gene_pool_router.py.bak_$STAMP"
echo "[OK] backup written"

echo
echo "===== 1. PATCH HTML / CSS / JS VISUALS ONLY ====="

python3 - <<'PY'
from pathlib import Path
import re

p = Path("/vaults/nvme0/qsb_tower_v1/tools/skyscraper_gene_pool_router.py")
s = p.read_text(errors="ignore")

start = s.find("HTML = r'''")
if start < 0:
    raise SystemExit("[FAIL] Could not find HTML = r''' block")

body_start = start + len("HTML = r'''")
end = s.find("'''", body_start)
if end < 0:
    raise SystemExit("[FAIL] Could not find end of HTML block")

new_html = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>SkyscraperHQ · Autonomous Brain Router Live Flow</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --bg:#020610;
  --panel:#071426;
  --panel2:#0c2035;
  --line:#1e4566;
  --text:#e8f7ff;
  --muted:#8ca9bd;
  --cyan:#42d9ff;
  --green:#45f59b;
  --amber:#ffc857;
  --red:#ff5d7d;
  --purple:#b987ff;
  --blue2:#2a8cff;
}
*{box-sizing:border-box}
body{
  margin:0;
  color:var(--text);
  font-family:system-ui,Segoe UI,Arial,sans-serif;
  overflow-x:hidden;
  background:
    radial-gradient(circle at 20% 0%,rgba(66,217,255,.18),transparent 28%),
    radial-gradient(circle at 85% 10%,rgba(185,135,255,.16),transparent 30%),
    radial-gradient(circle at 50% 0,#173655 0,#06101d 48%,#02050b 100%);
}
body:before{
  content:"";
  position:fixed;
  inset:0;
  pointer-events:none;
  opacity:.17;
  background-image:
    linear-gradient(rgba(66,217,255,.16) 1px, transparent 1px),
    linear-gradient(90deg, rgba(66,217,255,.16) 1px, transparent 1px);
  background-size:44px 44px;
  animation:gridDrift 18s linear infinite;
}
@keyframes gridDrift{to{background-position:44px 44px}}
header{
  padding:16px 20px;
  border-bottom:1px solid var(--line);
  background:rgba(0,0,0,.38);
  position:sticky;
  top:0;
  z-index:10;
  backdrop-filter:blur(12px);
}
h1{margin:0;font-size:24px;letter-spacing:.35px}
.sub{color:var(--muted);font-size:13px;margin-top:4px}
.main{display:grid;grid-template-columns:1.2fr .8fr;gap:14px;padding:14px}
.card{
  background:linear-gradient(180deg,rgba(13,32,54,.94),rgba(4,12,23,.94));
  border:1px solid var(--line);
  border-radius:20px;
  padding:14px;
  box-shadow:0 12px 38px rgba(0,0,0,.38), inset 0 0 32px rgba(66,217,255,.025);
}
.flow{height:650px;position:relative;overflow:hidden}
.flow:after{
  content:"";
  position:absolute;
  inset:0;
  pointer-events:none;
  background:radial-gradient(circle at 50% 50%,transparent 0,transparent 58%,rgba(2,6,16,.65) 100%);
}
.node{
  position:absolute;
  width:150px;
  height:78px;
  border:1px solid var(--line);
  border-radius:20px;
  background:linear-gradient(180deg,rgba(7,24,42,.94),rgba(2,9,18,.92));
  display:grid;
  place-items:center;
  text-align:center;
  box-shadow:0 0 22px rgba(66,217,255,.08), inset 0 0 18px rgba(255,255,255,.025);
  z-index:3;
  overflow:hidden;
}
.node:before{
  content:"";
  position:absolute;
  inset:-2px;
  border-radius:22px;
  opacity:.22;
  background:conic-gradient(from var(--a,0deg),transparent,var(--cyan),transparent 35%,transparent);
  animation:ring 4s linear infinite;
}
.node > *{position:relative;z-index:2}
.node b{display:block;font-size:15px}
.node small{color:var(--muted);font-size:11px}
@keyframes ring{to{--a:360deg}}
@property --a{syntax:"<angle>";initial-value:0deg;inherits:false}

.router{
  left:50%;
  top:270px;
  transform:translateX(-50%);
  width:190px;
  height:112px;
  border-color:var(--cyan);
  box-shadow:0 0 38px rgba(66,217,255,.36), inset 0 0 28px rgba(66,217,255,.08);
}
.router b{font-size:18px}
.router:after{
  content:"";
  position:absolute;
  width:78px;
  height:78px;
  border-radius:50%;
  border:2px dashed rgba(66,217,255,.45);
  animation:spin 7s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg)}}

.claude{left:34px;top:62px}
.ceo2{left:34px;top:276px}
.ceo3{left:34px;top:490px}
.wren{
  right:34px;
  bottom:28px;
  border-color:var(--green);
  box-shadow:0 0 30px rgba(69,245,155,.28), inset 0 0 24px rgba(69,245,155,.06);
}
.wren:before{background:conic-gradient(from var(--a,0deg),transparent,var(--green),transparent 35%,transparent)}
.provider{right:36px;width:148px;height:62px}
.p0{top:18px}.p1{top:88px}.p2{top:158px}.p3{top:228px}.p4{top:298px}.p5{top:368px}.p6{top:438px}.p7{top:508px}
.provider.active{
  border-color:var(--green);
  box-shadow:0 0 28px rgba(69,245,155,.28), inset 0 0 18px rgba(69,245,155,.06);
}
.provider.missing{
  border-color:rgba(255,93,125,.5);
  opacity:.72;
}
svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:1}
.line{
  stroke:#1d5f86;
  stroke-width:2;
  opacity:.45;
  stroke-dasharray:7 8;
  animation:dash 1.8s linear infinite;
}
.line.ceoline{stroke:rgba(66,217,255,.65)}
.line.providerline{stroke:rgba(185,135,255,.55)}
.line.wrenline{stroke:#246b49;opacity:.38}
@keyframes dash{to{stroke-dashoffset:-30}}
.hotbeam{
  stroke:var(--cyan);
  stroke-width:4;
  opacity:.95;
  filter:drop-shadow(0 0 8px var(--cyan));
  stroke-dasharray:12 10;
  animation:dash .9s linear infinite, fadeBeam 1.6s ease-out forwards;
}
@keyframes fadeBeam{to{opacity:0}}
.packet{
  position:absolute;
  width:12px;
  height:12px;
  border-radius:50%;
  background:var(--cyan);
  box-shadow:0 0 18px var(--cyan);
  opacity:0;
  z-index:6;
}
.packet:after{
  content:"";
  position:absolute;
  inset:-8px;
  border-radius:50%;
  border:1px solid rgba(66,217,255,.36);
}
.packet.go{animation:move 1.15s linear forwards}
@keyframes move{
  0%{opacity:0;transform:translate(var(--x1),var(--y1)) scale(.45)}
  12%{opacity:1}
  100%{opacity:0;transform:translate(var(--x2),var(--y2)) scale(1.25)}
}
.gauges{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.gauge{
  height:126px;
  display:grid;
  place-items:center;
  border-radius:18px;
  background:linear-gradient(180deg,#061426,#030a13);
  border:1px solid var(--line);
  position:relative;
  overflow:hidden;
}
.gauge:before{
  content:"";
  position:absolute;
  inset:0;
  background:linear-gradient(90deg,transparent,rgba(66,217,255,.07),transparent);
  animation:sweep 3s linear infinite;
}
@keyframes sweep{to{transform:translateX(100%)}}
.dial{
  width:88px;
  height:88px;
  border-radius:50%;
  background:conic-gradient(var(--green) calc(var(--v)*1%),#10263a 0);
  display:grid;
  place-items:center;
  transition:.45s;
  box-shadow:0 0 20px rgba(69,245,155,.14);
}
.dial:after{
  content:attr(data-v) '%';
  width:62px;
  height:62px;
  border-radius:50%;
  background:#061426;
  display:grid;
  place-items:center;
  font-weight:900;
}
.gauge span{position:absolute;bottom:9px;color:var(--muted);font-size:12px}
.statusgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.statusbox{
  background:#061426;
  border:1px solid var(--line);
  border-radius:16px;
  padding:10px;
  position:relative;
  overflow:hidden;
}
.statusbox:after{
  content:"";
  position:absolute;
  left:0;right:0;bottom:0;height:3px;
  background:linear-gradient(90deg,var(--cyan),var(--green));
  opacity:.8;
}
.big{font-size:28px;font-weight:900}
.providers{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.prov{
  padding:10px;
  border:1px solid var(--line);
  border-radius:16px;
  background:linear-gradient(180deg,#061426,#030a13);
  min-height:108px;
  position:relative;
  overflow:hidden;
}
.prov.ok{
  border-color:rgba(69,245,155,.75);
  box-shadow:0 0 14px rgba(69,245,155,.08);
}
.prov.bad{border-color:rgba(255,93,125,.55);opacity:.75}
.prov.ok:before{
  content:"";
  position:absolute;
  width:70px;
  height:70px;
  right:-28px;
  top:-28px;
  border-radius:50%;
  background:radial-gradient(circle,rgba(69,245,155,.30),transparent 70%);
}
.prov b{display:block}
.prov small{color:var(--muted)}
.stream{
  height:342px;
  overflow:auto;
  background:#040b14;
  border:1px solid var(--line);
  border-radius:16px;
  padding:10px;
  font-family:ui-monospace,monospace;
  font-size:12px;
}
.event{
  padding:7px;
  border-bottom:1px solid rgba(255,255,255,.05);
  animation:eventIn .35s ease-out;
}
@keyframes eventIn{from{opacity:0;transform:translateY(8px)}}
.ok{color:var(--green)}.warn{color:var(--amber)}.bad{color:var(--red)}
.pulse{
  display:inline-block;
  width:10px;
  height:10px;
  border-radius:50%;
  background:var(--green);
  box-shadow:0 0 16px var(--green);
  animation:pulse 1s infinite;
}
@keyframes pulse{50%{opacity:.25;transform:scale(.65)}}
.ticker{
  position:fixed;
  left:0;
  right:0;
  bottom:0;
  z-index:20;
  background:rgba(0,0,0,.62);
  border-top:1px solid var(--line);
  color:var(--cyan);
  font-family:ui-monospace,monospace;
  white-space:nowrap;
  overflow:hidden;
  height:28px;
  display:flex;
  align-items:center;
}
.ticker span{
  display:inline-block;
  padding-left:100%;
  animation:ticker 28s linear infinite;
}
@keyframes ticker{to{transform:translateX(-100%)}}
@media(max-width:1050px){
  .main{grid-template-columns:1fr}
  .providers,.gauges,.statusgrid{grid-template-columns:repeat(2,1fr)}
}
</style>
</head>
<body>
<header>
<h1>🧠 SkyscraperHQ Autonomous Brain Router · Live API Gene Pool <span class="pulse"></span></h1>
<div class="sub">Autonomous visual control room. Linux/vault scan and CEO routing run by themselves. Wren/GPU protected. CEOs use API Gene Pool only.</div>
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
<h3>Autonomy state</h3>
<div class="stream" id="statebox">Loading...</div>
</section>
</div>

<div class="main">
<section class="card"><h3>API Gene Pool</h3><div class="providers" id="providers"></div></section>
<section class="card"><h3>Rolling live flow graph</h3><div class="stream" id="stream"></div></section>
</div>

<div class="ticker"><span id="tickerText">SkyscraperHQ Brain Router online · Claude HQ active identity · Wren protected · CEOs API Gene Pool only · waiting for live events...</span></div>

<script>
const $=q=>document.querySelector(q);
let lastSeen=0;
let previousProvider=null;

function centre(el){
  const f=$("#flow").getBoundingClientRect(),r=el.getBoundingClientRect();
  return{x:r.left-f.left+r.width/2,y:r.top-f.top+r.height/2};
}
function lineBetween(a,b,cls){
  const l=document.createElementNS("http://www.w3.org/2000/svg","line");
  l.setAttribute("x1",a.x);l.setAttribute("y1",a.y);l.setAttribute("x2",b.x);l.setAttribute("y2",b.y);
  l.setAttribute("class",cls);
  return l;
}
function drawWires(){
  const svg=$("#wires");svg.innerHTML="";
  const router=centre($('[data-node="Brain Router"]'));
  [...document.querySelectorAll(".claude,.ceo2,.ceo3")].forEach(n=>svg.appendChild(lineBetween(centre(n),router,"line ceoline")));
  [...document.querySelectorAll(".provider")].forEach(n=>svg.appendChild(lineBetween(centre(n),router,"line providerline")));
  svg.appendChild(lineBetween(centre($('[data-node="Wren"]')),router,"line wrenline"));
}
function hotBeam(aSel,bSel){
  const a=$(aSel),b=$(bSel);if(!a||!b)return;
  const svg=$("#wires");
  const l=lineBetween(centre(a),centre(b),"hotbeam");
  svg.appendChild(l);
  setTimeout(()=>l.remove(),1700);
}
function packet(aSel,bSel,color){
  const aEl=$(aSel),bEl=$(bSel);if(!aEl||!bEl)return;
  hotBeam(aSel,bSel);
  const a=centre(aEl),b=centre(bEl);
  for(let i=0;i<3;i++){
    const p=document.createElement("div");
    p.className="packet";
    if(color){p.style.background=color;p.style.boxShadow=`0 0 18px ${color}`;}
    p.style.setProperty("--x1",(a.x-5)+"px");p.style.setProperty("--y1",(a.y-5)+"px");
    p.style.setProperty("--x2",(b.x-5)+"px");p.style.setProperty("--y2",(b.y-5)+"px");
    $("#flow").appendChild(p);
    setTimeout(()=>p.classList.add("go"),20+i*120);
    setTimeout(()=>p.remove(),1700+i*120);
  }
}
function ceoSel(n){return n==="Claude HQ"?".claude":n==="CEO 2"?".ceo2":".ceo3";}
function provSel(p){return `[data-provider="${p}"]`;}
function setGauge(id,v){v=Math.max(0,Math.min(100,Math.round(v||0)));const e=$(id);e.style.setProperty("--v",v);e.setAttribute("data-v",v);}
async function getJSON(u){const r=await fetch(u);return await r.json();}
function renderProviders(ps){
  $(".provider.active")?.classList.remove("active");
  document.querySelectorAll(".provider").forEach(n=>n.classList.remove("missing"));
  $("#providers").innerHTML=Object.values(ps||{}).map(p=>{
    const ok=(p.key_count||0)>0;
    const node=document.querySelector(`[data-provider="${p.provider}"]`);
    if(node){
      if(ok) node.classList.add("active");
      else node.classList.add("missing");
    }
    return `<div class="prov ${ok?'ok':'bad'}">
      <b>${p.label}</b>
      <small>${p.role}</small><br>
      <small>keys: ${p.key_count||0} · ${p.tier}</small><br>
      <small>${(p.keys||[]).slice(0,1).map(k=>k.masked+" · "+k.fingerprint).join("")}</small>
    </div>`;
  }).join("");
}
function renderEvents(logs){
  $("#stream").innerHTML=(logs||[]).slice(-90).reverse().map(e=>{
    const cls=e.status==="blocked"||e.status==="error"?"bad":e.status==="selected"||e.status==="stored"?"ok":"warn";
    return `<div class="event"><span class="${cls}">●</span> ${e.ts||""}<br>${e.from||"?"} → ${e.to||"?"} · ${e.provider||""} · ${e.task||""}<br><small>${e.detail||""}</small></div>`;
  }).join("");
}
function animate(e){
  if(!e)return;
  if(e.event==="request")packet(ceoSel(e.from),'[data-node="Brain Router"]',"#42d9ff");
  if(e.event==="dispatch"&&e.provider&&e.provider!=="none"){
    previousProvider=e.provider;
    packet('[data-node="Brain Router"]',provSel(e.provider),"#b987ff");
  }
  if(e.event==="return"&&e.provider&&e.provider!=="none"){
    packet(provSel(e.provider),'[data-node="Brain Router"]',"#45f59b");
    setTimeout(()=>packet('[data-node="Brain Router"]',ceoSel(e.to),"#45f59b"),500);
  }
  if(e.event==="auto_scan")packet('[data-node="Wren"]','[data-node="Brain Router"]',"#45f59b");
}
async function live(){
  const d=await getJSON("/api/live");
  const m=d.metrics||{},rev=m.rev||{};
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
  const active=m.active||{};
  $("#tickerText").textContent=`SkyscraperHQ live · ${active.from||"Brain Router"} → ${active.to||"API Gene Pool"} · provider ${active.provider||"scanning"} · task ${active.task||"autonomy"} · Wren protected · CEOs API Gene Pool only · routes ${(m.autonomy&&m.autonomy.route_count)||0}`;
  const logs=d.logs||[];
  if(logs.length>lastSeen){
    logs.slice(lastSeen).forEach((e,i)=>setTimeout(()=>animate(e),i*180));
    lastSeen=logs.length;
  }
}
drawWires();
window.addEventListener("resize",drawWires);
live();
setInterval(live,1150);
</script>
</body>
</html>'''

s = s[:body_start] + new_html + s[end:]
p.write_text(s, encoding="utf-8")
print("[OK] HTML visual block replaced")
PY

echo
echo "===== 2. COMPILE ====="
python3 -m py_compile "$APP" && echo "[OK] app compiles" || exit 2

echo
echo "===== 3. RESTART ROUTER ====="
[ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null || true
pkill -f "skyscraper_gene_pool_router.py" 2>/dev/null || true
sleep 2

nohup "$PROJECT/run_gene_pool_router.sh" >> "$LOG" 2>&1 &
PID="$!"
echo "$PID" > "$PIDFILE"
echo "[OK] started pid=$PID"

echo
echo "===== 4. WAIT FOR DASHBOARD ====="
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
echo "===== 5. SMOKE CHECK ====="
curl -sS --max-time 10 "http://127.0.0.1:$PORT/health" | python3 -m json.tool || true
curl -sS --max-time 20 "http://127.0.0.1:$PORT/api/live" > "$RUN_DIR/reports/live.json"

python3 - <<PYSHOW
import json
d=json.load(open("$RUN_DIR/reports/live.json"))
m=d.get("metrics",{})
print("ok:", d.get("ok"))
print("stored_key_count:", m.get("stored_key_count"))
print("active_provider_count:", m.get("active_provider_count"))
print("route_count:", m.get("autonomy",{}).get("route_count"))
print("events:", len(d.get("logs",[])))
print("")
for name,pv in (d.get("providers") or {}).items():
    print(f"{name:8s} keys={pv.get('key_count')} status={pv.get('status')}")
PYSHOW

echo
echo "===== 6. OPEN ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Local: http://127.0.0.1:$PORT"
echo "LAN:   http://${LAN_IP:-127.0.0.1}:$PORT"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1 || true
fi

echo
echo "============================================================"
echo "DONE — VISUALS POLISHED"
echo "Open:"
echo "http://127.0.0.1:$PORT"
echo "http://${LAN_IP:-127.0.0.1}:$PORT"
echo
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$RUN_DIR/reports/live.json" "$SEND/live.json"
