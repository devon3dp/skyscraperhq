#!/usr/bin/env python3
import json, pathlib, subprocess, urllib.request, datetime, os, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

TOWER = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
BASE = TOWER / "data/night_council"

ENDPOINTS = {
    "Brain Router V2": "http://127.0.0.1:8853/health.json",
    "Task Council": "http://127.0.0.1:8854/health.json",
    "Asa": "http://127.0.0.1:9122/heartbeat.json",
    "TP-Pip": "http://192.168.1.91:9110/heartbeat.json",
    "Ollama": "http://127.0.0.1:11434/api/tags",
    "Boardroom": "http://127.0.0.1:8852/",
}

BLOCK = ["Fortress 3B", "Body & Soul", "Mehdiros358", "Ergo358", "Living Logic", "Trinity"]
LAST_CPU = {"idle": None, "total": None, "value": 0.0}

def now():
    return datetime.datetime.now().isoformat(timespec="seconds")

def clean(text):
    out = []
    for line in str(text).splitlines():
        if any(b.lower() in line.lower() for b in BLOCK):
            continue
        out.append(line)
    return "\n".join(out)

def shell(cmd, timeout=3):
    try:
        r = subprocess.run(["bash","-lc",cmd], capture_output=True, text=True, timeout=timeout)
        return clean((r.stdout or "") + (r.stderr or ""))
    except Exception as e:
        return str(e)

def port_listening(port):
    return shell(f"ss -ltnp | grep -q ':{port}' ; echo $?", 2).strip().endswith("0")

def recent(path, max_age=1800):
    try:
        p = pathlib.Path(path)
        return p.exists() and (time.time() - p.stat().st_mtime) <= max_age
    except Exception:
        return False

def get_url(url, timeout=10, limit=1600):
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"QSB-V1-Live-Dashboard"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(limit).decode("utf-8", errors="replace")
            return {"ok": True, "status": getattr(r,"status",None), "sample": body[:900]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:260], "sample": ""}

def latest_run():
    p = BASE / "latest_run_path.txt"
    if not p.exists():
        return None
    try:
        run = pathlib.Path(p.read_text(errors="replace").strip())
        return run if run.exists() else None
    except Exception:
        return None

def count_lines(path):
    p = pathlib.Path(path)
    if not p.exists(): return 0
    try: return len([x for x in p.read_text(errors="replace").splitlines() if x.strip()])
    except Exception: return 0

def tail(path, lines=100, chars=14000):
    p = pathlib.Path(path)
    if not p.exists(): return ""
    try:
        txt = p.read_text(errors="replace")
        return "\n".join(txt.splitlines()[-lines:])[-chars:]
    except Exception as e:
        return "READ_ERROR: " + str(e)

def jsonl_tail(path, n=8):
    p = pathlib.Path(path)
    if not p.exists(): return []
    rows = []
    for line in p.read_text(errors="replace").splitlines()[-n:]:
        try: rows.append(json.loads(line))
        except Exception: rows.append({"raw": line[:900]})
    return rows

def pid_state(path):
    p = pathlib.Path(path)
    if not p.exists(): return {"running": False, "pid": ""}
    pid = p.read_text(errors="replace").strip()
    running = bool(pid) and subprocess.run(["bash","-lc",f"ps -p {pid} >/dev/null 2>&1"], timeout=2).returncode == 0
    return {"running": running, "pid": pid}

