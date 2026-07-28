#!/usr/bin/env python3
"""
qsb_control_hub.py — SkyscraperHQ CONTROL landing page (:8888).

2026-07-28, Ross: "a single front door — one URL that links every dash, Underground
front-and-centre." Shows the live Underground embedded, plus a card per dashboard with
its live up/down status. Read-only. systemd qsb-control-hub.service (boot-persistent).
"""
import json, argparse, urllib.request, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VER = str(int(time.time()))
# section, name, port, path, emoji, blurb
DASHES = [
    # Maps & pipelines
    ("Maps & Ops", "Underground", 8875, "/", "🚆", "Live tower-wide tube map — every train, every line"),
    ("Maps & Ops", "Task Council", 8864, "/", "🏛️", "Train-track pipeline + Accept/Reject + Wren decisions"),
    ("Maps & Ops", "Agentic Traders", 8863, "/", "📈", "Live trading fleet (real broker truth)"),
    # Chat & people
    ("Chat & People", "Talk to Wren", 8865, "/", "💬", "Primary chat surface — Wren's mind"),
    ("Chat & People", "Wren · Concierge", 8857, "/", "🛎️", "Concierge desk"),
    ("Chat & People", "Wren · Bench", 8851, "/", "🛠️", "Wren's workbench"),
    ("Chat & People", "Tour Guide", 8854, "/", "🧭", "Guided tour of the tower"),
    ("Chat & People", "Receptionist", 8856, "/", "📇", "Front-desk receptionist"),
    ("Chat & People", "Codex Floor", 8870, "/", "🤖", "Codex full-circle + terminal"),
    # Routing & gene pool
    ("Routing & Gene Pool", "Gene Pool · Router (canonical)", 8860, "/", "🧬", "Brain Router V4 — the REAL live provider routing"),
    ("Routing & Gene Pool", "Gene Pool · Controls", 8873, "/", "🎛️", "Provider force/disable overrides"),
    ("Routing & Gene Pool", "Boardroom Hub", 8852, "/", "🗣️", "Task council + town square"),
    # Floors & structure
    ("Floors & Structure", "Floor Planner", 8871, "/", "📋", "Every floor · click to open"),
    ("Floors & Structure", "Floor 53 · Command", 8874, "/", "🗼", "Whole-tower structure + new floors"),
    ("Floors & Structure", "Tower Reorganizer", 8872, "/", "🔧", "Guided floor moves (live apply)"),
]


def _up(port, path="/"):
    """Real HTTP health check — a 2xx/3xx is 'live'. A bound-but-404 port (e.g. :8850) reads DOWN,
    unlike the old raw TCP connect which false-greened anything merely listening."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=0.8) as r:
            return 200 <= r.status < 400
    except urllib.error.HTTPError as e:
        return 200 <= e.code < 400
    except Exception:
        return False


def build():
    return {"ver": VER, "dashes": [{"section": s, "name": n, "port": p, "path": pa, "emoji": e,
                                     "blurb": b, "up": _up(p, pa)}
                                    for s, n, p, pa, e, b in DASHES]}


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>SkyscraperHQ · Control</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0a0e16;--card:#131a26;--line:#233146;--txt:#e8f1ff;--dim:#8ba0ba;--ok:#39d98a;--bad:#ff6b6b;--acc:#40b4ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:18px}
h1{margin:0;font-size:24px}h1 span{color:var(--acc)}
.sub{color:var(--dim);margin:2px 0 14px}
.feature{border:1px solid var(--line);border-radius:16px;overflow:hidden;margin-bottom:16px;background:var(--card)}
.feature .bar{display:flex;justify-content:space-between;align-items:center;padding:10px 16px;border-bottom:1px solid var(--line)}
.feature .bar b{font-size:16px}.feature iframe{width:100%;height:560px;border:0;background:#080c14}
.sec{margin-bottom:18px}
.sec h2{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin:0 0 8px;border-bottom:1px solid var(--line);padding-bottom:5px}
.secgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.dash{display:block;text-decoration:none;color:var(--txt);background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;transition:border-color .2s,transform .1s}
.dash:hover{border-color:var(--acc);transform:translateY(-2px)}
.dash .top{display:flex;align-items:center;gap:10px}
.dash .em{font-size:26px}.dash .nm{font-weight:700;font-size:15px}
.dash .bl{color:var(--dim);font-size:12px;margin-top:6px}
.dash .st{margin-top:8px;font-size:11px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}
.up{background:var(--ok)}.down{background:var(--bad)}
.open{color:var(--acc);font-weight:700}
footer{color:var(--dim);margin-top:16px;font-size:12px}
</style></head><body><div class=wrap>
<h1>SkyscraperHQ <span>· Control</span></h1>
<div class=sub>Single front door. The Underground is live below; every dashboard is one click away.</div>
<div class=feature>
  <div class=bar><b>🚆 Underground — live tower map</b><a id=ugopen class=open target=_blank href="#">open full ↗</a></div>
  <iframe id=ugframe src="about:blank"></iframe>
</div>
<div class=grid id=grid></div>
<footer>auto-refresh · <span id=ts></span> · :8888</footer>
</div><script>
const HOST=location.hostname;
document.getElementById("ugframe").src="http://"+HOST+":8875/";
document.getElementById("ugopen").href="http://"+HOST+":8875/";
async function tick(){
  let d;try{d=await(await fetch("/api/data")).json()}catch(e){return}
  if(window.__v&&window.__v!==d.ver){location.reload();return}window.__v=d.ver;
  const secs=[];const bySec={};
  (d.dashes||[]).forEach(x=>{if(!bySec[x.section]){bySec[x.section]=[];secs.push(x.section)}bySec[x.section].push(x)});
  document.getElementById("grid").innerHTML=secs.map(sec=>
    `<div class=sec><h2>${sec}</h2><div class=secgrid>`+bySec[sec].map(x=>
      `<a class=dash href="http://${HOST}:${x.port}${x.path}" target=_blank>
         <div class=top><span class=em>${x.emoji}</span><span class=nm>${x.name}</span></div>
         <div class=bl>${x.blurb}</div>
         <div class=st><span class="dot ${x.up?'up':'down'}"></span>${x.up?'live':'down'} · :${x.port} · <span class=open>open ↗</span></div>
       </a>`).join("")+`</div></div>`).join("");
  document.getElementById("ts").textContent=new Date().toLocaleTimeString();
}
tick();setInterval(tick,5000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

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
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8888)
    a = ap.parse_args()
    print(f"control hub on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
