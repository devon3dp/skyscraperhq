#!/usr/bin/env python3
"""
qsb_gene_pool_dash.py — LIVE, INTERACTIVE Gene Pool control room (Floor 24).

2026-07-28, Ross: "gene pool dash needs to be a lot more informative and interactive
so I can override / make them compulsory, buttons ... show who's accessing what, how
the gene pool's working, where the info's going, who's asking, who's getting ... a
live flow diagram ... totally live. No demos, everything real."

EVERYTHING REAL — sourced from the live ledgers + the live router:
  - real routing flow : data/registries/qsb_brain_router_calls.jsonl  (caller -> provider, latency, cost)
  - advisory/spend    : data/registries/qsb_provider_spend_ledger.jsonl
  - provider/key state: data/registries/gene_pool_router_state.json
  - participants       : data/registries/qsb_gene_pool_participants.json
  - control (override) : data/registries/qsb_gene_pool_control.json   (READ by the router at route-time)
INTERACTIVE (all hit REAL targets):
  - Set/clear a FORCED provider, DISABLE providers, COMPULSORY mode -> writes the control
    file the router enforces.
  - "Send a real job" -> POST :8860/api/submit_job (a real route you can watch appear).
  - "Rescan keys"     -> POST :8860/api/rescan.
Additive service on :8873.  Run: python3 tools/qsb_gene_pool_dash.py --port 8873
"""
import json, argparse, socket, urllib.request, urllib.error
from collections import deque, Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import time as _time

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
CARD = ROOT / "floors" / "floor_24_gene_pool" / "floor_card.json"
GENE = REG / "gene_pool_router_state.json"
PARTICIPANTS = REG / "qsb_gene_pool_participants.json"
CALLS = REG / "qsb_brain_router_calls.jsonl"
SPEND = REG / "qsb_provider_spend_ledger.jsonl"
CONTROL = REG / "qsb_gene_pool_control.json"
ROUTER = "http://127.0.0.1:8860"

PROVIDERS_ALL = ["openai", "deepseek", "claude", "gemini", "kimi", "groq", "grok", "cohere"]
DEFAULT_CONTROL = {"enabled": False, "forced_provider": None, "disabled_providers": [],
                   "compulsory": False, "set_by": None, "ts": None,
                   "note": "Router reads this at route-time. enabled=false -> normal policy."}


def _load(p, d):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


def _tail(path, n):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return list(deque(f, maxlen=n))
    except Exception:
        return []


def _port_up(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except Exception:
        return False


def _router_live():
    """Pull the router's rich live streams (event log, latest decision, CEO panels)."""
    try:
        with urllib.request.urlopen(ROUTER + "/api/live", timeout=1.5) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}


def load_control():
    c = dict(DEFAULT_CONTROL)
    c.update(_load(CONTROL, {}) or {})
    return c


def _flow_events(n=700):
    """Unified REAL flow: caller -> provider, from the router call log + spend ledger."""
    ev = []
    for ln in _tail(CALLS, n):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        ev.append({"ts": r.get("ts", ""), "caller": r.get("caller") or "?",
                   "task": r.get("task", ""), "provider": r.get("provider_used") or r.get("provider") or "?",
                   "model": r.get("model_used") or r.get("model", ""),
                   "latency": r.get("latency_s"), "cost": r.get("cost_usd_est") or r.get("cost_usd"),
                   "claude_avoided": r.get("claude_avoided"), "src": "router"})
    for ln in _tail(SPEND, 300):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        reason = (r.get("reason") or "?")
        ev.append({"ts": r.get("ts", ""), "caller": reason.split("_")[0] if reason else "?",
                   "task": reason, "provider": r.get("provider") or "?", "model": r.get("model", ""),
                   "latency": None, "cost": r.get("cost_usd"),
                   "claude_avoided": None, "src": "advisory"})
    ev.sort(key=lambda e: e["ts"])
    return ev


_VER = str(int(_time.time()))


