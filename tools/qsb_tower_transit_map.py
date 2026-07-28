#!/usr/bin/env python3
"""
qsb_tower_transit_map.py — LIVE SkyscraperHQ Tube Map (:8875).

2026-07-28, Ross: "like a tube station underground network ... carriages on the move ...
Bill + Wren need a track to everyone everywhere ... the gene pool needs its own SUB-TRACKS
to show what it's doing with who."

Stations = hubs/floors + the gene pool's PROVIDER sub-stations. Trains = real tasks /
routing / messages. A busy line works; a still line doesn't. No demo motion.

REAL sources:
  - gene-pool routing : qsb_brain_router_calls.jsonl  (caller -> Gene Pool -> provider)
  - council flow       : qsb_council_tasks.jsonl
  - comms mesh         : leadership_comms/room.jsonl + acks.jsonl + dm/*.jsonl
  - presence (online)  : leadership_comms/presence.json
Read-only. systemd qsb-transit-map.service.
"""
import json, argparse, time, glob
from collections import deque, Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REG = Path("/vaults/nvme0/qsb_tower_v1/data/registries")
LC = REG / "leadership_comms"
CALLS = REG / "qsb_brain_router_calls.jsonl"
COUNCIL = REG / "qsb_council_tasks.jsonl"
ROOM = LC / "room.jsonl"
ACKS = LC / "acks.jsonl"
PRESENCE = LC / "presence.json"
VER = str(int(time.time()))

STATIONS = {
    # hubs
    "boardroom":    {"x": 560, "y": 300, "label": "Boardroom Hub", "big": True},
    "town_square":  {"x": 560, "y": 92,  "label": "Town Square · 74", "big": True},
    "task_council": {"x": 560, "y": 520, "label": "Task Council · 77", "big": True},
    "council15":    {"x": 330, "y": 540, "label": "Council of 15 · 75"},
    "gene_pool":    {"x": 820, "y": 300, "label": "Gene Pool · 24", "big": True},
    # AIs / floors
    "codex":        {"x": 110, "y": 360, "label": "Codex · 40"},
    "lumen":        {"x": 150, "y": 540, "label": "Lumen · 48"},
    "wren":         {"x": 380, "y": 300, "label": "Wren"},
    "tp_pip":       {"x": 200, "y": 150, "label": "TP-Pip"},
    "acer_cass":    {"x": 200, "y": 470, "label": "Asa"},
    "bill":         {"x": 380, "y": 110, "label": "Bill · Mac"},
    # gene-pool provider sub-stations (far right fan)
    "openai":       {"x": 1050, "y": 130, "label": "openai", "prov": True},
    "deepseek":     {"x": 1080, "y": 220, "label": "deepseek", "prov": True},
    "cohere":       {"x": 1095, "y": 305, "label": "cohere", "prov": True},
    "gemini":       {"x": 1080, "y": 388, "label": "gemini", "prov": True},
    "groq":         {"x": 1050, "y": 470, "label": "groq", "prov": True},
    "kimi":         {"x": 970,  "y": 150, "label": "kimi", "prov": True},
    "grok":         {"x": 970,  "y": 455, "label": "grok", "prov": True},
    "claude":       {"x": 940,  "y": 300, "label": "claude", "prov": True},
    # Council-of-15 + Wren shared specialist sub-stations
    "iquest_40b":   {"x": 230, "y": 235, "label": "iQuest-40B", "sub": True},
    "qwen_worker":  {"x": 255, "y": 605, "label": "qwen worker", "sub": True},
    "hermes":       {"x": 430, "y": 612, "label": "Hermes", "sub": True},
    "claude_acct":  {"x": 150, "y": 300, "label": "Claude", "sub": True},
    "wren_brain":   {"x": 375, "y": 205, "label": "Wren·qwen14b", "sub": True},
    "f46_bench":    {"x": 480, "y": 235, "label": "F46 Bench", "sub": True},
    "tc_sandbox":   {"x": 660, "y": 600, "label": "Sandbox", "sub": True},
    "oracle":       {"x": 760, "y": 110, "label": "Oracle · Cloud VM", "big": True},
}
PROV = {"openai", "deepseek", "cohere", "gemini", "groq", "kimi", "grok", "claude", "ollama_lan", "ollama_local"}

