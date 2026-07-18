#!/usr/bin/env python3
"""
QSB Receptionist — the front desk (runs on the Raspberry Pi 4, hostname qsb-reception).

Role (per Ross/ChatGPT 2026-07-09): the Pi is NOT Claude HQ, Wren, TP, Acer or a
Brain Router. It is the front desk. It boots, checks who is online, posts to Town
Square, creates Task Council jobs, listens for Ross commands, and routes all
THINKING work back to the tower. No model runs here. No API keys live here.

Talks to the tower over LAN only:
  TOWER_HUB   = http://192.168.1.72:8852   (Boardroom hub: town square, ceo_mind, tasks)
  BRAIN       = http://192.168.1.72:8860   (Brain Router / gene pool — status only)

Endpoints (local, on the Pi):
  GET  /              front-desk status page
  GET  /health        {ok, host, uptime_s, tower_reachable}
  GET  /status        tower vitals (proxied from hub /quad_monitor/health)
  POST /ask     {text}    -> routes to tower /ceo_mind/hq_claude, returns reply (thinking stays in tower)
  POST /announce {text}   -> posts to Town Square as 'qsb_reception'
  POST /task    {title}   -> creates a Task Council job via the hub

Stdlib only — no pip installs needed on Raspberry Pi OS Lite first boot.
"""
import json, os, socket, time, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

TOWER_HUB = os.environ.get("QSB_TOWER_HUB", "http://192.168.1.72:8852")
BRAIN     = os.environ.get("QSB_BRAIN",     "http://192.168.1.72:8860")
PORT      = int(os.environ.get("QSB_RECEPTION_PORT", "8080"))
HOST      = socket.gethostname()
BOOT_TS   = time.time()