def build_data():
    card = _load(CARD, {}) or {}
    gp = _load(GENE, {}) or {}
    met = gp.get("metrics", {}) or {}
    auto = met.get("autonomy", {}) or {}
    providers = gp.get("providers", {}) or {}
    prov = []
    for name, v in providers.items():
        keys = v.get("keys", v.get("key_count", 0)) if isinstance(v, dict) else 0
        if isinstance(keys, list):
            keys = len(keys)
        prov.append({"name": name, "keys": keys or 0})
    prov.sort(key=lambda x: -x["keys"])

    ev = _flow_events()
    recent = ev[-350:]
    callers = Counter(e["caller"] for e in recent)
    provs = Counter(e["provider"] for e in recent if e["provider"] != "?")
    edges = Counter((e["caller"], e["provider"]) for e in recent if e["provider"] != "?")
    costs = [e["cost"] for e in recent if isinstance(e["cost"], (int, float))]
    lats = [e["latency"] for e in recent if isinstance(e["latency"], (int, float))]
    avoided = sum(1 for e in recent if e["claude_avoided"] is True)

    parts_raw = _load(PARTICIPANTS, {}) or {}
    pmap = parts_raw.get("participants", parts_raw) if isinstance(parts_raw, dict) else {}
    participants = [{"id": k, "floor": v.get("floor"), "provider": v.get("provider"),
                     "lane": v.get("lane"), "status": v.get("status")}
                    for k, v in (pmap.items() if isinstance(pmap, dict) else []) if isinstance(v, dict)]

    return {
        "ver": _VER,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "floor_no": card.get("floor_number", 24),
        "name": card.get("floor_name", "Gene Pool"),
        "kpis": {
            "window": len(recent),
            "cost_window": round(sum(costs), 4),
            "avg_latency": round(sum(lats) / len(lats), 2) if lats else None,
            "claude_avoided": avoided,
            "stored_keys": met.get("stored_key_count") or auto.get("stored_key_count") or sum(p["keys"] for p in prov),
            "active_providers": met.get("active_provider_count") or auto.get("active_provider_count"),
            "autonomy": auto.get("enabled"),
            "last_scan": auto.get("last_scan"),
        },
        "flow": {
            "callers": callers.most_common(8),
            "providers": provs.most_common(8),
            "edges": [{"from": a, "to": b, "n": n} for (a, b), n in edges.most_common(40)],
        },
        "providers": prov,
        "participants": participants,
        "feed": [{"ts": e["ts"][11:19], "caller": e["caller"], "task": e["task"][:26],
                  "provider": e["provider"], "model": e["model"], "latency": e["latency"],
                  "cost": e["cost"], "avoided": e["claude_avoided"], "src": e["src"]}
                 for e in reversed(recent[-40:])],
        "control": load_control(),
        "routers": {"central_8860": _port_up(8860), "msi_8890": _port_up(8890)},
        "providers_all": PROVIDERS_ALL,
    }