CORE = ["wren", "tp_pip", "acer_cass", "bill", "codex", "lumen"]
HUBS = ["boardroom", "town_square", "task_council", "council15", "gene_pool"]
PROVIDERS = ["openai", "deepseek", "cohere", "gemini", "groq", "kimi", "grok", "claude"]
LINES = []
# EVERYONE connects with EVERYONE — full mesh among the AIs/CEOs
for i, a in enumerate(CORE):
    for b in CORE[i + 1:]:
        LINES.append((a, b, "comms"))
# every AI -> every hub (gene-pool access for ALL, council, comms, interchange)
for a in CORE:
    for h in HUBS:
        cat = "route" if h == "gene_pool" else ("council" if h in ("task_council", "council15")
              else ("comms" if h == "town_square" else "hub"))
        LINES.append((a, h, cat))
# hubs interconnect (every hub to every hub)
for i, a in enumerate(HUBS):
    for b in HUBS[i + 1:]:
        LINES.append((a, b, "hub"))
# gene-pool SUB-TRACKS -> every provider
for p in PROVIDERS:
    LINES.append(("gene_pool", p, "provider"))
# dedupe (keep first category)
_seen = set(); _L = []
for a, b, c in LINES:
    k = tuple(sorted((a, b)))
    if k not in _seen:
        _seen.add(k); _L.append((a, b, c))
LINES = _L
# SUB-TRACKS: Council of 15, Wren, and Task Council each get their own internal lines
LINES += [
    ("council15", "iquest_40b", "c15"), ("council15", "qwen_worker", "c15"),
    ("council15", "hermes", "c15"), ("council15", "claude_acct", "c15"), ("council15", "gene_pool", "c15"),
    ("wren", "wren_brain", "wrensub"), ("wren", "f46_bench", "wrensub"),
    ("wren", "hermes", "wrensub"), ("wren", "iquest_40b", "wrensub"),
    ("task_council", "tc_sandbox", "council"), ("task_council", "council15", "council"),
    # Oracle Cloud VM — tunnels into the tower
    ("oracle", "boardroom", "hub"), ("oracle", "gene_pool", "route"),
    ("oracle", "town_square", "comms"), ("oracle", "wren", "comms"),
]
CAT_COLOR = {"route": "#40b4ff", "provider": "#45f59b", "council": "#b98bff", "comms": "#ffc24b",
             "hub": "#6d7f98", "c15": "#2dd4bf", "wrensub": "#c4a3ff"}
PRES_MAP = {"wren": "wren", "tp": "tp_pip", "asa": "acer_cass", "bill": "bill", "pip": "tp_pip"}
# comms logs use short names (asa/tp/pip); stations are keyed acer_cass/tp_pip. Resolve so
# TP↔Asa room posts, acks, and DM lines actually become trains ("everyone talking").
ALIAS = {"asa": "acer_cass", "tp": "tp_pip", "pip": "tp_pip", "tp_pip": "tp_pip",
         "acer_cass": "acer_cass", "wren": "wren", "bill": "bill"}


def _sid(name):
    """Resolve a comms-log actor name to a station key, or None if not a station."""
    if not name:
        return None
    s = ALIAS.get(name, name)
    return s if s in STATIONS else None


def _tail(path, n):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return [json.loads(x) for x in deque(f, maxlen=n) if x.strip()]
    except Exception:
        return []


def _load(p, d):
    try:
        return json.loads(Path(p).read_text(errors="ignore"))
    except Exception:
        return d


