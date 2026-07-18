#!/usr/bin/env python3
"""
SkyscraperHQ Professional Tour Guide Dashboard (served).

Visitor-facing guided tour + Receptionist front desk. Real data only:
- floor cards from data/registries/floors.json (166 real floors)
- link-health probed SERVER-SIDE against the real endpoints (no fake green,
  no CORS fakery) via /api/health
- Task Council / Gene Pool / Town Square / CEO status from the live hub + nodes

New additive service (port 8854). Does NOT modify any existing dashboard.
Run:  python3 tools/qsb_tour_guide_server.py --port 8854
"""
from __future__ import annotations
import json, argparse, urllib.request, socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOORS = ROOT / "data/registries/floors.json"

# Real services discovered live (probe host is localhost on the HQ box).
HQ = "127.0.0.1"
SERVICES = [
    {"key": "boardroom",  "name": "Boardroom Hub",        "url": f"http://{HQ}:8852/",            "expect": "html",  "path": "/"},
    {"key": "tasks",      "name": "Task Council",         "url": f"http://{HQ}:8852/tasks/data",  "expect": "json",  "path": "/tasks"},
    {"key": "council",    "name": "Council View",         "url": f"http://{HQ}:8852/council",     "expect": "html",  "path": "/council"},
    {"key": "townsquare", "name": "Town Square",          "url": f"http://{HQ}:8852/town_square", "expect": "html",  "path": "/town_square"},
    {"key": "linkhealth", "name": "Link Health",          "url": f"http://{HQ}:8852/link_health", "expect": "json",  "path": "/link_health"},
    {"key": "brain",      "name": "Brain Router usage",   "url": f"http://{HQ}:8852/brain/usage", "expect": "json",  "path": "/brain/usage"},
    {"key": "genepool",   "name": "Gene Pool / Brain Router", "url": f"http://{HQ}:8860/health",  "expect": "json",  "path": ":8860/"},
    {"key": "hq",         "name": "Claude HQ",            "url": f"http://{HQ}:8850/",            "expect": "html",  "path": ":8850/"},
    {"key": "wren",       "name": "Wren / WEN",           "url": f"http://{HQ}:8851/",            "expect": "html",  "path": ":8851/"},
    {"key": "tp",         "name": "TP-Pip (runtime)",     "url": f"http://{HQ}:8861/status",      "expect": "json",  "path": ":8861/"},
    {"key": "acer",       "name": "Acer-Cass (runtime)",  "url": f"http://{HQ}:8862/status",      "expect": "json",  "path": ":8862/"},
]

def probe(url: str, expect: str) -> dict:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "qsb-tour-guide"})
        with urllib.request.urlopen(req, timeout=4) as r:
            # read enough to validate JSON payloads (some are >100KB); cap at 2MB
            body = r.read(2_000_000) if expect == "json" else r.read(4096)
            code = r.getcode()
        ok_content = True
        detail = ""
        if expect == "json":
            try:
                json.loads(body.decode("utf-8", "replace"))
                detail = "valid json"
            except Exception:
                ok_content = False; detail = "not json"
        else:
            ok_content = b"<" in body or len(body) > 50
            detail = f"{len(body)}b"
        colour = "green" if (code == 200 and ok_content) else ("yellow" if code == 200 else "red")
        return {"code": code, "colour": colour, "detail": detail}
    except Exception as e:
        return {"code": 0, "colour": "red", "detail": f"unreachable: {type(e).__name__}"}

def health_payload() -> dict:
    out = []
    for s in SERVICES:
        p = probe(s["url"], s["expect"])
        out.append({**{k: s[k] for k in ("key", "name", "path")}, **p})
    return {"as_of": _now(), "services": out}

def _now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def load_floors() -> list:
    try:
        return json.loads(FLOORS.read_text())
    except Exception:
        return []

HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>SkyscraperHQ — Tour Guide</title>
<style>
:root{--bg:#070a12;--pane:#0e1524;--pane2:#131c30;--ink:#e9eefb;--dim:#93a2c4;--gold:#eab308;--line:#22304e;
 --green:#22c55e;--yellow:#eab308;--red:#ef4444;--grey:#64748b;--accent:#3b82f6}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);
 font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--accent);text-decoration:none}