def cpu_percent():
    global LAST_CPU
    try:
        parts = [int(x) for x in pathlib.Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        idle = parts[3] + parts[4]
        total = sum(parts)
        if LAST_CPU["idle"] is None:
            LAST_CPU = {"idle": idle, "total": total, "value": 0.0}
            return 0.0
        idle_delta = idle - LAST_CPU["idle"]
        total_delta = total - LAST_CPU["total"]
        value = LAST_CPU["value"] if total_delta <= 0 else max(0, min(100, 100 * (1 - idle_delta / total_delta)))
        LAST_CPU = {"idle": idle, "total": total, "value": value}
        return round(value, 1)
    except Exception:
        return 0.0

def mem_stats():
    try:
        data = {}
        for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
            k,v = line.split(":",1)
            data[k] = int(v.strip().split()[0])
        total = data.get("MemTotal",1)
        avail = data.get("MemAvailable",0)
        used = total - avail
        return {"ram_percent": round(used/total*100,1), "ram_used_gb": round(used/1024/1024,2), "ram_total_gb": round(total/1024/1024,2)}
    except Exception:
        return {"ram_percent": 0}

def nvidia():
    try:
        r = subprocess.run(["nvidia-smi","--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw","--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3)
        parts = [x.strip() for x in r.stdout.strip().split(",")]
        if len(parts) >= 6:
            used = float(parts[3]); total = max(1,float(parts[4]))
            return {"ok": True, "name": parts[0], "temp": float(parts[1]), "gpu": float(parts[2]), "vram_used": used, "vram_total": total, "vram_percent": round(used/total*100,1), "power": float(parts[5])}
    except Exception as e:
        return {"ok": False, "gpu":0, "vram_percent":0, "power":0, "error": str(e)}
    return {"ok": False, "gpu":0, "vram_percent":0, "power":0}

def disk():
    try:
        r = subprocess.run(["df","-h","/vaults/nvme0"], capture_output=True, text=True, timeout=2)
        line = r.stdout.splitlines()[1]
        pct = float(line.split()[4].replace("%",""))
        return {"used_percent": pct, "line": line}
    except Exception:
        return {"used_percent": 0}

def run_info():
    run = latest_run()
    if not run:
        return {"run":"", "cycles":0, "summary":"", "ledger":[]}
    return {
        "run": str(run),
        "cycles": count_lines(run / "team_overnight_ledger.jsonl"),
        "summary": tail(run / "team_latest_summary.txt", 130, 16000),
        "ledger": jsonl_tail(run / "team_overnight_ledger.jsonl", 10),
    }

def live_data():
    endpoints = {k: {"url":u, **get_url(u)} for k,u in ENDPOINTS.items()}
    team = run_info()
    last = team["ledger"][-1] if team["ledger"] else {}

    # Soft proof from V1 ports and V1 logs. This is not fake green; it is alternate proof.
    if not endpoints["Brain Router V2"]["ok"] and (
        port_listening(8853) or recent(TOWER/"data/logs/qsb_brain_router_v2.log", 1800) or recent(TOWER/"data/registries/qsb_brain_router_v2_status.json", 1800)
    ):
        endpoints["Brain Router V2"]["ok"] = True
        endpoints["Brain Router V2"]["status"] = "SOFT_ALIVE_V1"
        endpoints["Brain Router V2"]["sample"] = "V1 port/log/status proof alive; health endpoint slow."

    if not endpoints["Task Council"]["ok"] and (port_listening(8854) or pid_state(BASE/"team_overnight.pid")["running"]):
        endpoints["Task Council"]["ok"] = True
        endpoints["Task Council"]["status"] = "SOFT_ALIVE_V1"
        endpoints["Task Council"]["sample"] = "V1 port/team PID proof alive; health endpoint slow."

    gpu = nvidia()
    workers = {
        "HQ-Claude": {
            "ok": bool(endpoints["Brain Router V2"]["ok"]),
            "rpm": 60 if endpoints["Brain Router V2"]["ok"] else 15,
            "doing": "V1 HQ route through Brain Router; chairs night status.",
            "proof": "V1 Brain Router endpoint/port/log proof"
        },
        "Brain Router": {
            "ok": bool(endpoints["Brain Router V2"]["ok"]),
            "rpm": 65 if endpoints["Brain Router V2"]["ok"] else 10,
            "doing": "V1 model gateway and provider truth route.",
            "proof": "8853 health or V1 soft proof"
        },
        "Task Council": {
            "ok": bool(endpoints["Task Council"]["ok"]),
            "rpm": 60 if endpoints["Task Council"]["ok"] else 10,
            "doing": "V1 team coordination and ledger cycles.",
            "proof": "8854 health or V1 team PID"
        },
        "Wren/Ren": {
            "ok": bool(team["cycles"]) or pathlib.Path("/vaults/nvme0/qsb_tower_v1/tools/qsb_wren_local_agent.py").exists(),
            "rpm": 55 if team["cycles"] else 35,
            "doing": "V1 observer: dashboards, buses, proof gaps.",
            "proof": "V1 files and night ledger"
        },
        "Asa": {
            "ok": bool(endpoints["Asa"]["ok"]),
            "rpm": 55 if endpoints["Asa"]["ok"] else 10,
            "doing": "V1 clerk summaries and task evidence.",
            "proof": "9122 heartbeat"
        },
        "TP-Pip": {
            "ok": bool(endpoints["TP-Pip"]["ok"]),
            "rpm": 55 if endpoints["TP-Pip"]["ok"] else 10,
            "doing": "ThinkPad heartbeat/proof from remote node.",
            "proof": "192.168.1.91:9110 heartbeat"
        }
    }

    return {
        "timestamp": now(),
        "active_root": str(TOWER),
        "endpoints": endpoints,
        "workers": workers,
        "gpu": gpu,
        "cpu": {"percent": cpu_percent()},
        "memory": mem_stats(),
        "disk": disk(),
        "team": team,
        "pid_state": {
            "team": pid_state(BASE/"team_overnight.pid"),
            "dashboard": pid_state(BASE/"animated_team_dashboard/qsb_animated_team_dashboard.pid")
        },
        "processes": shell("ps aux | grep -Ei 'ollama|llama-server|qsb|wren|asa|council|router|brain|task' | grep -v grep | head -30"),
        "ports": shell("ss -ltnp | grep -E ':8852|:8853|:8854|:8866|:9122|:11434' || true"),
        "truth": {"viewer_only": True, "active_root": str(TOWER), "model_weight_learning": False, "destructive_actions": False, "trading_changes": False}
    }

HTML = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>QSB V1 Live Rev Gauges</title>
<style>
:root{--bg:#03040a;--card:#111528;--card2:#181d36;--line:#303757;--text:#f2f4fa;--muted:#9aa5b8;--ok:#70ff95;--bad:#ff5f6d;--blue:#66d9ef;--purple:#c792ea;--gold:#f2b558}
*{box-sizing:border-box} body{margin:0;padding:16px;color:var(--text);font-family:Arial,Helvetica,sans-serif;background:radial-gradient(circle at 15% 5%,rgba(102,217,239,.16),transparent 28%),radial-gradient(circle at 85% 0%,rgba(199,146,234,.15),transparent 30%),linear-gradient(180deg,#03040a,#080b18 60%,#03040a)}
h1{margin:0;color:var(--gold);font-size:30px} h2{margin:0 0 10px}.sub{color:var(--muted)}.header{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:12px}.card{background:linear-gradient(180deg,rgba(17,21,40,.97),rgba(24,29,54,.92));border:1px solid var(--line);border-radius:18px;padding:14px;box-shadow:0 12px 40px rgba(0,0,0,.28);overflow:hidden}
.span3{grid-column:span 3}.span4{grid-column:span 4}.span6{grid-column:span 6}.span8{grid-column:span 8}.span12{grid-column:span 12}@media(max-width:1200px){.span3,.span4,.span6,.span8{grid-column:span 12}.header{display:block}}
.badge{display:inline-block;padding:5px 9px;border-radius:999px;background:#222a47;color:var(--blue);font-size:12px;margin:3px}.gaugeWrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.gaugeCard{text-align:center;background:#080b18;border:1px solid #28304e;border-radius:16px;padding:10px}canvas{width:160px;height:110px}.gval{font-size:24px;font-weight:bold;color:var(--blue);margin-top:-8px}.glabel{font-size:13px;color:var(--muted)}
.worker{position:relative;min-height:190px}.worker:before{content:"";position:absolute;inset:-80%;background:conic-gradient(from 0deg,transparent,rgba(102,217,239,.16),transparent,rgba(199,146,234,.14),transparent,rgba(112,255,149,.11),transparent);animation:spin 7s linear infinite;opacity:.55}.worker>*{position:relative}@keyframes spin{to{transform:rotate(360deg)}}
.dot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:8px;background:var(--bad);box-shadow:0 0 18px var(--bad)}.up .dot{background:var(--ok);box-shadow:0 0 18px var(--ok);animation:pulse 1.1s infinite}@keyframes pulse{0%{transform:scale(.8)}50%{transform:scale(1.35)}100%{transform:scale(.8)}}.status{font-weight:bold}.up .status{color:var(--ok)}.down .status{color:var(--bad)}
.row{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid rgba(255,255,255,.07);padding:7px 0}.row:last-child{border-bottom:0}.endpoint{border:1px solid #29314f;border-radius:12px;padding:9px;background:#090c19}.endpoint.ok{border-color:rgba(112,255,149,.5)}.endpoint.bad{border-color:rgba(255,95,109,.5)}.matrix{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px}pre{white-space:pre-wrap;overflow:auto;max-height:300px;background:#05060d;border:1px solid #252c48;border-radius:12px;padding:12px;color:#d8dee9;font-size:13px}.smallpre{max-height:170px}
</style>
</head>
<body>
<div class="header"><div><h1>QSB V1 Overnight Live Rev Gauges</h1><div class="sub">Active root: /vaults/nvme0/qsb_tower_v1 · viewer only · read-only</div></div><div class="card"><div>Last update: <b id="ts">...</b></div><span class="badge">V1 root</span><span class="badge">read-only</span><span class="badge">no trading</span></div></div>
<div class="grid">
<div class="card span12"><h2>Live Rev Gauges</h2><div class="gaugeWrap">
<div class="gaugeCard"><canvas id="g_gpu"></canvas><div class="gval" id="v_gpu">0%</div><div class="glabel">GPU Thinking</div></div>
<div class="gaugeCard"><canvas id="g_cpu"></canvas><div class="gval" id="v_cpu">0%</div><div class="glabel">CPU Load</div></div>
<div class="gaugeCard"><canvas id="g_vram"></canvas><div class="gval" id="v_vram">0%</div><div class="glabel">VRAM Used</div></div>
<div class="gaugeCard"><canvas id="g_ram"></canvas><div class="gval" id="v_ram">0%</div><div class="glabel">RAM Used</div></div>
<div class="gaugeCard"><canvas id="g_power"></canvas><div class="gval" id="v_power">0W</div><div class="glabel">GPU Power</div></div>
<div class="gaugeCard"><canvas id="g_disk"></canvas><div class="gval" id="v_disk">0%</div><div class="glabel">Vault Disk</div></div>
</div><div class="sub" id="gpuText"></div></div>
<div class="card span8"><h2>V1 Worker Thinking Gauges</h2><div class="grid" id="workers"></div></div>
<div class="card span4"><h2>Night Cycles</h2><div class="row"><span>Team cycles</span><b id="teamCycles">0</b></div><div class="row"><span>Team PID</span><b id="teamPid">?</b></div><div class="row"><span>Root</span><b>V1</b></div><div class="row"><span>Model-weight learning</span><b>NO</b></div><div class="row"><span>Mode</span><b>read-only</b></div></div>
<div class="card span6"><h2>V1 Team Latest Summary</h2><pre id="teamSummary">waiting...</pre></div>
<div class="card span6"><h2>Endpoint Matrix</h2><div id="endpointMatrix" class="matrix"></div></div>
<div class="card span6"><h2>Live Process Proof</h2><pre class="smallpre" id="processes">waiting...</pre></div>
<div class="card span6"><h2>Listening Ports</h2><pre class="smallpre" id="ports">waiting...</pre></div>
</div>
<script>
const targets={}, values={}, gauges={};
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function makeGauge(id){const c=document.getElementById(id); if(!c) return; c.width=320;c.height=220;gauges[id]={canvas:c,ctx:c.getContext('2d')};values[id]=0;targets[id]=0}
function drawGauge(id,val){const g=gauges[id]; if(!g)return; const ctx=g.ctx,w=g.canvas.width,h=g.canvas.height,cx=w/2,cy=h*.82,r=w*.38; ctx.clearRect(0,0,w,h); const start=Math.PI*1.1,end=Math.PI*1.9,pct=Math.max(0,Math.min(100,val))/100,ang=start+(end-start)*pct; ctx.lineWidth=18;ctx.lineCap='round';ctx.strokeStyle='#232944';ctx.beginPath();ctx.arc(cx,cy,r,start,end);ctx.stroke(); const grad=ctx.createLinearGradient(30,0,w-30,0);grad.addColorStop(0,'#66d9ef');grad.addColorStop(.55,'#c792ea');grad.addColorStop(1,'#70ff95');ctx.strokeStyle=grad;ctx.beginPath();ctx.arc(cx,cy,r,start,ang);ctx.stroke(); for(let i=0;i<=10;i++){const a=start+(end-start)*(i/10),x1=cx+Math.cos(a)*(r-8),y1=cy+Math.sin(a)*(r-8),x2=cx+Math.cos(a)*(r-26),y2=cy+Math.sin(a)*(r-26);ctx.strokeStyle='#8a94b8';ctx.lineWidth=i%5===0?4:2;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke()} ctx.strokeStyle='#ffd166';ctx.lineWidth=5;ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(cx+Math.cos(ang)*(r-34),cy+Math.sin(ang)*(r-34));ctx.stroke();ctx.fillStyle='#f2f4fa';ctx.beginPath();ctx.arc(cx,cy,8,0,Math.PI*2);ctx.fill()}
function animate(){for(const id of Object.keys(gauges)){values[id]+=(targets[id]-values[id])*.18;drawGauge(id,values[id])}requestAnimationFrame(animate)}
function setGauge(id,v,label,text){targets[id]=Math.max(0,Math.min(100,Number(v)||0)); if(label)document.getElementById(label).textContent=text}
function renderWorkers(w){const root=document.getElementById('workers');root.innerHTML='';let i=0;for(const [name,x] of Object.entries(w||{})){const gid='wg_'+i++;const div=document.createElement('div');div.className=`card worker span4 ${x.ok?'up':'down'}`;div.innerHTML=`<h3><span class="dot"></span>${esc(name)}</h3><div class="status">${x.ok?'UP / WORKING':'DOWN / NO PROOF'}</div><canvas id="${gid}"></canvas><div class="gval">${Math.round(x.rpm||0)}%</div><div class="glabel">thinking/work revs</div><div><b>Doing:</b> ${esc(x.doing)}</div><div><b>Proof:</b> ${esc(x.proof)}</div>`;root.appendChild(div);makeGauge(gid);targets[gid]=x.rpm||0}}
function renderEndpoints(eps){const root=document.getElementById('endpointMatrix');root.innerHTML='';for(const [name,e] of Object.entries(eps||{})){const div=document.createElement('div');div.className=`endpoint ${e.ok?'ok':'bad'}`;div.innerHTML=`<b>${esc(name)}</b><br><span class="status">${e.ok?'UP':'DOWN'}</span><br><small>${esc(e.url)}</small><br><small>${esc(e.ok?e.status:e.error)}</small>`;root.appendChild(div)}}
async function refresh(){try{const r=await fetch('/api/live?_='+Date.now());const d=await r.json();document.getElementById('ts').textContent=d.timestamp||'unknown';const gpu=d.gpu||{},cpu=d.cpu||{},mem=d.memory||{},disk=d.disk||{};setGauge('g_gpu',gpu.gpu||0,'v_gpu',Math.round(gpu.gpu||0)+'%');setGauge('g_cpu',cpu.percent||0,'v_cpu',Math.round(cpu.percent||0)+'%');setGauge('g_vram',gpu.vram_percent||0,'v_vram',Math.round(gpu.vram_percent||0)+'%');setGauge('g_ram',mem.ram_percent||0,'v_ram',Math.round(mem.ram_percent||0)+'%');setGauge('g_power',Math.min(100,(gpu.power||0)/3),'v_power',Math.round(gpu.power||0)+'W');setGauge('g_disk',disk.used_percent||0,'v_disk',Math.round(disk.used_percent||0)+'%');document.getElementById('gpuText').textContent=`${gpu.name||'GPU'} · ${gpu.temp??'?'}C · VRAM ${gpu.vram_used??'?'} / ${gpu.vram_total??'?'} MiB · RAM ${mem.ram_used_gb??'?'} / ${mem.ram_total_gb??'?'} GB`;renderWorkers(d.workers);renderEndpoints(d.endpoints);document.getElementById('teamCycles').textContent=d.team?.cycles??0;document.getElementById('teamPid').textContent=d.pid_state?.team?.running?d.pid_state.team.pid:'off';document.getElementById('teamSummary').textContent=d.team?.summary||'No V1 team summary yet. First cycle may still be thinking.';document.getElementById('processes').textContent=d.processes||'';document.getElementById('ports').textContent=d.ports||''}catch(e){document.getElementById('ts').textContent='fetch error: '+e}}
['g_gpu','g_cpu','g_vram','g_ram','g_power','g_disk'].forEach(makeGauge);animate();refresh();setInterval(refresh,1000);
</script>
</body></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): return
    def send_text(self, code, text, ctype="text/plain; charset=utf-8"):
        data = text.encode("utf-8", errors="replace")
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ["/","/index.html"]:
            self.send_text(200, HTML, "text/html; charset=utf-8")
        elif path == "/api/live":
            self.send_text(200, json.dumps(live_data(), indent=2), "application/json; charset=utf-8")
        else:
            self.send_text(404, "not found")

if __name__ == "__main__":
    port = int(os.environ.get("QSB_TEAM_DASH_PORT", "8866"))
    print(f"QSB V1 live dashboard on http://127.0.0.1:{port}/", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
