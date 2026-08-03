#!/usr/bin/env python3
"""Live Dashboard of Dashboards (:8895).

Read-only aggregator: systemd state and TCP reachability are measured on every
request; it never invents service health and never exposes retired identities.
"""
from __future__ import annotations
import json, socket, subprocess, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT = "0.0.0.0", 8895
DASHBOARDS = [
    ("Task Council", "qsb-council-live-dash.service", "http://127.0.0.1:8864/", 8864, "governance"),
    ("Wren", "qsb-wren-dash.service", "http://127.0.0.1:8851/", 8851, "people"),
    ("Talk to Wren", "qsb-wren-chat-dash.service", "http://127.0.0.1:8865/", 8865, "people"),
    ("Boardroom", "qsb-boardroom.service", "http://127.0.0.1:8852/", 8852, "leadership"),
    ("Leadership", "qsb-leadership-live-dash.service", "http://127.0.0.1:8855/", 8855, "leadership"),
    ("Transit Map", "qsb-transit-map.service", "http://127.0.0.1:8875/", 8875, "tower"),
    ("Codex Floor", "qsb-codex-floor-dash.service", "http://10.55.0.1:8870/", 8870, "engineering"),
    ("Evolution", "qsb-evolution-dash.service", "http://127.0.0.1:8869/", 8869, "learning"),
    ("Gene Pool", "qsb-gene-pool-dash.service", "http://127.0.0.1:8873/", 8873, "learning"),
    ("Knowledge Base", "qsb-knowledge-dash.service", "http://127.0.0.1:8866/", 8866, "learning"),
    ("Floor Planner", "qsb-floor-planner-dash.service", "http://127.0.0.1:8871/", 8871, "tower"),
    ("Tower Command", "qsb-floor53-command-dash.service", "http://127.0.0.1:8874/", 8874, "tower"),
    ("Receptionist", "qsb-receptionist-dash.service", "http://127.0.0.1:8856/", 8856, "operations"),
    ("Work Mode", "qsb-work-mode-dash.service", "http://127.0.0.1:8882/", 8882, "operations"),
    ("Wren Concierge", "qsb-wren-concierge-dash.service", "http://127.0.0.1:8857/", 8857, "people"),
    ("Living Skyscraper", "qsb-living-skyscraper.service", "http://127.0.0.1:8878/", 8878, "tower"),
    ("Agentic Traders", "qsb-agentic-traders-dash.service", "http://127.0.0.1:8863/", 8863, "operations"),
    ("Tour Guide", "qsb-tour-guide.service", "http://127.0.0.1:8854/", 8854, "operations"),
]

def active(unit: str) -> bool:
    try:
        return subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=2).stdout.strip() == "active"
    except Exception:
        return False

def reachable(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.2): return True
    except Exception: return False

def state():
    rows=[]
    for name, unit, url, port, group in DASHBOARDS:
        host = "127.0.0.1" if "127.0.0.1" in url else "10.55.0.1"
        svc, net = active(unit), reachable(port, host)
        rows.append({"name":name,"unit":unit,"url":url,"port":port,"group":group,"service":svc,"reachable":net,"ok":svc and net})
    ok=sum(x["ok"] for x in rows)
    return {"ts":time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),"total":len(rows),"ok":ok,"degraded":len(rows)-ok,"rows":rows,"source":"systemd is-active + TCP connect; read-only"}

HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SkyscraperHQ · Dashboard of Dashboards</title><style>
:root{--bg:#070b12;--card:#111a28;--line:#24344c;--text:#e7eefb;--dim:#8da2bd;--ok:#36e39b;--bad:#ff6b78;--accent:#74a7ff}*{box-sizing:border-box}body{margin:0;background:radial-gradient(1000px 500px at 50% -10%,#172946,var(--bg));color:var(--text);font:14px system-ui, sans-serif}main{max-width:1500px;margin:auto;padding:24px}.sub,.dim{color:var(--dim)}h1{margin:0 0 6px;font-size:27px}h2{font-size:13px;text-transform:uppercase;letter-spacing:.09em;color:#a9c1df;margin:0 0 13px}.hero,.card{background:rgba(17,26,40,.93);border:1px solid var(--line);border-radius:13px;padding:16px;box-shadow:0 12px 35px #0003}.hero{margin:20px 0}.kpis{display:flex;gap:10px;flex-wrap:wrap;margin-top:17px}.kpi{min-width:130px;background:#0d1522;border:1px solid var(--line);border-radius:10px;padding:12px}.num{font-size:27px;font-weight:800}.ok{color:var(--ok)}.bad{color:var(--bad)}.bar{height:10px;background:#0a111c;border-radius:9px;overflow:hidden;margin-top:12px}.fill{height:100%;background:linear-gradient(90deg,#5f88ff,#39e59d);transition:width .7s ease}.groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px}.cards{display:grid;gap:8px}.dash{display:grid;grid-template-columns:12px 1fr auto;gap:10px;align-items:center;border:1px solid #22314a;border-radius:9px;padding:10px;background:#0d1522}.dot{width:10px;height:10px;border-radius:50%;background:var(--bad);box-shadow:0 0 0 3px #ff6b7822}.dot.on{background:var(--ok);box-shadow:0 0 0 3px #36e39b22;animation:pulse 1.7s infinite}.name{font-weight:750}.meta{font-size:11px;color:var(--dim);margin-top:3px}a{color:#9bc1ff;text-decoration:none;border:1px solid #355787;border-radius:7px;padding:6px 9px}a:hover{background:#183254}.ticker{overflow:hidden;white-space:nowrap;border:1px solid var(--line);border-radius:8px;padding:9px;color:var(--dim);margin-top:16px}.track{display:inline-flex;gap:35px;animation:scroll 24s linear infinite}.track span{color:var(--text)}@keyframes scroll{from{transform:translateX(0)}to{transform:translateX(-45%)}}@keyframes pulse{50%{opacity:.45}}footer{margin-top:16px;font-size:11px;color:var(--dim)}button{background:#183254;color:#dbe9ff;border:1px solid #355787;border-radius:7px;padding:7px 10px;cursor:pointer}@media(max-width:650px){main{padding:13px}.groups{grid-template-columns:1fr}}
</style></head><body><main><h1>SkyscraperHQ · Dashboard of Dashboards</h1><div class=sub>One live control surface for the active tower dashboards. Retired HQ identities are excluded.</div><section class=hero><h2>Live fleet health</h2><div><span id=ok class="num ok">—</span> / <span id=total class=num>—</span> dashboards reachable <span id=stamp class=dim></span></div><div class=bar><div id=fill class=fill style="width:0"></div></div><div class=kpis><div class=kpi><div id=up class="num ok">—</div><div class=dim>healthy service + port</div></div><div class=kpi><div id=down class="num bad">—</div><div class=dim>needs attention</div></div><div class=kpi><div id=refresh class=num>3s</div><div class=dim>live refresh</div></div></div></section><div class=ticker><div id=ticker class=track>Waiting for live dashboard measurements…</div></div><section id=groups class=groups></section><footer id=source>Source: systemd is-active + local TCP reachability. Read-only aggregator.</footer></main><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function tick(){try{const d=await (await fetch('/api/data',{cache:'no-store'})).json();ok.textContent=d.ok;total.textContent=d.total;up.textContent=d.ok;down.textContent=d.degraded;fill.style.width=(d.total?100*d.ok/d.total:0)+'%';stamp.textContent='· measured '+d.ts;const gs={};d.rows.forEach(x=>(gs[x.group]??=[]).push(x));groups.innerHTML=Object.entries(gs).map(([g,rs])=>`<section class=card><h2>${esc(g)}</h2><div class=cards>${rs.map(x=>`<div class=dash><i class="dot ${x.ok?'on':''}"></i><div><div class=name>${esc(x.name)}</div><div class=meta>${esc(x.unit)} · :${x.port} · service ${x.service?'active':'inactive'} · port ${x.reachable?'reachable':'unreachable'}</div></div><a href="${esc(x.url)}" target="_blank" rel="noreferrer">Open</a></div>`).join('')}</div></section>`).join('');const lines=d.rows.map(x=>`<span>${x.ok?'●':'○'} ${esc(x.name)} :${x.port} ${x.ok?'LIVE':'ATTENTION'}</span>`);ticker.innerHTML=(lines.concat(lines)).join(' · ')}catch(e){stamp.textContent='· source unavailable'}}tick();setInterval(tick,3000);
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        if self.path.startswith('/api/data'):
            raw=json.dumps(state()).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
        raw=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

if __name__=='__main__':
    print(f'Dashboard hub listening on :{PORT}',flush=True)
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
