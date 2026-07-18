#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import urllib.request
import json
import datetime

BOARDROOM = "http://127.0.0.1:8852"

def utc():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def fetch(path, timeout=2.5):
    try:
        with urllib.request.urlopen(BOARDROOM + path, timeout=timeout) as r:
            raw = r.read()
            text = raw.decode("utf-8", "replace")
            try:
                return {"ok": True, "json": json.loads(text), "bytes": len(raw)}
            except Exception:
                return {"ok": True, "text": text[:1000], "bytes": len(raw)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HQ-Claude Dashboard · 8850</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#08080e;color:#e8ecf3;font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:20;background:#0b0d12;border-bottom:1px solid #334155;padding:12px}
h1{margin:0;color:#eab308;font-size:20px}
.sub{color:#94a3b8;font-size:12px;margin:4px 0 10px}
.btn{display:inline-block;background:#1e293b;color:#eab308;border:1px solid #334155;border-radius:8px;padding:8px 10px;margin:3px;text-decoration:none;font-weight:800}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:12px;padding:12px}
.card{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:12px;min-height:130px}
.card h2{margin:0 0 8px;color:#eab308;font-size:15px}
pre{white-space:pre-wrap;word-break:break-word;background:#05070a;border:1px solid #1f2937;border-radius:8px;padding:8px;max-height:250px;overflow:auto;font-size:11px}
.good{color:#22c55e}.bad{color:#ef4444}.warn{color:#f59e0b}
.chat{display:flex;gap:8px;padding:0 12px 12px}
input{flex:1;background:#0b1220;color:#e8ecf3;border:1px solid #334155;border-radius:8px;padding:12px}
button{background:#eab308;color:#000;border:none;border-radius:8px;padding:12px 18px;font-weight:900;cursor:pointer}
.pill{display:inline-block;border-radius:999px;padding:2px 8px;background:#1e293b;color:#94a3b8;font-size:11px}
</style>
</head>
<body>
<header>
<h1>🟨 HQ-Claude Dashboard · 8850 <span id="state" class="pill">starting</span></h1>
<div class="sub">Visible HQ control dashboard. Reads Boardroom 8852. Posts chat to Town Square. This is the missing Claude HQ dashboard link for the iPad.</div>
<a class="btn" href="http://127.0.0.1:8852/ipad">📱 iPad</a>
<a class="btn" href="http://127.0.0.1:8852/">🏛 Boardroom</a>
<a class="btn" href="http://127.0.0.1:8852/tasks">📋 Task Council</a>
<a class="btn" href="http://127.0.0.1:8852/team_live">🟨 Team Live</a>
<a class="btn" href="http://127.0.0.1:8852/town_square">🗣 Town</a>
<a class="btn" href="http://127.0.0.1:8852/brain/usage">🧠 Brain Usage</a>
<a class="btn" href="http://127.0.0.1:8851/">🟪 Wren</a>
</header>

<div class="grid">
  <div class="card"><h2>HQ Stats</h2><pre id="hq">loading</pre></div>
  <div class="card"><h2>Task Council</h2><pre id="tasks">loading</pre></div>
  <div class="card"><h2>Team Live</h2><pre id="team">loading</pre></div>
  <div class="card"><h2>Brain Usage</h2><pre id="brain">loading</pre></div>
  <div class="card"><h2>Link Health</h2><pre id="links">loading</pre></div>
  <div class="card"><h2>Town Square</h2><pre id="town">loading</pre></div>
</div>

<div class="chat">
<input id="msg" placeholder="message to Town Square as Ross from HQ dashboard">
<button onclick="send()">SEND</button>
</div>

<script>
function small(x){ return JSON.stringify(x,null,2).slice(0,2200); }
async function j(path){ const r=await fetch(path,{cache:'no-store'}); return await r.json(); }
async function tick(){
  try{
    const d=await j('/state.json');
    document.getElementById('state').textContent=d.ok?'LIVE':'DEGRADED';
    document.getElementById('state').className=d.ok?'good':'bad';
    document.getElementById('hq').textContent=small(d.hq);
    document.getElementById('tasks').textContent=small(d.tasks);
    document.getElementById('team').textContent=small(d.team);
    document.getElementById('brain').textContent=small(d.brain);
    document.getElementById('links').textContent=small(d.links);
    document.getElementById('town').textContent=small(d.town);
  }catch(e){
    document.getElementById('state').textContent='ERR';
    document.getElementById('state').className='bad';
  }
}
async function send(){
  const el=document.getElementById('msg');
  const text=el.value.trim();
  if(!text) return;
  el.value='';
  await fetch('/api/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',to:'council',text,src:'hq_dash_8850'})});
  setTimeout(tick,250);
}
tick();
setInterval(tick,1000);
</script>
</body>
</html>
"""

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self.send(200, HTML, "text/html; charset=utf-8")
        if path in ("/health.json", "/state.json"):
            hq = fetch("/hq/stats", 2.5)
            tasks = fetch("/tasks/data", 2.5)
            team = fetch("/team_live/data", 4.5)
            brain = fetch("/brain/usage", 2.5)
            links = fetch("/link_health", 4)
            town = fetch("/town_square_feed", 3)
            out = {
                "ok": hq.get("ok") and tasks.get("ok"),
                "ts": utc(),
                "hq": hq,
                "tasks": tasks,
                "team": team,
                "brain": brain,
                "links": links,
                "town": town,
            }
            return self.send(200, json.dumps(out), "application/json")
        return self.send(404, "not found", "text/plain")

    def do_POST(self):
        path = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(n)
        if path == "/api/post":
            try:
                data = json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                data = {}
            payload = {
                "from": data.get("from", "ross"),
                "to": data.get("to", "council"),
                "text": data.get("text", ""),
                "src": data.get("src", "hq_dash_8850"),
            }
            req = urllib.request.Request(
                BOARDROOM + "/town/post",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=4) as r:
                    body = r.read()
                return self.send(200, body, "application/json")
            except Exception as e:
                return self.send(502, json.dumps({"ok": False, "error": str(e)}), "application/json")
        return self.send(404, "not found", "text/plain")

if __name__ == "__main__":
    print("HQ-Claude dashboard on http://0.0.0.0:8850/")
    ThreadingHTTPServer(("0.0.0.0", 8850), H).serve_forever()
