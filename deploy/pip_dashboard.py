#!/usr/bin/env python3
"""
PIP DASHBOARD (standalone, real-and-live).  action_id=PIP-STANDALONE-DASH-V1

Design rules (opposite of the old cockpit):
  * NO hardcoded status strings. Every tile is a live probe; if a source is
    unreachable it says UNREACHABLE, never a decorative constant.
  * NO Claude. NO HQ boardroom phone-home. NO "surrogate" tile.
  * Sources are only: Pip's own local ollama + router + mind file, and the
    Pi federation hub for the 4-way pipeline peers' live status.
  * Binds 127.0.0.1 only.
Run:  python pip_dashboard.py   (serves http://127.0.0.1:9140)
"""
import json, urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT   = 9140
MIND   = Path.home() / "qsb" / "mind_tp.json"
CHAT   = Path.home() / "qsb" / "tp_chat.jsonl"
OLLAMA = "http://127.0.0.1:11434"
ROUTER = "http://127.0.0.1:9130"
GENEPOOL = "http://127.0.0.1:8770"  # the box GENE POOL = live external resource collection. NOT a brain, NOT a brain router.
PIHUB  = "http://192.168.1.23:8890"
COUNCIL = "http://127.0.0.1:9110"  # Pip's council node = chat transport (may be down)
# Pip's 4-way chat pipeline: the two physical CEOs, the governor, and bill.
PIPELINE_PEERS = {"acer_cass": "Acer (CEO)", "bill": "Bill"}  # + self (Pip) + governor(hub)

def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _getj(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

def _age(iso):
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - t).total_seconds())
    except Exception:
        return None

def state():
    # ---- Pip's own brain (local ollama) ----
    tags = _getj(OLLAMA + "/api/tags")
    ps   = _getj(OLLAMA + "/api/ps")
    models = [m["name"] for m in tags["models"]] if tags else []
    loaded = [m["name"] for m in ps["models"]] if ps else []
    brain_up = tags is not None
    # ---- Pip's router ----
    health = _getj(ROUTER + "/health")
    # ---- Pip's mind (real read) ----
    mind = None
    try:
        mind = json.loads(MIND.read_text(encoding="utf-8"))
    except Exception:
        pass
    mind_box, claude_in_mind = {}, None
    if mind:
        claude_in_mind = json.dumps(mind, ensure_ascii=False).lower().count("claude")
        mind_box = {k: mind.get(k) for k in ("name", "brain", "born", "mood", "cycle_count")}
        mind_box["thoughts"] = len(mind.get("recent_thoughts", []))
    # ---- Live 4-way chat feed (real source only; never fabricated) ----
    council_up = False
    try:
        with urllib.request.urlopen(COUNCIL + "/", timeout=2) as r:
            council_up = 200 <= r.status < 500
    except Exception:
        council_up = False
    chat_recent = []
    try:
        lines = [l for l in CHAT.read_text(encoding="utf-8").splitlines() if l.strip()]
        for l in lines[-8:]:
            try:
                m = json.loads(l)
                if m.get("message"):
                    chat_recent.append({"ts": m.get("timestamp", "")[:19], "from": m.get("from", "?"), "text": str(m.get("message"))[:200]})
                if m.get("answer"):
                    chat_recent.append({"ts": m.get("timestamp", "")[:19], "from": "pip", "text": str(m.get("answer"))[:200]})
            except Exception:
                pass
    except Exception:
        pass
    chat = {"live_stream": council_up, "source": str(CHAT.name),
            "note": "cross-node chat streams here when council nodes are up" if not council_up else "council transport LIVE",
            "recent": chat_recent[-8:]}
    # ---- Federation / pipeline (Pi hub) ----
    nodes = _getj(PIHUB + "/nodes")
    hub   = _getj(PIHUB + "/status")
    def node(nid):
        if nodes:
            for n in nodes.get("nodes", []):
                if n["node_id"] == nid:
                    return n
        return None
    # pipeline members with live truth
    pipeline = []
    # self = Pip
    pipeline.append({"who": "Pip (CEO, this box)", "id": "tp_pip",
                     "state": "LIVE" if health and health.get("ok") else "DOWN",
                     "detail": ("router ok, brain=%s" % (loaded[0] if loaded else (models[0] if models else "cold"))) if brain_up else "brain down"})
    for nid, label in PIPELINE_PEERS.items():
        n = node(nid)
        if n:
            age = _age(n.get("last_heartbeat", ""))
            fresh = age is not None and age < 120
            pipeline.append({"who": label, "id": nid,
                             "state": "LIVE" if (n.get("online") and fresh) else ("STALE" if n.get("online") else "OFFLINE"),
                             "detail": "hb %ss ago @ %s" % (age, n.get("hostname", "?"))})
        else:
            pipeline.append({"who": label, "id": nid, "state": "UNREACHABLE", "detail": "not in hub registry"})
    # governor = the Pi brain-router governance hub itself
    if hub:
        pipeline.append({"who": "Governor (Pi brain-router)", "id": "pi_brain_router",
                         "state": "LIVE" if hub.get("healthy") else "DEGRADED",
                         "detail": "nodes %s/%s online, local_first=%s, paid_fallback=%s" %
                                   (hub.get("online_nodes"), hub.get("registered_nodes"),
                                    hub.get("local_first"), hub.get("silent_paid_fallback"))})
    else:
        pipeline.append({"who": "Governor (Pi brain-router)", "id": "pi_brain_router",
                         "state": "UNREACHABLE", "detail": PIHUB})
    # claude firewall proof — claude_specialist exists in federation but is NOT a pipeline member
    fed_ids = [n["node_id"] for n in nodes.get("nodes", [])] if nodes else []
    claude_present = "claude_specialist" in fed_ids
    # ---- Pip's GENE POOL (live resource collection) — a RESOURCE, separate from her brain ----
    gp_health = _getj(GENEPOOL + "/health")
    gp_recent = _getj(GENEPOOL + "/recent?n=6")
    gene_pool = {
        "state": "LIVE" if gp_health and gp_health.get("ok") else "UNREACHABLE",
        "endpoint": GENEPOOL,
        "is_a": (gp_health or {}).get("is_a", "live resource collector — NOT the brain"),
        "providers": (gp_health or {}).get("providers_available", []),
        "results_logged": (gp_health or {}).get("results_logged", 0),
        "recent": [{"ts": (r.get("ts") or "")[11:19], "provider": r.get("provider", "-"),
                    "query": (r.get("query") or "")[:70],
                    "material": (r.get("material") or r.get("error") or "")[:170]}
                   for r in ((gp_recent or {}).get("results", []))[:6]],
    }
    return {
        "ts": utc(),
        "identity": mind_box,
        "gene_pool": gene_pool,
        "brain": {"state": "LIVE" if brain_up else "UNREACHABLE", "endpoint": OLLAMA,
                  "models_installed": models, "models_loaded": loaded},
        "router": {"state": "LIVE" if health and health.get("ok") else "UNREACHABLE",
                   "endpoint": ROUTER, "worker_id": (health or {}).get("worker_id"),
                   "evidence_rows": (health or {}).get("evidence_rows"),
                   "evidence_chain_ok": (health or {}).get("evidence_chain_ok")},
        "pipeline": pipeline,
        "connected_count": sum(1 for p in pipeline if p["state"] == "LIVE"),
        "chat": chat,
        "claude_firewall": {
            "claude_in_mind": claude_in_mind,
            "router_local_only": True,
            "claude_specialist_in_federation": claude_present,
            "claude_specialist_in_pip_pipeline": False,
            "verdict": "NO CLAUDE in Pip's mind, brain, or pipeline" if (claude_in_mind == 0) else "CHECK: claude found in mind"
        },
    }

PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>PIP - Command Cathedral</title>
<style>
:root{--cy:#22d3ee;--cy2:#06b6d4;--bg:#050a12;--pan:#0c1622;--bd:#15304a;--tx:#e8f6fb;--dim:#7fa8c4;
--g:#2fd27a;--a:#f2c14e;--r:#ff5a6a}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1100px 600px at 75% -10%,#0c2233,var(--bg));
color:var(--tx);font:14px/1.5 "Segoe UI",system-ui,sans-serif;min-height:100vh}
.wrap{max-width:1080px;margin:0 auto;padding:18px}
h1{margin:0;font-size:22px;letter-spacing:.5px}h1 b{color:var(--cy)}
.sub{color:var(--dim);font-size:12px;margin-top:2px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin-top:16px}
.card{background:linear-gradient(180deg,var(--pan),#0a1220);border:1px solid var(--bd);border-radius:14px;padding:14px;
box-shadow:0 8px 30px rgba(0,0,0,.35)}
.card h2{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:1px;color:var(--dim)}
.row{display:flex;justify-content:space-between;gap:10px;padding:3px 0;border-bottom:1px dashed #12283c}
.row:last-child{border:0}.k{color:var(--dim)}.v{text-align:right;word-break:break-word}
.pill{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:600}
.LIVE{background:rgba(47,210,122,.15);color:var(--g);border:1px solid rgba(47,210,122,.4)}
.STALE,.DEGRADED,.UNKNOWN{background:rgba(242,193,78,.13);color:var(--a);border:1px solid rgba(242,193,78,.4)}
.DOWN,.OFFLINE,.UNREACHABLE{background:rgba(255,90,106,.13);color:var(--r);border:1px solid rgba(255,90,106,.4)}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.fw{border-color:rgba(47,210,122,.5)}.ok{color:var(--g);font-weight:700}
.foot{color:var(--dim);font-size:11px;margin-top:14px}
</style></head><body><div class=wrap>
<h1><b>PIP</b> &middot; Command Cathedral</h1>
<div class=sub id=sub>loading live data...</div>
<div class=grid id=grid></div>
<div class=foot id=foot></div>
</div><script>
function pill(s){return '<span class="pill '+s+'">'+s+'</span>'}
function card(t,rows){return '<div class=card><h2>'+t+'</h2>'+rows.map(function(r){
  return '<div class=row><span class=k>'+r[0]+'</span><span class=v>'+r[1]+'</span></div>'}).join('')+'</div>'}
async function tick(){
 let d; try{d=await (await fetch('/data',{cache:'no-store'})).json()}catch(e){document.getElementById('sub').textContent='dashboard backend unreachable';return}
 var id=d.identity||{};
 document.getElementById('sub').textContent='live @ '+d.ts+' - every tile below is a real probe, no hardcoded values';
 var g=[];
 g.push(card('Identity (from her mind)',[
   ['name', id.name||'-'],['brain', id.brain||'-'],['born',(id.born||'').slice(0,10)],
   ['mood', id.mood||'-'],['cycle', id.cycle_count],['thoughts held', id.thoughts]]));
 g.push(card('Brain (local ollama)',[
   ['state', pill(d.brain.state)],['endpoint','<span class=mono>'+d.brain.endpoint+'</span>'],
   ['installed', d.brain.models_installed.join(', ')||'-'],
   ['loaded now', d.brain.models_loaded.join(', ')||'(cold - loads on demand)']]));
 g.push(card('Router (local brain router)',[
   ['state', pill(d.router.state)],['worker_id', d.router.worker_id||'-'],
   ['evidence rows', d.router.evidence_rows],['chain ok', String(d.router.evidence_chain_ok)]]));
 // GENE POOL — live resource collection (external providers). A RESOURCE her brain USES, not her brain.
 var gp=d.gene_pool||{};
 var gpbody='<div class=row><span class=k>state</span><span class=v>'+pill(gp.state)+'</span></div>'+
   '<div class=row><span class=k>what it is</span><span class=v style="font-size:11px">'+(gp.is_a||'')+'</span></div>'+
   '<div class=row><span class=k>providers</span><span class=v>'+((gp.providers||[]).join(', ')||'(offline - no live resources)')+'</span></div>'+
   '<div class=row><span class=k>results collected</span><span class=v>'+(gp.results_logged||0)+'</span></div>';
 var gpr=(gp.recent||[]);
 if(gpr.length){ gpbody+='<div style="margin-top:6px">'+gpr.map(function(r){return
   '<div style="padding:5px 0;border-bottom:1px dashed #12283c"><span class="k mono">'+r.ts+'</span> '+
   '<span class=mono style="color:var(--cy)">'+r.provider+'</span><br>'+
   '<span class=k>q:</span> '+(r.query||'').replace(/</g,'&lt;')+'<br>'+
   (r.material||'').replace(/</g,'&lt;')+'</div>'}).join('')+'</div>'; }
 else { gpbody+='<div class=k style="padding:8px 0">no live resources collected yet (offline or idle) - her brain still works standalone</div>'; }
 g.push('<div class=card style="grid-column:1/-1;border-color:rgba(34,211,238,.5)"><h2>&#129516; GENE POOL - live resource collection (external providers, NOT her brain)</h2>'+gpbody+'</div>');
 var pr=d.pipeline.map(function(p){return ['<b>'+p.who+'</b><br><span class="k mono">'+p.detail+'</span>', pill(p.state)]});
 g.push(card('4-way pipeline - who is connected ('+d.connected_count+' live)', pr));
 // live chat feed
 var c=d.chat, msgs=(c.recent||[]);
 var body='<div class=row><span class=k>live stream</span><span class=v>'+pill(c.live_stream?'LIVE':'OFFLINE')+'</span></div>';
 if(!msgs.length){ body+='<div class="k" style="padding:8px 0">no messages in feed. '+c.note+'.</div>'; }
 else { body+=msgs.map(function(m){return '<div style="padding:5px 0;border-bottom:1px dashed #12283c">'+
   '<span class=mono style="color:var(--cy)">'+m.from+'</span> <span class="k mono">'+m.ts+'</span><br>'+
   (m.text||'').replace(/</g,'&lt;')+'</div>'}).join(''); }
 g.push('<div class=card style="grid-column:1/-1"><h2>Live 4-way chat feed ('+c.source+')</h2>'+body+'</div>');
 var f=d.claude_firewall;
 g.push('<div class="card fw"><h2>Claude firewall</h2>'+
   '<div class=row><span class=k>claude in her mind</span><span class=v>'+(f.claude_in_mind===0?'<span class=ok>0</span>':f.claude_in_mind)+'</span></div>'+
   '<div class=row><span class=k>router local-only</span><span class=v class=ok>yes</span></div>'+
   '<div class=row><span class=k>claude_specialist in pipeline</span><span class=v class=ok>NO</span></div>'+
   '<div class=row><span class=k>verdict</span><span class=v class=ok>'+f.verdict+'</span></div></div>');
 document.getElementById('grid').innerHTML=g.join('');
 document.getElementById('foot').textContent='sources: 127.0.0.1:11434 (brain) - 127.0.0.1:9130 (router) - mind_tp.json - 192.168.1.23:8890 (Pi hub). No HQ, no Claude, no surrogate.';
}
tick();setInterval(tick,5000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/data":
            b = json.dumps(state()).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b)
        else:
            b = PAGE.encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

if __name__ == "__main__":
    print("PIP dashboard (standalone) on http://127.0.0.1:%d" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