# ── interactive actions (all REAL) ────────────────────────────────────────────
def set_control(payload):
    c = load_control()
    if "forced_provider" in payload:
        fp = payload["forced_provider"] or None
        c["forced_provider"] = fp if fp in PROVIDERS_ALL else None
    if "disabled_providers" in payload:
        c["disabled_providers"] = [p for p in payload["disabled_providers"] if p in PROVIDERS_ALL]
    if "compulsory" in payload:
        c["compulsory"] = bool(payload["compulsory"])
    if "enabled" in payload:
        c["enabled"] = bool(payload["enabled"])
    c["set_by"] = "ross"
    c["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    CONTROL.write_text(json.dumps(c, indent=2), encoding="utf-8")
    return {"ok": True, "control": c}


def _router_post(path, payload):
    try:
        req = urllib.request.Request(ROUTER + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"router {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def submit_job(payload):
    return _router_post("/api/submit_job", {"task": payload.get("task", "default")})


def rescan():
    return _router_post("/api/rescan", {})


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>Gene Pool Control · #24</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b0f17;--card:#131a26;--line:#233146;--txt:#dce6f5;--dim:#7d8da6;--gene:#8a5cf6;--ok:#39d98a;--warn:#f5c451;--bad:#ff6b6b;--acc:#5aa9ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:18px}
h1{margin:0;font-size:21px}h1 .n{color:var(--gene)}
.sub{color:var(--dim);margin:2px 0 12px;font-style:italic}
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 14px}
.kpi .v{font-size:20px;font-weight:700}.kpi .l{color:var(--dim);font-size:10px;text-transform:uppercase}
.cols{display:grid;grid-template-columns:1.5fr 1fr;gap:14px}@media(max-width:900px){.cols{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px}
.card h2{margin:0 0 10px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--dim)}
#flow{width:100%;height:340px}
.legend{display:flex;justify-content:space-between;color:var(--dim);font-size:11px;margin-top:4px}
.ctl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
select,input{background:#0d1420;border:1px solid var(--line);border-radius:8px;color:var(--txt);padding:7px 9px;font-size:13px}
button{border:0;border-radius:8px;padding:8px 13px;font-weight:700;cursor:pointer;font-size:13px}
.b-set{background:var(--gene);color:#fff}.b-go{background:var(--ok);color:#04120d}.b-scan{background:var(--acc);color:#04101f}.b-clear{background:transparent;border:1px solid var(--line);color:var(--dim);font-weight:400}
.provtog{display:inline-flex;gap:5px;align-items:center;border:1px solid var(--line);border-radius:999px;padding:3px 9px;cursor:pointer;font-size:12px;user-select:none}
.provtog.off{opacity:.45;text-decoration:line-through}
.state{font-size:12px;padding:8px;border:1px solid var(--line);border-radius:8px;background:#0d1420;margin-top:6px}
.state.on{border-color:var(--warn)}
.on-badge{color:var(--warn);font-weight:700}
table{width:100%;border-collapse:collapse;font-size:11px}
th,td{text-align:left;padding:4px 7px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--dim);text-transform:uppercase;font-size:9px;position:sticky;top:0;background:#0f1622}
.feedwrap{max-height:360px;overflow:auto}
.prov{color:var(--gene);font-weight:600}.caller{color:var(--acc)}.mono{font-family:ui-monospace,monospace;color:var(--dim)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}.up{background:var(--ok)}.down{background:var(--bad)}
.pill{font-size:11px;color:var(--dim)}
footer{color:var(--dim);margin-top:12px;font-size:11px}
</style></head><body><div class=wrap>
<h1>Gene Pool <span class=n>· Control Room · #24</span></h1>
<div class=sub>Live routing — who's asking, who's serving, where it flows. Every number real.</div>
<div class=kpis>
  <div class=kpi><div class=v id=kWin>—</div><div class=l>calls (live window)</div></div>
  <div class=kpi><div class=v id=kCost>—</div><div class=l>$ window</div></div>
  <div class=kpi><div class=v id=kLat>—</div><div class=l>avg latency</div></div>
  <div class=kpi><div class=v id=kAvoid>—</div><div class=l>claude avoided</div></div>
  <div class=kpi><div class=v id=kKeys>—</div><div class=l>keys</div></div>
  <div class=kpi><div class=v id=kProv>—</div><div class=l>providers</div></div>
</div>
<div class=cols>
  <div>
    <div class=card><h2>Live flow · callers → Gene Pool → providers</h2>
      <svg id=flow></svg><div class=legend><span>who's asking</span><span>Gene Pool</span><span>who's serving</span></div></div>
    <div class=card><h2>Live access feed (real routes)</h2><div class=feedwrap><table>
      <thead><tr><th>time</th><th>caller</th><th>task</th><th>provider</th><th>model</th><th>lat</th><th>$</th></tr></thead>
      <tbody id=feed></tbody></table></div></div>
  </div>
  <div>
    <div class=card><h2>⚡ Override controls (real — router enforces)</h2>
      <div class=ctl><span class=pill>force provider:</span>
        <select id=force></select>
        <label class=pill><input type=checkbox id=compulsory> compulsory (only forced)</label>
      </div>
      <div class=ctl id=provtogs></div>
      <div class=ctl>
        <button class=b-set onclick=applyControl(true)>Apply override</button>
        <button class=b-clear onclick=applyControl(false)>Clear / normal policy</button>
      </div>
      <div id=cstate class=state>—</div>
    </div>
    <div class=card><h2>▶ Drive the pool (real)</h2>
      <div class=ctl><span class=pill>task:</span>
        <select id=jobtask><option>default</option><option>coding</option><option>architecture</option><option>summary</option><option>cheap</option></select>
        <button class=b-go onclick=sendJob()>Send real job</button>
        <button class=b-scan onclick=doRescan()>Rescan keys</button>
      </div>
      <div id=jobout class=state>—</div>
    </div>
    <div class=card><h2>Providers · Participants · Routers</h2>
      <div id=provlist></div>
      <div id=partlist style="margin-top:8px"></div>
      <div id=routerlist style="margin-top:8px"></div>
    </div>
  </div>
</div>
<footer>read = live ledgers · write = real router/control · auto-refresh 4s · <span id=ts></span> · :8873</footer>
</div><script>
const NS='http://www.w3.org/2000/svg';
function esc(s){return (''+(s==null?'':s)).replace(/</g,'&lt;')}
function el(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e}
let DATA=null;
function drawFlow(d){
  const svg=document.getElementById('flow');svg.innerHTML='';
  const W=svg.clientWidth||600,H=340;svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const callers=d.flow.callers, provs=d.flow.providers;
  const cx1=90, cxm=W/2, cx2=W-90;
  const cy=n=>({});
  const cpos={}, ppos={};
  callers.forEach((c,i)=>cpos[c[0]]=40+i*(H-70)/Math.max(1,callers.length-1||1));
  provs.forEach((p,i)=>ppos[p[0]]=40+i*(H-70)/Math.max(1,provs.length-1||1));
  const maxE=Math.max(1,...d.flow.edges.map(e=>e.n));
  // edges caller->hub->provider
  d.flow.edges.forEach(e=>{
    if(cpos[e.from]==null||ppos[e.to]==null)return;
    const w=1+5*e.n/maxE, op=.2+.6*e.n/maxE;
    const p1=el('path',{d:`M ${cx1} ${cpos[e.from]} C ${(cx1+cxm)/2} ${cpos[e.from]}, ${(cx1+cxm)/2} ${H/2}, ${cxm} ${H/2}`,stroke:'#8a5cf6','stroke-width':w,fill:'none','stroke-opacity':op,'stroke-linecap':'round'});
    p1.setAttribute('class','flowline');svg.appendChild(p1);
    const p2=el('path',{d:`M ${cxm} ${H/2} C ${(cxm+cx2)/2} ${H/2}, ${(cxm+cx2)/2} ${ppos[e.to]}, ${cx2} ${ppos[e.to]}`,stroke:'#5aa9ff','stroke-width':w,fill:'none','stroke-opacity':op,'stroke-linecap':'round'});
    p2.setAttribute('class','flowline');svg.appendChild(p2);
  });
  // hub
  svg.appendChild(el('circle',{cx:cxm,cy:H/2,r:26,fill:'#131a26',stroke:'#8a5cf6','stroke-width':2}));
  const ht=el('text',{x:cxm,y:H/2+4,'text-anchor':'middle',fill:'#8a5cf6','font-size':11,'font-weight':700});ht.textContent='POOL';svg.appendChild(ht);
  // nodes
  callers.forEach(c=>{svg.appendChild(el('circle',{cx:cx1,cy:cpos[c[0]],r:5,fill:'#5aa9ff'}));
    const t=el('text',{x:cx1-10,y:cpos[c[0]]+4,'text-anchor':'end',fill:'#dce6f5','font-size':11});t.textContent=c[0]+' ('+c[1]+')';svg.appendChild(t);});
  provs.forEach(p=>{svg.appendChild(el('circle',{cx:cx2,cy:ppos[p[0]],r:5,fill:'#8a5cf6'}));
    const t=el('text',{x:cx2+10,y:ppos[p[0]]+4,fill:'#dce6f5','font-size':11});t.textContent=p[0]+' ('+p[1]+')';svg.appendChild(t);});
}
async function tick(){
  let d;try{d=await (await fetch('/api/data')).json()}catch(e){return}
  if(window.__v&&window.__v!==d.ver){location.reload();return}window.__v=d.ver;
  DATA=d;const k=d.kpis;
  kWin.textContent=k.window;kCost.textContent='$'+k.cost_window;kLat.textContent=(k.avg_latency==null?'—':k.avg_latency+'s');
  kAvoid.textContent=k.claude_avoided;kKeys.textContent=k.stored_keys;kProv.textContent=k.active_providers;
  drawFlow(d);
  feed.innerHTML=d.feed.map(r=>`<tr><td class=mono>${esc(r.ts)}</td><td class=caller>${esc(r.caller)}</td><td class=mono>${esc(r.task)}</td><td class=prov>${esc(r.provider)}</td><td class=mono>${esc(r.model)}</td><td class=mono>${r.latency==null?'':r.latency+'s'}</td><td class=mono>${r.cost==null?'':'$'+(+r.cost).toFixed(4)}</td></tr>`).join('');
  // controls (only rebuild if not focused)
  if(!window.__ctlInit){
    const f=document.getElementById('force');f.innerHTML='<option value="">— none —</option>'+d.providers_all.map(p=>`<option>${p}</option>`).join('');
    provtogs.innerHTML='<span class=pill>disable:</span>'+d.providers_all.map(p=>`<span class="provtog" data-p="${p}" onclick="this.classList.toggle('off')">${p}</span>`).join('');
    window.__ctlInit=true;
    const c=d.control; f.value=c.forced_provider||''; document.getElementById('compulsory').checked=!!c.compulsory;
    (c.disabled_providers||[]).forEach(p=>{const t=document.querySelector('.provtog[data-p="'+p+'"]');if(t)t.classList.add('off')});
  }
  const c=d.control;const cs=document.getElementById('cstate');
  cs.className='state'+(c.enabled?' on':'');
  cs.innerHTML=c.enabled?`<span class=on-badge>OVERRIDE ACTIVE</span> · forced=<b>${esc(c.forced_provider)||'none'}</b> · compulsory=${c.compulsory} · disabled=[${(c.disabled_providers||[]).join(', ')}] · by ${esc(c.set_by)} ${esc((c.ts||'').slice(11,19))}`:'normal policy (no override)';
  provlist.innerHTML='<b class=pill>PROVIDERS</b> '+d.providers.map(p=>`<span class=pill>${p.name}:${p.keys}</span>`).join(' ');
  partlist.innerHTML='<b class=pill>PARTICIPANTS</b> '+d.participants.map(p=>`<span class=pill>${esc(p.id)}·#${esc(p.floor)}·${esc(p.provider)}</span>`).join(' ')||'';
  routerlist.innerHTML=`<b class=pill>ROUTERS</b> <span class=pill><span class="dot ${d.routers.central_8860?'up':'down'}"></span>:8860</span> <span class=pill><span class="dot ${d.routers.msi_8890?'up':'down'}"></span>:8890</span>`;
  ts.textContent=(d.ts||'').replace('T',' ');
}
async function applyControl(enabled){
  const forced=document.getElementById('force').value;
  const compulsory=document.getElementById('compulsory').checked;
  const disabled=[...document.querySelectorAll('.provtog.off')].map(t=>t.dataset.p);
  const r=await (await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled,forced_provider:forced,compulsory,disabled_providers:disabled})})).json();
  document.getElementById('cstate').innerHTML=r.ok?'saved — router will enforce on next route':'error';
  tick();
}
async function sendJob(){
  const jo=document.getElementById('jobout');jo.textContent='routing…';
  const r=await (await fetch('/api/submit_job',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:document.getElementById('jobtask').value})})).json();
  jo.textContent=JSON.stringify(r).slice(0,300);tick();
}
async function doRescan(){
  const jo=document.getElementById('jobout');jo.textContent='rescanning…';
  const r=await (await fetch('/api/rescan',{method:'POST'})).json();
  jo.textContent=r.ok?('rescanned — '+((r.metrics||{}).stored_key_count||'?')+' keys'):('error '+(r.error||''));tick();
}
tick();setInterval(tick,4000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/data"):
            self._send(build_data())
        else:
            b = PAGE.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            payload = {}
        if self.path.startswith("/api/control"):
            self._send(set_control(payload))
        elif self.path.startswith("/api/submit_job"):
            self._send(submit_job(payload))
        elif self.path.startswith("/api/rescan"):
            self._send(rescan())
        else:
            self._send({"ok": False, "error": "not found"}, 404)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8873)
    a = ap.parse_args()
    print(f"gene pool control room on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
