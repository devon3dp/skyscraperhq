#!/usr/bin/env python3
"""
qsb_knowledge_dash.py — LIVE read-only view of the tower's LEARNING layer (:8866).

2026-07-29, Ross: "make the tower LEARN ... show it accumulating". This surfaces
data/registries/qsb_knowledge.jsonl — the real, deduped learnings the workers + council
produce — so you can SEE the knowledge base grow: total entries, entries per source/topic,
learnings-per-day, most-reaffirmed lines, and the newest entries with their real timestamps.

EVERYTHING REAL: every number and line comes straight from qsb_knowledge (which only ever
stores genuine worker output). No demo rows. Read-only. Auto-refreshes every 5s.

Endpoints:
    /                -> HTML dashboard
    /api/knowledge   -> {summary, recent[], reaffirmed[]}  (JSON)

systemd: qsb-knowledge-dash.service (Type=simple). Run: python3 tools/qsb_knowledge_dash.py
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import qsb_knowledge as KB  # noqa: E402

PORT = 8866
VER = str(int(time.time()))  # bumps on restart -> clients auto-reload


def _payload():
    summ = KB.summary()
    recent = KB.recent(40)
    reaffirmed = sorted(
        [r for r in KB._load_all() if int(r.get("seen", 1)) > 1],
        key=lambda r: int(r.get("seen", 1)), reverse=True,
    )[:15]
    return {"ver": VER, "summary": summ, "recent": recent, "reaffirmed": reaffirmed}


HTML = """<!doctype html><html><head><meta charset=utf-8>
<title>QSB Tower — Knowledge Base</title>
<style>
 body{background:#0b0f14;color:#d6e2f0;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:22px}
 h1{font-size:20px;margin:0 0 4px}.sub{color:#7f95ab;font-size:12px;margin-bottom:18px}
 .cards{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:20px}
 .card{background:#131a22;border:1px solid #1e2a36;border-radius:10px;padding:14px 18px;min-width:120px}
 .card .n{font-size:28px;font-weight:700;color:#5ee6a8}.card .l{font-size:11px;color:#7f95ab;text-transform:uppercase;letter-spacing:.5px}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
 @media(max-width:900px){.grid{grid-template-columns:1fr}}
 .panel{background:#131a22;border:1px solid #1e2a36;border-radius:10px;padding:14px 16px}
 .panel h2{font-size:13px;color:#9fb4c9;margin:0 0 10px;text-transform:uppercase;letter-spacing:.5px}
 .row{padding:8px 0;border-bottom:1px solid #18222c}.row:last-child{border:0}
 .meta{color:#6f849a;font-size:11px}
 .tag{display:inline-block;background:#1c2a38;color:#8fd3ff;border-radius:4px;padding:1px 6px;font-size:10px;margin-left:4px}
 .seen{color:#f0b45e;font-size:11px}
 .bar{display:flex;align-items:center;gap:8px;margin:4px 0}
 .bar .b{height:10px;background:#2b6a52;border-radius:3px}.bar .k{width:110px;color:#9fb4c9;font-size:12px}.bar .v{color:#5ee6a8;font-size:12px}
 .txt{color:#d6e2f0}
</style></head><body>
<h1>🧠 QSB Tower — Knowledge Base</h1>
<div class=sub>Real, deduped learnings the workers + council actually produced. Auto-refresh 5s. <span id=ts></span></div>
<div class=cards id=cards></div>
<div class=grid>
 <div class=panel><h2>Newest learnings</h2><div id=recent></div></div>
 <div>
  <div class=panel style="margin-bottom:20px"><h2>By source</h2><div id=bysrc></div></div>
  <div class=panel style="margin-bottom:20px"><h2>By topic</h2><div id=bytopic></div></div>
  <div class=panel style="margin-bottom:20px"><h2>Learnings per day</h2><div id=byday></div></div>
  <div class=panel><h2>Most reaffirmed (dedup at work)</h2><div id=reaff></div></div>
 </div>
</div>
<script>
let VER=null;
function bars(el,obj){
 const max=Math.max(1,...Object.values(obj));
 el.innerHTML=Object.entries(obj).map(([k,v])=>
   `<div class=bar><div class=k>${k}</div><div class=b style="width:${20+180*v/max}px"></div><div class=v>${v}</div></div>`).join('')||'<div class=meta>none yet</div>';
}
async function tick(){
 let d; try{d=await (await fetch('/api/knowledge')).json();}catch(e){return;}
 if(VER&&d.ver!==VER){location.reload();return;} VER=d.ver;
 const s=d.summary;
 document.getElementById('ts').textContent='· last entry '+(s.last_ts||'—');
 document.getElementById('cards').innerHTML=[
   ['entries',s.total_entries],['observations absorbed',s.total_observations],
   ['reaffirmed',s.reaffirmed_entries],['sources',Object.keys(s.by_source).length],
   ['topics',Object.keys(s.by_topic).length]
 ].map(([l,n])=>`<div class=card><div class=n>${n}</div><div class=l>${l}</div></div>`).join('');
 document.getElementById('recent').innerHTML=d.recent.map(r=>
   `<div class=row><div class=txt>${esc(r.text)}</div><div class=meta>${r.ts} · <b>${r.source}</b><span class=tag>${r.topic}</span><span class=tag>${r.kind}</span>${r.seen>1?` <span class=seen>seen x${r.seen}</span>`:''}</div></div>`
 ).join('')||'<div class=meta>no learnings yet — run a worker cycle</div>';
 bars(document.getElementById('bysrc'),s.by_source);
 bars(document.getElementById('bytopic'),s.by_topic);
 bars(document.getElementById('byday'),s.by_day);
 document.getElementById('reaff').innerHTML=d.reaffirmed.map(r=>
   `<div class=row><div class=txt>${esc(r.text)}</div><div class=meta><span class=seen>seen x${r.seen}</span> · <b>${r.source}</b><span class=tag>${r.topic}</span></div></div>`
 ).join('')||'<div class=meta>nothing reaffirmed yet</div>';
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
tick();setInterval(tick,5000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/knowledge"):
            body = json.dumps(_payload()).encode()
            self._send(200, body, "application/json")
            return
        self._send(200, HTML.encode(), "text/html; charset=utf-8")


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print(f"[knowledge-dash] serving http://0.0.0.0:{PORT}  (ver {VER})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