def _tool_station(text):
    t = (text or "").lower()
    if "gene pool" in t: return "gene_pool"
    if "iquest" in t: return "iquest_40b"
    if "hermes" in t: return "hermes"
    if "claude" in t: return "claude_acct"
    if "qwen" in t: return "qwen_worker"
    return "qwen_worker"


def build():
    trains = []
    # 1) gene-pool routing: caller -> gene_pool AND gene_pool -> provider (the sub-track)
    for r in _tail(CALLS, 70):
        caller = r.get("caller")
        frm = _sid(caller) or "boardroom"
        prov = (r.get("provider_used") or r.get("provider") or "").lower()
        ts = r.get("ts")
        trains.append({"from": frm, "to": "gene_pool", "ts": ts, "cat": "route",
                       "label": (caller or "?") + " → Gene Pool"})
        if prov in STATIONS:
            trains.append({"from": "gene_pool", "to": prov, "ts": ts, "cat": "provider",
                           "label": "Gene Pool → " + prov + "  (" + (caller or "?") + ")"})
    # 2) council flow
    for r in _tail(COUNCIL, 90):
        ev, actor, tid = r.get("event"), r.get("actor"), r.get("task_id")
        seg = None
        if ev == "created" and actor == "codex":
            seg = ("codex", "task_council")
        elif ev == "tool_selected":
            seg = ("task_council", "council15")
        elif ev in ("sandbox_passed", "awaiting_verification", "peer_signoff"):
            seg = ("task_council", "gene_pool")
        elif actor == "wren" and ev in ("claimed", "assigned", "blocked", "recycled", "done", "noted"):
            seg = ("wren", "task_council")
        elif actor == "bill":
            seg = ("bill", "task_council")
        if seg:
            trains.append({"from": seg[0], "to": seg[1], "ts": r.get("ts"), "cat": "council",
                           "label": (actor or "?") + " " + (ev or "") + " " + (tid or "")})
        # SUB-TRACK trains
        if ev == "tool_selected":
            spec = _tool_station(r.get("text"))
            trains.append({"from": "council15", "to": spec, "ts": r.get("ts"), "cat": "c15",
                           "label": "Council of 15 → " + spec})
            trains.append({"from": "wren", "to": spec, "ts": r.get("ts"), "cat": "wrensub",
                           "label": "Wren wields " + spec})
        elif ev in ("sandbox_passed", "sandbox_rejected"):
            trains.append({"from": "task_council", "to": "tc_sandbox", "ts": r.get("ts"), "cat": "council",
                           "label": "sandbox " + (ev or "")})
        elif ev == "done":
            trains.append({"from": "task_council", "to": "wren", "ts": r.get("ts"), "cat": "council",
                           "label": "Wren gate: done " + (tid or "")})
    # Wren's own brain (her local qwen replies)
    for r in _tail(REG / "qsb_wren_dash_chat.jsonl", 20):
        if r.get("reply") or (r.get("role") or r.get("from") or "").lower() == "wren":
            trains.append({"from": "wren", "to": "wren_brain", "ts": r.get("ts", ""), "cat": "wrensub",
                           "label": "Wren thinking · qwen14b"})
    # 3) comms mesh: room -> town square, acks between members, DMs member<->member
    for r in _tail(ROOM, 60):
        frm = _sid(r.get("from") or r.get("sender")) or "boardroom"
        trains.append({"from": frm, "to": "town_square", "ts": r.get("ts", ""), "cat": "comms",
                       "label": STATIONS[frm]["label"].split(" ·")[0] + " → square"})
    for r in _tail(ACKS, 60):
        frm, to = _sid(r.get("from")), _sid(r.get("to"))
        if frm and to and frm != to:
            trains.append({"from": frm, "to": to, "ts": r.get("ts", ""), "cat": "comms",
                           "label": frm + " → " + to + " ack"})
    for f in glob.glob(str(LC / "dm" / "*.jsonl")):
        nm = [_sid(x) for x in Path(f).stem.split("__")]
        if len(nm) == 2 and nm[0] and nm[1] and nm[0] != nm[1]:
            for r in _tail(f, 8):
                frm = _sid(r.get("from")) or nm[0]
                to = nm[1] if frm == nm[0] else nm[0]
                trains.append({"from": frm, "to": to, "ts": r.get("ts", ""), "cat": "comms",
                               "label": frm + " ↔ " + to + " DM"})
    # balance categories so routing traffic doesn't DROWN the comms mesh — show EVERYONE talking
    _bc = {}
    for t in trains:
        _bc.setdefault(t["cat"], []).append(t)
    trains = []
    for cat, K in (("route", 12), ("provider", 12), ("comms", 24), ("council", 12), ("c15", 8), ("wrensub", 8)):
        trains += _bc.get(cat, [])[-K:]
    trains.sort(key=lambda t: t.get("ts") or "")

    # presence -> online glow
    pres = _load(PRESENCE, {}) or {}
    online = {}
    for k, v in (pres.items() if isinstance(pres, dict) else []):
        if isinstance(v, dict) and v.get("last_heartbeat_epoch"):
            sid = PRES_MAP.get(k, k)
            if sid in STATIONS and (time.time() - v["last_heartbeat_epoch"]) < 120:
                online[sid] = True

    act = Counter((t["from"], t["to"]) for t in trains)
    return {"ver": VER, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "stations": STATIONS, "online": online,
            "lines": [{"a": a, "b": b, "cat": c, "act": act.get((a, b), 0) + act.get((b, a), 0)} for a, b, c in LINES],
            "trains": trains, "cat_color": CAT_COLOR, "moving": len(trains),
            "bill_gp": sum(1 for t in trains if t["from"] == "bill" and t["to"] == "gene_pool")}


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>SkyscraperHQ · Tube Map · :8875</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0a0e16;--line:#233146;--txt:#e8f1ff;--dim:#8ba0ba}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1300px;margin:0 auto;padding:14px}
h1{margin:0;font-size:20px}.sub{color:var(--dim);margin:2px 0 8px}
.hp{display:inline-block;padding:3px 10px;border-radius:999px;font-weight:700;font-size:12px;margin-left:8px}
.hp.ok{background:rgba(69,245,155,.15);color:#45f59b;border:1px solid #45f59b}
.hp.dead{background:rgba(255,93,125,.15);color:#ff5d7d;border:1px solid #ff5d7d}
#map{width:100%;height:680px;background:radial-gradient(circle at 62% 44%,#0f1a2c,#080c14 72%);border:1px solid var(--line);border-radius:16px}
.rail{fill:none;stroke-linecap:round;stroke-linejoin:round}
.roundel{fill:#0a0e16;stroke:#e8f1ff;stroke-width:3}
.roundel.big{stroke-width:4}.roundel.prov{stroke-width:2}
.on{stroke:#45f59b}
.stlabel{fill:#e8f1ff;font-size:11px;font-weight:600}
.stlabel.big{font-size:13px;font-weight:700}.stlabel.prov{fill:#8fe6b5;font-size:10px}
.train{filter:drop-shadow(0 0 6px currentColor)}
.legend{display:flex;gap:14px;color:var(--dim);font-size:12px;margin-top:8px;flex-wrap:wrap;align-items:center}
.k{display:inline-block;width:22px;height:5px;border-radius:3px;margin-right:6px;vertical-align:middle}
</style></head><body><div class=wrap>
<h1>SkyscraperHQ · Underground <span style="color:#40b4ff">· :8875</span><span id=health class="hp ok">—</span></h1>
<div class=sub>Carriages run on lines with REAL activity. Gene-Pool sub-tracks show which provider it routes to. Green ring = online.</div>
<svg id=map></svg>
<div class=legend>
  <span><span class=k style="background:#40b4ff"></span>routing → Gene Pool</span>
  <span><span class=k style="background:#45f59b"></span>Gene-Pool → provider (sub-track)</span>
  <span><span class=k style="background:#b98bff"></span>council (tasks)</span>
  <span><span class=k style="background:#ffc24b"></span>comms mesh</span>
  <span id=movetxt></span>
  <span style="color:#8ba0ba">· click any station to command it</span>
</div>
<div id=cmd style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:60" onclick="if(event.target===this)this.style.display='none'">
  <div style="max-width:460px;margin:80px auto;background:#131a26;border:1px solid #233146;border-radius:14px;padding:18px">
    <div style="display:flex;justify-content:space-between;align-items:center"><b id=cmdTitle style="font-size:16px"></b><span onclick="document.getElementById('cmd').style.display='none'" style="cursor:pointer;color:#8ba0ba;font-size:22px">×</span></div>
    <textarea id=cmdText rows=3 placeholder="message / task / job…" style="width:100%;margin-top:10px;background:#0d1420;border:1px solid #233146;border-radius:8px;color:#e8f1ff;padding:8px;font:13px inherit;resize:vertical"></textarea>
    <div id=cmdBtns style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap"></div>
    <div id=cmdRes style="margin-top:10px;color:#8ba0ba;font-size:12px"></div>
  </div>
</div>
</div><script>
function actionsFor(id){
  if(id==='gene_pool')return [['route_job','▶ Route a job through the pool'],['link_mc','🧬 Open Mission Control — the REAL Gene Pool']];
  if(id==='task_council'||id==='council15')return [['book_task','📋 Book a council task']];
  if(['wren','tp_pip','acer_cass','bill','codex','lumen','oracle','boardroom','town_square'].includes(id))return [['message','✉ Send a message']];
  return [];
}
function openCmd(id,label){
  const m=document.getElementById('cmd');document.getElementById('cmdTitle').textContent=label+' — command';
  document.getElementById('cmdText').value='';document.getElementById('cmdRes').textContent='';
  const acts=actionsFor(id);
  document.getElementById('cmdBtns').innerHTML=acts.length?acts.map(a=>a[0]==='link_mc'?`<a href="http://${location.hostname}:8852/proxy/gene_pool" target=_blank style="background:#8a5cf6;color:#fff;border-radius:8px;padding:8px 12px;font-weight:700;text-decoration:none">${a[1]}</a>`:`<button onclick="sendCmd('${id}','${a[0]}')" style="background:#40b4ff;color:#04101f;border:0;border-radius:8px;padding:8px 12px;font-weight:700;cursor:pointer">${a[1]}</button>`).join(''):'<span style="color:#8ba0ba;font-size:12px">no direct command for this node</span>';
  m.style.display='block';
}
async function sendCmd(station,action){
  const text=document.getElementById('cmdText').value,res=document.getElementById('cmdRes');res.textContent='working…';
  try{const r=await(await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({station,action,text})})).json();
    res.textContent=r.ok?('✓ '+(r.result||'done')):('✕ '+(r.error||'failed'));}
  catch(e){res.textContent='✕ '+e}
}
const NS="http://www.w3.org/2000/svg";
function el(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e}
const svg=document.getElementById("map");let ST={},TR=[],CC={},ON={},qi=0;
function draw(d){
  ST=d.stations;CC=d.cat_color;ON=d.online||{};svg.innerHTML="";svg.setAttribute("viewBox","0 0 1200 680");
  d.lines.forEach(L=>{const A=ST[L.a],B=ST[L.b];if(!A||!B)return;const col=CC[L.cat]||"#6d7f98",act=L.act>0;
    svg.appendChild(el("path",{class:"rail",d:`M ${A.x} ${A.y} L ${B.x} ${B.y}`,stroke:col,"stroke-width":act?6:4,opacity:act?0.95:0.22}));});
  Object.entries(ST).forEach(([id,s])=>{
    const r=s.big?13:((s.prov||s.sub)?7:9),online=ON[id];
    if(online)svg.appendChild(el("circle",{cx:s.x,cy:s.y,r:r+5,fill:"none",stroke:"#45f59b","stroke-width":2,opacity:.8,id:"on_"+id}));
    const stc=el("circle",{cx:s.x,cy:s.y,r:r,class:"roundel"+(s.big?" big":"")+(s.prov?" prov":"")+(online?" on":""),id:"st_"+id});
    stc.style.cursor="pointer";stc.addEventListener("click",()=>openCmd(id,s.label));svg.appendChild(stc);
    const t=el("text",{x:s.x,y:s.y-(s.big?21:s.prov?13:17),"text-anchor":"middle",class:"stlabel"+(s.big?" big":"")+(s.prov?" prov":"")});
    t.textContent=s.label;svg.appendChild(t);
  });
  TR=d.trains||[];
}
function launch(tr){
  const A=ST[tr.from],B=ST[tr.to];if(!A||!B)return;const col=CC[tr.cat]||"#40b4ff";
  const g=el("g",{class:"train"});g.style.color=col;
  g.appendChild(el("rect",{x:A.x-12,y:A.y-5,width:11,height:10,rx:3,fill:col}));
  g.appendChild(el("rect",{x:A.x+1,y:A.y-5,width:11,height:10,rx:3,fill:col,opacity:.85}));
  const ti=el("title");ti.textContent=tr.label;g.appendChild(ti);svg.appendChild(g);
  g.animate([{transform:"translate(0,0)"},{transform:`translate(${B.x-A.x}px,${B.y-A.y}px)`}],
    {duration:1700,easing:"cubic-bezier(.35,0,.3,1)"}).onfinish=()=>{g.remove();
      const dst=document.getElementById("st_"+tr.to);if(dst){const rr=+dst.getAttribute("r");dst.animate([{r:rr},{r:rr*1.5},{r:rr}],{duration:450})}};
}
// fire several trains per tick so MANY carriages move at once (everyone talking, visibly)
setInterval(()=>{ if(!TR.length)return; for(let n=0;n<3;n++){ launch(TR[qi%TR.length]); qi++; } }, 300);
async function tick(){
  let d;try{d=await(await fetch("/api/data")).json()}catch(e){return}
  if(window.__v&&window.__v!==d.ver){location.reload();return}window.__v=d.ver;
  draw(d);
  const h=document.getElementById("health");
  if(d.moving>0){h.className="hp ok";h.textContent="● LIVE · "+d.moving+" trains"}
  else{h.className="hp dead";h.textContent="○ NO MOVEMENT"}
  document.getElementById("movetxt").textContent=d.moving+" real events · Bill→GenePool trains: "+d.bill_gp;
}
tick();setInterval(tick,2500);
</script></body></html>"""


import urllib.request as _urlreq


def _post(url, payload):
    try:
        req = _urlreq.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with _urlreq.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def command(payload):
    """Interactive control room: click a station -> a REAL command."""
    st = payload.get("station")
    action = payload.get("action")
    text = (payload.get("text") or "").strip()[:600]
    if action == "route_job":
        r = _post("http://127.0.0.1:8860/api/submit_job", {"task": text or "default"})
        return {"ok": r.get("ok", True), "result": "routed a job through the Gene Pool", "detail": str(r)[:220]}
    if action == "book_task":
        import sys
        sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
        try:
            import qsb_council_tasks as C
            r = C.create(text or "Ross task via control room", "", "ross_knechtel")
            tid = r.get("task_id") if isinstance(r, dict) else r
            return {"ok": True, "result": "booked Task Council task " + str(tid)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:160]}
    if action == "message":
        r = _post("http://127.0.0.1:8852/api/post", {"from": "ross", "target": st, "text": text or "hello from Ross"})
        return {"ok": r.get("ok", True), "result": "message sent to " + str(st)}
    return {"ok": False, "error": "unknown action"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        if self.path.startswith("/api/command"):
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                payload = {}
            b = json.dumps(command(payload)).encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            self.send_response(404); self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/data"):
            b = json.dumps(build()).encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            b = PAGE.encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8875)
    a = ap.parse_args()
    print(f"tower tube map on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