def _post(url, obj, timeout=45):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get(url, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def announce(text):
    """Post to Town Square as the front desk (never as a CEO)."""
    try:
        return _post(f"{TOWER_HUB}/api/compose",
                     {"from": "qsb_reception", "to": "council", "text": text,
                      "src": "reception"}, timeout=10)
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def tower_reachable():
    try:
        _get(f"{TOWER_HUB}/quad_monitor/health", timeout=6)
        return True
    except Exception:
        return False


_RECEPTION_TOUCH = r"""<!doctype html><html lang=en><head>
<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>SkyscraperHQ · Reception</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;height:100%;background:radial-gradient(ellipse at top,#141b2b,#0a0e14 55%,#000);color:#e8edf2;font-family:-apple-system,Segoe UI,Roboto,system-ui,sans-serif;overflow:hidden;user-select:none}
#wrap{display:flex;flex-direction:column;height:100vh;padding:14px;gap:12px}
.top{display:flex;align-items:center;gap:12px;flex:0 0 auto}
.crest{font-size:30px}
.title{font-weight:900;font-size:22px;color:#eab308;letter-spacing:.3px;line-height:1}
.sub{font-size:12px;color:#7d8ba0;margin-top:2px}
.clock{margin-left:auto;text-align:right;font-family:ui-monospace,monospace}
.clock .t{font-size:22px;font-weight:800}
.clock .d{font-size:11px;color:#7d8ba0}
.greet{flex:0 0 auto;background:linear-gradient(90deg,rgba(234,179,8,.14),transparent);border:1px solid #2a3446;border-left:4px solid #eab308;border-radius:12px;padding:12px 16px}
.greet b{color:#eab308;font-size:16px}
.greet span{color:#b9c4d4;font-size:13px}
#health{flex:0 0 auto;display:flex;gap:8px;overflow-x:auto;padding-bottom:2px}
.chip{display:flex;align-items:center;gap:7px;padding:7px 12px;background:#0f1620;border:1px solid #1e2a38;border-radius:22px;white-space:nowrap;font-size:13px}
.dot{width:11px;height:11px;border-radius:50%;background:#556;box-shadow:0 0 0 0}
.dot.up{background:#22c55e;box-shadow:0 0 9px #22c55e}
.dot.down{background:#ef4444;box-shadow:0 0 9px #ef4444}
.grid{flex:1 1 auto;display:grid;grid-template-columns:repeat(4,1fr);grid-auto-rows:1fr;gap:12px;min-height:0}
@media (max-width:820px){.grid{grid-template-columns:repeat(2,1fr)}}
.btn{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;background:linear-gradient(180deg,#141d2b,#0b1017);border:1px solid #26344a;border-radius:18px;color:#e8edf2;font-weight:800;font-size:16px;cursor:pointer;text-decoration:none;padding:10px;transition:transform .1s,border-color .2s;text-align:center}
.btn:active{transform:scale(.96);border-color:#eab308}
.btn .ic{font-size:38px;line-height:1}
.btn .sm{font-size:11px;color:#8ba0b8;font-weight:600}
.btn.hero{grid-column:span 2;background:linear-gradient(135deg,#eab308,#f59e0b);color:#000;border:none}
.btn.hero .sm{color:#4a2f00}
.btn.tour{background:linear-gradient(135deg,#a855f7,#7c3aed);color:#fff;border:none}
.btn.tour .sm{color:#e9d5ff}
.foot{flex:0 0 auto;display:flex;align-items:center;gap:10px;font-size:11px;color:#5b6b82}
.foot .fdot{width:8px;height:8px;border-radius:50%;background:#556}
.btn.wide{grid-column:span 2}
</style></head><body>
<div id=wrap>
  <div class=top>
    <div class=crest>🏛</div>
    <div><div class=title>SkyscraperHQ · Reception</div><div class=sub id=hostsub>front desk</div></div>
    <div class=clock><div class=t id=clk>--:--</div><div class=d id=clkd></div></div>
  </div>
  <div class=greet><b>Welcome to SkyscraperHQ.</b> <span>I'm the front desk. Tap a floor to travel the tower, or start the guided tour.</span></div>
  <div id=health></div>
  <div class=grid id=grid></div>
  <div class=foot><span class=fdot id=fdot></span><span id=footmsg>connecting to tower…</span></div>
</div>
<script>
const CFG = __CFG__;
document.getElementById('hostsub').textContent = 'front desk · '+CFG.host+' · tower '+CFG.hub.split('//')[1];
const BTNS = [
  {k:'wall', ic:'🖥️', t:'4× Dashboard Wall', sm:'all CEO screens', cls:'hero', url:CFG.wall},
  {k:'tour', ic:'🎫', t:'Start Guided Tour', sm:'travel the tower', cls:'tour', url:CFG.tour},
  {k:'boardroom', ic:'🏛', t:'Boardroom', sm:'the hub', url:CFG.boardroom},
  {k:'tasks', ic:'📋', t:'Task Council', sm:'the work', url:CFG.tasks},
  {k:'town', ic:'📢', t:'Town Square', sm:'live feed', url:CFG.town},
  {k:'gene', ic:'🧠', t:'Brain Router', sm:'gene pool', url:CFG.gene},
  {k:'hqdash', ic:'🟡', t:'Claude HQ', sm:'orchestrator', url:CFG.hqdash},
  {k:'wren', ic:'🟣', t:'Wren', sm:'designer', url:CFG.wren},
  {k:'tp', ic:'🔬', t:'TP-Pip', sm:'research', url:CFG.tp},
  {k:'acer', ic:'⚡', t:'Acer-Cass', sm:'data foundry', url:CFG.acer},
];
const grid=document.getElementById('grid');
BTNS.forEach(b=>{const a=document.createElement('a');a.className='btn '+(b.cls||'');a.href=b.url;a.target='_blank';
  a.innerHTML='<span class=ic>'+b.ic+'</span><span>'+b.t+'</span><span class=sm>'+b.sm+'</span>';grid.appendChild(a);});
function tick(){const d=new Date();document.getElementById('clk').textContent=d.toTimeString().slice(0,5);
  document.getElementById('clkd').textContent=d.toDateString();}
tick();setInterval(tick,1000);
const HKEYS=[['hq','Claude HQ'],['wren','Wren'],['tp','TP-Pip'],['acer','Acer']];
async function health(){
  try{
    const r=await fetch('/status',{cache:'no-store'});const j=await r.json();
    const p=(j.tower&&j.tower.panels)||{};const hd=document.getElementById('health');hd.innerHTML='';
    let up=0,tot=0;
    HKEYS.forEach(([k,name])=>{const v=p[k]||{};const ok=!!v.up;tot++;if(ok)up++;
      const c=document.createElement('div');c.className='chip';
      c.innerHTML='<span class="dot '+(ok?'up':'down')+'"></span>'+name;hd.appendChild(c);});
    document.getElementById('fdot').className='fdot';document.getElementById('fdot').style.background=up?'#22c55e':'#ef4444';
    document.getElementById('footmsg').textContent='tower '+up+'/'+tot+' CEO screens live · '+new Date().toLocaleTimeString();
  }catch(e){document.getElementById('footmsg').textContent='tower unreachable — front desk still open ('+e+')';
    document.getElementById('fdot').style.background='#ef4444';}
}
health();setInterval(health,5000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode())
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/health":
            self._json(200, {"ok": True, "host": HOST, "role": "front_desk",
                             "uptime_s": round(time.time() - BOOT_TS),
                             "tower_hub": TOWER_HUB, "tower_reachable": tower_reachable()})
            return
        if p == "/status":
            try:
                self._json(200, {"ok": True, "tower": _get(f"{TOWER_HUB}/quad_monitor/health")})
            except Exception as e:
                self._json(502, {"ok": False, "error": str(e)[:160]})
            return
        # front-desk TOUCH dashboard (Ross 2026-07-09 — production touch UI for the Pi screen)
        _host = TOWER_HUB.split("//")[-1].split(":")[0]  # tower host, e.g. 192.168.1.72
        cfg = {
            "hub": TOWER_HUB, "brain": BRAIN, "host": HOST,
            "wall": f"{TOWER_HUB}/quad_monitor", "tour": f"{TOWER_HUB}/tour",
            "boardroom": f"{TOWER_HUB}/", "tasks": f"{TOWER_HUB}/tasks",
            "town": f"{TOWER_HUB}/town_square",
            "hqdash": f"http://{_host}:8850/", "wren": f"http://{_host}:8851/",
            "gene": f"http://{_host}:8860/", "tp": "http://192.168.1.74:9110/",
            "acer": "http://192.168.1.41:9000/",
        }
        html = _RECEPTION_TOUCH.replace("__CFG__", json.dumps(cfg))
        b = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        p = self.path.split("?", 1)[0]
        d = self._body()
        if p == "/ask":
            # route THINKING to the tower — the Pi never thinks locally
            text = (d.get("text") or "").strip()
            if not text:
                self._json(400, {"error": "empty text"}); return
            try:
                out = _post(f"{TOWER_HUB}/ceo_mind/hq_claude", {"prompt": text, "mode": "gene"})
                self._json(200, {"ok": True, "routed_to": "tower/hq_claude", "reply": out.get("reply", ""),
                                 "mind": out.get("mind", "")})
            except Exception as e:
                self._json(502, {"ok": False, "error": str(e)[:160]})
            return
        if p == "/announce":
            self._json(200, announce((d.get("text") or "").strip()[:2000])); return
        if p == "/task":
            title = (d.get("title") or d.get("text") or "").strip()
            if not title:
                self._json(400, {"error": "empty title"}); return
            try:
                out = _post(f"{TOWER_HUB}/tasks/create",
                            {"title": title, "from": "qsb_reception", "src": "reception"})
                self._json(200, {"ok": True, "task": out})
            except Exception as e:
                # hub may expose a different task route; surface honestly rather than fake success
                self._json(502, {"ok": False, "error": str(e)[:160],
                                 "note": "confirm hub task-create route on first boot"})
            return
        self._json(404, {"error": "no such route"})


def main():
    # announce arrival to the tower (best-effort; front desk still boots if tower is down)
    res = announce(f"Front desk {HOST} is online and open. Tower reachable: {tower_reachable()}.")
    print(f"[boot] announce -> {res}", flush=True)
    print(f"[boot] QSB Receptionist on 0.0.0.0:{PORT} (front desk, no local model, no keys)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