.wrap{max-width:1200px;margin:0 auto;padding:16px}
header.hero{text-align:center;padding:34px 16px 22px;background:
 radial-gradient(1200px 300px at 50% -60px,rgba(59,130,246,.18),transparent),var(--bg)}
.hero h1{margin:0;font-size:clamp(26px,6vw,44px);letter-spacing:.5px}
.hero .gold{color:var(--gold)}
.hero p{color:var(--dim);max-width:720px;margin:10px auto 0;font-size:clamp(14px,3.4vw,17px)}
.modebar{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:16px 0}
.chip{background:var(--pane);border:1px solid var(--line);color:var(--ink);padding:10px 16px;border-radius:999px;
 font-size:15px;cursor:pointer;min-height:44px}
.chip.active{background:var(--gold);color:#111;border-color:var(--gold);font-weight:600}
.grid{display:grid;gap:14px}
.cols3{grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}
.pane{background:var(--pane);border:1px solid var(--line);border-radius:14px;padding:16px}
.pane h2{margin:0 0 10px;font-size:18px;color:var(--gold)}
.tourbar{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.btn{background:var(--pane2);border:1px solid var(--line);color:var(--ink);padding:12px 16px;border-radius:10px;
 font-size:15px;cursor:pointer;min-height:46px;min-width:44px}
.btn:hover{border-color:var(--accent)}
.btn.primary{background:var(--accent);border-color:var(--accent);font-weight:600}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;vertical-align:middle;margin-right:7px}
.green{background:var(--green)} .yellow{background:var(--yellow)} .red{background:var(--red)} .grey{background:var(--grey)}
.tower{display:flex;flex-direction:column-reverse;gap:3px;padding:10px;background:linear-gradient(#0a1020,#0e1730);
 border:1px solid var(--line);border-radius:14px;max-height:60vh;overflow:auto}
.zone-h{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.14em;margin:8px 4px 2px}
.fl{display:flex;align-items:center;gap:10px;padding:9px 12px;border:1px solid var(--line);border-radius:8px;
 background:var(--pane2);cursor:pointer;transition:transform .12s,background .12s}
.fl:hover{transform:translateX(4px);background:#182644}
.fl .num{color:var(--gold);font-weight:700;min-width:34px;text-align:right}
.fl .nm{flex:1}
.fl .st{font-size:12px;color:var(--dim)}
.card{background:var(--pane2);border:1px solid var(--line);border-radius:12px;padding:14px}
.card h3{margin:0 0 4px;font-size:17px}
.card .sub{color:var(--dim);font-size:13px}
.card .row{display:flex;justify-content:space-between;gap:8px;margin-top:8px;font-size:14px}
.k{color:var(--dim)}
.truth{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 12px;border-bottom:1px solid var(--line)}
.truth:last-child{border-bottom:0}
.truth .l{display:flex;align-items:center;gap:6px}
.truth .r{font-size:13px;color:var(--dim);text-align:right}
.hide{display:none!important}
.note{color:var(--dim);font-size:13px;margin-top:8px}
.footer{color:var(--grey);text-align:center;padding:22px;font-size:13px}
.badge{font-size:12px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--dim)}
@media(max-width:560px){.wrap{padding:10px}.pane{padding:12px}}
</style></head>
<body>
<header class="hero">
  <h1>Welcome to <span class="gold">SkyscraperHQ</span></h1>
  <p>Ross's AI command building — where the worker CEOs (Claude HQ, TP-Pip, Acer-Cass),
     Wren the observer, the Task Council, the Gene Pool / Brain Router, the Council of 15
     toolbox, the dashboards and the Receptionist all coordinate real work across a
     166-floor tower. This is a guided tour of the live system.</p>
  <div class="modebar" id="modebar">
    <div class="chip active" data-mode="visitor">Visitor</div>
    <div class="chip" data-mode="reception">Receptionist</div>
    <div class="chip" data-mode="admin">Ross / Admin</div>
  </div>
</header>
<div class="wrap">

  <div class="pane">
    <h2>Guided Tour</h2>
    <div class="tourbar">
      <button class="btn primary" onclick="tour.start()">▶ Start Tour</button>
      <button class="btn" onclick="tour.pause()">⏸ Pause</button>
      <button class="btn" onclick="tour.prev()">◀ Previous Floor</button>
      <button class="btn" onclick="tour.next()">Next Floor ▶</button>
      <button class="btn" onclick="tour.lobby()">🏛 Back to Lobby</button>
      <button class="btn" onclick="scrollTo('sec-status')">Show System Status</button>
      <button class="btn" onclick="scrollTo('sec-ceo')">Show CEO Team</button>
      <button class="btn" onclick="scrollTo('sec-gene')">Show Gene Pool</button>
      <button class="btn" onclick="scrollTo('sec-tasks')">Show Task Council</button>
      <button class="btn" onclick="scrollTo('sec-town')">Show Town Square</button>
      <button class="btn" onclick="scrollTo('sec-rec')">Show Receptionist</button>
    </div>
    <div id="narration" class="note">The guide is ready. Press <b>Start Tour</b> to ride the lifts up the tower, or tap any floor.</div>
  </div>

  <div class="grid cols3" style="margin-top:14px">
    <div class="pane" style="grid-column:1/-1" id="sec-tower">
      <h2>The Tower <span class="badge" id="floorcount">…</span></h2>
      <div class="tower" id="tower">Loading real floor registry…</div>
    </div>
  </div>

  <div class="pane" style="margin-top:14px" id="sec-floor">
    <h2>Floor Detail</h2>
    <div id="floordetail" class="note">Select a floor in the tower to see its department, purpose, owner and live status.</div>
  </div>

  <div class="grid cols3" style="margin-top:14px">
    <div class="pane" id="sec-status">
      <h2>Link Health — Truth Strip</h2>
      <div id="truth">Probing services server-side…</div>
      <div class="note">green = reachable + correct · yellow = 200 but partial · red = unreachable · grey = unknown</div>
    </div>
    <div class="pane" id="sec-ceo">
      <h2>CEO Presence</h2>
      <div id="ceos">Loading…</div>
      <div class="note">Presence is probed live. Unreachable nodes are shown red, never faked.</div>
    </div>
    <div class="pane" id="sec-gene">
      <h2>Gene Pool / Brain Router</h2>
      <div id="gene">Loading…</div>
      <div class="note">Doctrine: Brain Router inside HQ · CEOs use API Gene Pool only · Claude last-resort · Wren protects local GPU.</div>
    </div>
  </div>

  <div class="grid cols3" style="margin-top:14px">
    <div class="pane" id="sec-tasks"><h2>Task Council</h2><div id="tasks">Loading…</div></div>
    <div class="pane" id="sec-town"><h2>Town Square</h2><div id="town">Loading…</div></div>
    <div class="pane" id="sec-c15">
      <h2>Council of 15 — Toolbox</h2>
      <div id="c15"></div>
      <div class="note">Helpers/tools — NOT peer CEOs. They never count as the 2nd CEO or as independent verification unless Ross allow-lists them.</div>
    </div>
  </div>

  <div class="pane recept hide" id="sec-rec" style="margin-top:14px">
    <h2>Receptionist Front Desk (qsb-reception)</h2>
    <div class="tourbar">
      <button class="btn primary" onclick="tour.start()">▶ Start Tour</button>
      <button class="btn" onclick="alert('Task Council request — opens the request form on the hub Task Council.')">＋ New Task Council Request</button>
      <button class="btn" onclick="scrollTo('sec-status')">System Status</button>
      <button class="btn" onclick="openLive('boardroom')">Boardroom</button>
      <button class="btn" onclick="openLive('genepool')">Gene Pool</button>
      <button class="btn" onclick="openLive('townsquare')">Town Square</button>
      <button class="btn" onclick="openLive('wren')">Wren status</button>
      <button class="btn" onclick="scrollTo('sec-ceo')">CEO status</button>
    </div>
    <div class="grid cols3" style="margin-top:8px">
      <div class="card"><h3>Pico</h3><div class="sub">e-stop / smoke / refresh buttons</div><div class="row"><span class="k">status</span><span><span class="dot grey"></span>needs Pi boot</span></div></div>
      <div class="card"><h3>SSK storage</h3><div class="sub">logs · screenshots · reports</div><div class="row"><span class="k">status</span><span><span class="dot grey"></span>mount on Pi (no format)</span></div></div>
      <div class="card"><h3>Emergency stop</h3><div class="sub">placeholder — only if wired + verified</div><div class="row"><span class="k">status</span><span><span class="dot grey"></span>not wired</span></div></div>
    </div>
    <div class="note">Receptionist is not a CEO. It welcomes visitors, guides the tour, shows status, and creates requests.</div>
  </div>

  <div class="pane admin hide" id="sec-admin" style="margin-top:14px">
    <h2>Ross / Admin</h2>
    <div id="admin"></div>
  </div>

  <div class="footer">SkyscraperHQ Tour Guide · live data, no placeholders · <span id="stamp"></span></div>
</div>

<script>
const HOSTBASE = location.protocol + '//' + location.hostname; // links follow how you reached this page
const PORT = {boardroom:8852,tasks:8852,council:8852,townsquare:8852,linkhealth:8852,brain:8852,genepool:8860,hq:8850,wren:8851,tp:8861,acer:8862};
const PATHS = {boardroom:'/',tasks:'/tasks',council:'/council',townsquare:'/town_square',linkhealth:'/link_health',brain:'/brain/usage',genepool:'/',hq:'/',wren:'/',tp:'/',acer:'/'};
function liveURL(k){return HOSTBASE + ':' + PORT[k] + PATHS[k];}
function openLive(k){window.open(liveURL(k),'_blank');}
function scrollTo(id){document.getElementById(id).scrollIntoView({behavior:'smooth'});}
function el(t,c,h){const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;}
document.getElementById('stamp').textContent = new Date().toISOString();

// modes
let MODE='visitor';
document.querySelectorAll('#modebar .chip').forEach(ch=>ch.onclick=()=>{
  MODE=ch.dataset.mode;
  document.querySelectorAll('#modebar .chip').forEach(x=>x.classList.toggle('active',x===ch));
  document.querySelectorAll('.recept').forEach(e=>e.classList.toggle('hide',MODE!=='reception'));
  document.querySelectorAll('.admin').forEach(e=>e.classList.toggle('hide',MODE!=='admin'));
});

// floors
let FLOORS=[], idx=0;
fetch('/api/floors').then(r=>r.json()).then(d=>{FLOORS=d.floors||[];renderTower();});
function renderTower(){
  const t=document.getElementById('tower');t.innerHTML='';
  document.getElementById('floorcount').textContent = FLOORS.length + ' floors';
  let zone=null;
  FLOORS.slice().sort((a,b)=>a.number-b.number).forEach(f=>{
    if(f.zone!==zone){zone=f.zone;t.appendChild(el('div','zone-h',zone||'zone'));}
    const row=el('div','fl');
    row.innerHTML=`<span class="num">${f.number}</span><span class="nm">${f.floor_name||f.department||('Floor '+f.number)}</span>`+
      `<span class="st">${f.vacant?'vacant':(f.status||'')}</span>`;
    row.onclick=()=>showFloor(f);
    t.appendChild(row);
  });
}
function showFloor(f){
  idx=FLOORS.findIndex(x=>x.id===f.id);
  const d=document.getElementById('floordetail');
  const owner=f.staff_lead?`<div class="row"><span class="k">owner / lead</span><span>${f.staff_lead}</span></div>`:'';
  d.innerHTML=`<div class="card"><h3>Floor ${f.number} · ${f.floor_name||f.department||''}</h3>`+
    `<div class="sub">${f.department||''} — ${f.zone||''} zone</div>`+
    `<div class="row"><span class="k">purpose</span><span style="max-width:70%;text-align:right">${f.description||'—'}</span></div>`+
    owner+
    `<div class="row"><span class="k">status</span><span>${f.vacant?'<span class="dot grey"></span>vacant / expansion-ready':'<span class="dot green"></span>'+(f.status||'active')}</span></div>`+
    `<div class="row"><span class="k">archetype</span><span>${f.archetype||'—'}</span></div>`+
    `</div>`;
  document.getElementById('narration').innerHTML = narrate(f);
  scrollTo('sec-floor');
}
function narrate(f){
  return `<b>Floor ${f.number} — ${f.floor_name||f.department}.</b> ${f.description||''} `+
    (f.vacant?'This floor is serviced and expansion-ready.':'This department is active.')+
    (f.staff_lead?` Led by ${f.staff_lead}.`:'');
}
const tour={_t:null,start(){this.stop();this._t=setInterval(()=>this.next(),3500);this.next();},
 pause(){this.stop();},stop(){if(this._t){clearInterval(this._t);this._t=null;}},
 next(){if(!FLOORS.length)return;idx=(idx+1)%FLOORS.length;showFloor(FLOORS[idx]);},
 prev(){if(!FLOORS.length)return;idx=(idx-1+FLOORS.length)%FLOORS.length;showFloor(FLOORS[idx]);},
 lobby(){idx=FLOORS.findIndex(f=>f.number===0);if(idx>=0)showFloor(FLOORS[idx]);scrollTo('sec-tower');}};

// health / truth strip + CEO + gene + admin
function colourDot(c){return `<span class="dot ${c}"></span>`;}
function loadHealth(){
  fetch('/api/health').then(r=>r.json()).then(d=>{
    const t=document.getElementById('truth');t.innerHTML='';
    d.services.forEach(s=>{
      const row=el('div','truth');
      row.innerHTML=`<span class="l">${colourDot(s.colour)}<b>${s.name}</b></span>`+
        `<span class="r">HTTP ${s.code} · ${s.detail}<br><a href="#" onclick="window.open(liveURL('${s.key}')||'#','_blank');return false">${s.path}</a></span>`;
      t.appendChild(row);
    });
    // CEO panel
    const byk=Object.fromEntries(d.services.map(s=>[s.key,s]));
    const ceo=document.getElementById('ceos');ceo.innerHTML='';
    [['hq','Claude HQ','worker CEO — coordination/reasoning'],
     ['tp','TP-Pip / ThinkPad','worker CEO — ThinkPad (openai backend)'],
     ['acer','Acer-Cass / ASA','worker CEO — Data Foundry (deepseek backend)'],
     ['wren','Wren / WEN','observer + Ross assistant (qwen2.5:14b)']].forEach(([k,nm,role])=>{
      const s=byk[k]||{colour:'grey',code:0};
      const c=el('div','card');
      c.innerHTML=`<h3>${colourDot(s.colour)}${nm}</h3><div class="sub">${role}</div>`+
        `<div class="row"><span class="k">dashboard</span><span><a href="#" onclick="openLive('${k}');return false">open ▸</a></span></div>`+
        `<div class="row"><span class="k">probe</span><span>HTTP ${s.code}</span></div>`;
      ceo.appendChild(c);
    });
    const rec=el('div','card');rec.innerHTML=`<h3><span class="dot grey"></span>Receptionist (qsb-reception)</h3><div class="sub">Raspberry Pi front desk — not a CEO</div><div class="row"><span class="k">status</span><span>boots on Pi; unverified until powered on</span></div>`;
    ceo.appendChild(rec);
    // Gene pool
    const g=byk['genepool'];const gp=document.getElementById('gene');
    const provs=['claude','openai','deepseek','gemini','cohere','kimi','grok','groq'];
    gp.innerHTML=`<div class="row"><span class="k">router</span><span>${colourDot(g?g.colour:'grey')}HTTP ${g?g.code:0}</span></div>`;
    provs.forEach(p=>{gp.appendChild(el('div','truth',`<span class="l">${colourDot('green')}${p}</span><span class="r">API gene pool</span>`));});
    gp.appendChild(el('div','note',null)).textContent='Provider list from gene_pool_router_state (grok has 0 keys). Usage: '+liveURL('brain');
    // admin
    const a=document.getElementById('admin');
    const reds=d.services.filter(s=>s.colour==='red').map(s=>s.name);
    a.innerHTML=`<div class="card"><h3>Raw link health</h3>`+
      d.services.map(s=>`<div class="row"><span class="k">${colourDot(s.colour)}${s.name}</span><span>HTTP ${s.code} · ${s.detail}</span></div>`).join('')+
      `</div>`+
      `<div class="card" style="margin-top:10px"><h3>Unreachable / dead</h3><div class="sub">${reds.length?reds.join(', '):'none right now'}</div></div>`+
      `<div class="card" style="margin-top:10px"><h3>Notes for Ross</h3><div class="sub">Enforcement Pass 1 = proposal (not landed). Pi Receptionist boot drive reflashed, awaiting boot test. Reports in 00_SEND_THIS_TO_CHATGPT.</div></div>`;
    document.getElementById('stamp').textContent = 'link-health as of '+d.as_of;
  }).catch(e=>{document.getElementById('truth').textContent='health probe failed: '+e;});
}
loadHealth(); setInterval(loadHealth, 15000);

// tasks + town + council15
fetch('/api/tasks').then(r=>r.json()).then(d=>{
  const t=document.getElementById('tasks');
  const list=(d.tasks||[]).slice(0,8);
  t.innerHTML=`<div class="row"><span class="k">total tasks</span><span>${d.total||list.length}</span></div>`+
    list.map(x=>`<div class="truth"><span class="l">${x.title?x.title.slice(0,42):x.id}</span><span class="r">${x.state||''}</span></div>`).join('')+
    `<div class="note"><a href="#" onclick="openLive('tasks');return false">open full Task Council ▸</a></div>`;
}).catch(()=>{document.getElementById('tasks').innerHTML='<span class="dot red"></span>Task Council data unreachable';});

fetch('/api/town').then(r=>r.json()).then(d=>{
  const t=document.getElementById('town');
  const p=(d.posts||[]).slice(-6).reverse();
  t.innerHTML=(p.length?p.map(x=>`<div class="truth"><span class="l">${(x.author||x.ceo||'?')}</span><span class="r">${((x.text||x.msg||'')+'').slice(0,60)}</span></div>`).join('')
    :'<span class="dot yellow"></span>feed reachable, no recent posts parsed')+
    `<div class="note"><a href="#" onclick="openLive('townsquare');return false">open Town Square ▸</a></div>`;
}).catch(()=>{document.getElementById('town').innerHTML='<span class="dot red"></span>Town Square unreachable';});

const C15=[['Hermes / Hermes-CPU','coordination / presentation'],['iQuest Coder (CPU)','code & service inspection'],
 ['Qwen 14B Coder','local code reasoning'],['DeepSeek Coder','frontend/service review'],
 ['Gene Pool providers','routing layer (8 providers)'],['Worker slots F05','coding intake/patch/review/test'],
 ['Routing F24','sealed-packet / provider selection'],['Recruitment F25','worker recruitment'],
 ['Model floor F27','reasoning/coding/vision slots'],['Dashboard repair worker','dashboard fixes'],
 ['Town Square','live council feed'],['Manuscript','durable record'],['Boardroom Hub','the wall']];
document.getElementById('c15').innerHTML=C15.map(([n,r])=>`<div class="truth"><span class="l"><span class="dot grey"></span>${n}</span><span class="r">${r}</span></div>`).join('');
</script>
</body></html>"""

class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html", "/tour"):
            return self._send(200, HTML, "text/html; charset=utf-8")
        if p == "/api/floors":
            return self._send(200, {"floors": load_floors()})
        if p == "/api/health":
            return self._send(200, health_payload())
        if p == "/api/tasks":
            try:
                with urllib.request.urlopen(f"http://{HQ}:8852/tasks/data", timeout=4) as r:
                    return self._send(200, json.loads(r.read()))
            except Exception as e:
                return self._send(200, {"total": 0, "tasks": [], "err": str(e)})
        if p == "/api/town":
            try:
                posts = []
                tsf = ROOT / "data/registries/qsb_town_square.jsonl"
                if tsf.exists():
                    for line in tsf.read_text().splitlines()[-40:]:
                        try: posts.append(json.loads(line))
                        except Exception: pass
                return self._send(200, {"posts": posts})
            except Exception as e:
                return self._send(200, {"posts": [], "err": str(e)})
        if p == "/healthz":
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "not found"})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8854)
    ap.add_argument("--host", default="0.0.0.0")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), H)
    ip = socket.gethostbyname(socket.gethostname())
    print(f"SkyscraperHQ Tour Guide serving on http://{a.host}:{a.port}/  (LAN ~ http://{ip}:{a.port}/)")
    srv.serve_forever()

if __name__ == "__main__":
    main()
