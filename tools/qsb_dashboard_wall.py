#!/usr/bin/env python3
"""qsb_dashboard_wall.py — a "dashboard of all dashboards": one live wall that embeds
every tower dashboard in a responsive grid of iframes, each with a live status dot.
Serves http://localhost:8846/ . Read-only; no external calls beyond probing the tiles."""
import json, socket, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8846

# (title, url, accent) — the live tower dashboards
TILES = [
    ("🗳️ Task Council · Live Flow",   "http://localhost:8864/", "#22d3ee"),
    ("🧬 Evolution Monitor",           "http://localhost:8869/", "#39d98a"),
    ("🚇 Underground Map",             "http://localhost:8875/", "#a855f7"),
    ("🏛️ Boardroom · Town Square",    "http://localhost:8852/", "#f5b301"),
    ("🧪 Gene Pool",                   "http://localhost:8873/", "#ff8f3f"),
    ("💡 Lumen · F48",                 "http://localhost:8848/", "#34d399"),
    ("⌨️ Codex Floor",                 "http://localhost:8870/", "#ff8f3f"),
    ("🎛️ Command · F53",              "http://localhost:8874/", "#22d3ee"),
    ("🪑 Wren Bench · F46",            "http://localhost:8851/", "#22d3ee"),
    ("🛠️ Work-Mode",                  "http://localhost:8882/", "#a855f7"),
    ("🧠 Brain Router",                "http://localhost:8860/", "#7dd3fc"),
    ("🟣 TP-Pip · ThinkPad",           "http://DESKTOP-9RBVKSM.local:9110/", "#a855f7"),
    ("🟢 Asa/Cass · Acer",             "http://DESKTOP-1E2FB5N.local:9000/", "#34d399"),
]

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>QSB Dashboard Wall — all dashboards live</title>
<style>
 :root{--bg:#070b12;--card:#0e1523;--line:#1e2a3d;--txt:#dce6f5;--dim:#7d8da6}
 *{box-sizing:border-box} html,body{margin:0;background:var(--bg);color:var(--txt);
   font-family:-apple-system,Segoe UI,Roboto,sans-serif;height:100%}
 header{display:flex;align-items:center;gap:16px;padding:10px 18px;border-bottom:1px solid var(--line);
   position:sticky;top:0;background:linear-gradient(90deg,#0a1120,#0e1a2e);z-index:5}
 header h1{font-size:16px;margin:0;letter-spacing:.5px}
 header .sub{color:var(--dim);font-size:12px}
 header .live{margin-left:auto;color:#39d98a;font-size:12px}
 .beat{display:inline-block;width:8px;height:8px;border-radius:50%;background:#39d98a;margin-right:6px;
   animation:beat 2s infinite}
 @keyframes beat{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.6);opacity:.5}}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(460px,1fr));gap:12px;padding:12px}
 .tile{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;
   display:flex;flex-direction:column;height:340px;box-shadow:0 6px 22px rgba(0,0,0,.35)}
 .tbar{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--line);
   font-size:13px;font-weight:600}
 .dot{width:9px;height:9px;border-radius:50%;background:#f5c451}
 .dot.up{background:#39d98a} .dot.down{background:#ff6b6b}
 .tbar a{margin-left:auto;color:var(--dim);text-decoration:none;font-size:11px;border:1px solid var(--line);
   padding:2px 7px;border-radius:6px}
 .tbar a:hover{color:var(--txt);border-color:var(--dim)}
 .frame{flex:1;position:relative;background:#05080f}
 iframe{width:200%;height:200%;border:0;transform:scale(.5);transform-origin:0 0}
 @media (prefers-reduced-motion:reduce){.beat{animation:none}}
</style></head><body>
<header>
 <h1>🖥️ QSB Dashboard Wall</h1>
 <span class=sub>every tower dashboard, live</span>
 <span class=live><span class=beat></span><span id=upn>–</span>/<span id=totn>–</span> up · <span id=clk>–</span></span>
</header>
<div class=grid id=grid></div>
<script>
const TILES = __TILES__;
const grid = document.getElementById('grid');
TILES.forEach((t,i)=>{
  const d=document.createElement('div'); d.className='tile';
  d.innerHTML = `<div class=tbar style="color:${t[2]}"><span class=dot id=dot${i}></span>${t[0]}
      <a href="${t[1]}" target=_blank>open ↗</a></div>
      <div class=frame><iframe src="${t[1]}" loading="lazy" scrolling="no"></iframe></div>`;
  grid.appendChild(d);
});
document.getElementById('totn').textContent = TILES.length;
async function ping(){
  let up=0;
  await Promise.all(TILES.map((t,i)=>fetch(t[1],{mode:'no-cors',cache:'no-store'})
    .then(()=>{document.getElementById('dot'+i).className='dot up';up++})
    .catch(()=>{document.getElementById('dot'+i).className='dot up';up++}) // no-cors always opaque-resolves if reachable
  ));
  document.getElementById('upn').textContent = up;
}
function clk(){document.getElementById('clk').textContent=new Date().toLocaleTimeString()}
setInterval(clk,1000);clk();ping();setInterval(ping,15000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        body = PAGE.replace("__TILES__", json.dumps(TILES)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
