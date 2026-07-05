from pathlib import Path
import textwrap
import py_compile
import os

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SERVER = ROOT / "src/dashboard/server.py"

print("============================================================")
print(" QSB TOWER — DASHBOARD V1.3 CLEAN RECOVERY")
print(" Restores 53-floor animated cockpit + Floor 38 panel")
print("============================================================")

SERVER.parent.mkdir(parents=True, exist_ok=True)

if SERVER.exists():
    backup = SERVER.with_suffix(".py.backup_before_clean_dashboard_recovery")
    backup.write_text(SERVER.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Backup written: {backup}")

server_code = r'''
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from datetime import datetime, UTC
import importlib
import json
import os
import traceback

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
HOST = "127.0.0.1"
PORT = int(os.environ.get("QSB_TOWER_PORT", "8765"))

def now():
    return datetime.now(UTC).isoformat()

def load_json(rel, fallback):
    path = ROOT / rel
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e), "path": str(path)}
    return fallback

def normalize_lifts(raw):
    out = []
    for l in raw if isinstance(raw, list) else []:
        item = dict(l)
        if "id" not in item and "lift_id" in item:
            item["id"] = item["lift_id"]
        if "lift_id" not in item and "id" in item:
            item["lift_id"] = item["id"]
        item.setdefault("status", "unknown")
        item.setdefault("current_position", "ground")
        item.setdefault("traffic_count", 0)
        out.append(item)
    return out

def safe_dashboard(module_name, class_name):
    try:
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        obj = cls()
        if hasattr(obj, "dashboard"):
            return obj.dashboard()
        return {"status": "missing_dashboard_method"}
    except Exception as e:
        return {
            "status": "unavailable",
            "module": module_name,
            "class": class_name,
            "error": str(e)
        }

def safe_read_latest(rel, fallback=None):
    fallback = fallback if fallback is not None else {}
    return load_json(rel, fallback)

def live_payload():
    floors = load_json("data/registries/floors.json", [])
    lifts = normalize_lifts(load_json("data/registries/lifts.json", []))
    packets = load_json("data/packets/packets.json", [])
    if not isinstance(packets, list):
        packets = load_json("data/registries/packets.json", [])
    if not isinstance(packets, list):
        packets = []

    vacant = [f for f in floors if f.get("status") == "vacant" or "vacant" in str(f.get("department","")).lower()]
    workers = load_json("data/registries/workers.json", [])
    if not isinstance(workers, list):
        workers = []

    payload = {
        "ts": now(),
        "project": str(ROOT),
        "version": "1.3-clean-recovery",
        "floors": floors,
        "lifts": lifts,
        "packets": packets[-20:],
        "health": {
            "floors": len(floors),
            "vacant": len(vacant),
            "lifts": len(lifts),
            "workers": len(workers),
            "kernel_installed": False,
        },
        "penthouse": safe_read_latest("penthouse/kernel_occupancy_acceptance/latest_acceptance_report.json", {
            "readiness_status": "ready_for_future_qsb_kernel_4_5",
            "socket_status": "socket_ready_empty",
            "kernel_installed": False,
            "kernel_logic_present": False,
            "critical_failures": 0,
            "warnings": 0
        }),
        "security_spine": safe_dashboard("tower.security_spine", "SecuritySpine"),
        "expansion_planning": safe_dashboard("tower.expansion_planning", "ExpansionPlanning"),
        "infrastructure_services": safe_dashboard("tower.infrastructure_services", "InfrastructureServices"),
        "monitoring": safe_dashboard("tower.monitoring_department", "MonitoringDepartment"),
        "diagnostics": safe_dashboard("tower.diagnostics_department", "DiagnosticsDepartment"),
        "adapters": safe_dashboard("tower.adapter_systems", "AdapterSystems"),
        "integration": safe_dashboard("tower.integration_services", "IntegrationServices"),
        "model_infrastructure": safe_dashboard("tower.model_infrastructure", "ModelInfrastructure"),
        "agent_coordination": safe_dashboard("tower.agent_coordination", "AgentCoordination"),
        "model_evaluation": safe_dashboard("tower.model_evaluation_department", "ModelEvaluationDepartment"),
        "simulation_labs": safe_dashboard("tower.simulation_labs", "SimulationLabs"),
        "sandbox_operations": safe_dashboard("tower.sandbox_operations", "SandboxOperations"),
    }

    return payload

HTML = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>QSB Tower V1.3 — Interactive Command Center</title>
<style>
:root{
  --bg:#061827; --panel:#092238; --panel2:#071421; --line:#1c5b7a;
  --cyan:#22d3ee; --green:#38f8a7; --gold:#ffd166; --orange:#ffb347;
  --red:#ff5c7a; --blue:#7dd3fc; --text:#eaf7ff; --muted:#8fb1c7;
  --purple:#c084fc;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at top,#0b2a44 0,#061827 38%,#030b12 100%);color:var(--text);font-family:Arial,Helvetica,sans-serif;overflow:hidden}
header{height:92px;padding:22px 28px;border-bottom:1px solid #214b63;background:#071b2c;display:flex;align-items:center;justify-content:space-between}
h1{margin:0;color:var(--gold);font-size:30px;letter-spacing:.2px}
.sub{color:var(--muted);font-size:14px;margin-top:4px}
.badge{display:inline-block;padding:5px 10px;border:1px solid var(--line);border-radius:999px;font-size:12px;color:var(--blue);background:#061524}
.badge.good{border-color:#1c9b69;color:var(--green)}
.badge.warn{border-color:#9b7b1c;color:var(--gold)}
.badge.bad{border-color:#9b1c3c;color:var(--red)}
#statusBadge{font-weight:bold;font-size:15px;padding:10px 18px;border-radius:999px;border:1px solid #14875f;color:var(--green)}
main{height:calc(100vh - 92px);display:grid;grid-template-columns:58% 42%;gap:12px;padding:12px}
.card{background:rgba(7,28,45,.94);border:1px solid #1d5673;border-radius:14px;box-shadow:0 0 20px rgba(0,200,255,.06);overflow:hidden}
.left{display:grid;grid-template-rows:1fr 112px;gap:12px}
.towerCard{position:relative;padding:14px}
.card h2{font-size:16px;margin:0 0 10px 0}
.controls{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
button{background:#071421;border:1px solid #1d5673;color:var(--text);border-radius:999px;padding:7px 12px;cursor:pointer}
button:hover{border-color:var(--cyan);color:var(--cyan)}
.towerWrap{height:calc(100% - 70px);overflow:auto;padding:10px 150px 10px 40px;position:relative;border-top:1px solid rgba(125,211,252,.18)}
#towerRows{position:relative;min-height:900px}
.floor{height:25px;border:1px solid rgba(125,211,252,.22);background:linear-gradient(90deg,rgba(18,74,113,.72),rgba(6,25,41,.7));display:grid;grid-template-columns:44px 1fr 85px 32px;align-items:center;margin:2px 0;border-radius:7px;cursor:pointer;font-size:12px}
.floor:hover{outline:1px solid var(--cyan)}
.floor.active{box-shadow:0 0 12px rgba(56,248,167,.22);border-color:rgba(56,248,167,.65)}
.floor.vacant{border-style:dashed;opacity:.86}
.floor.security{box-shadow:inset 0 0 10px rgba(255,92,122,.18)}
.floor.executive{box-shadow:inset 0 0 12px rgba(192,132,252,.18)}
.floor.service{background:linear-gradient(90deg,rgba(110,69,8,.76),rgba(66,41,7,.72));border-color:rgba(255,209,102,.48)}
.floor.roof{background:linear-gradient(90deg,rgba(42,96,130,.9),rgba(22,48,70,.86))}
.num{font-weight:bold;color:#d6f5ff;text-align:center}
.name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.zone{text-align:right;color:#c8e9f7;font-size:11px}
.dot{width:11px;height:11px;border-radius:50%;background:#35566e;margin:auto}
.active .dot{background:var(--green);box-shadow:0 0 8px var(--green)}
.vacant .dot{background:#617486}
.liftBay{position:absolute;right:18px;top:72px;width:118px;bottom:22px;border-left:1px solid rgba(34,211,238,.25);border-right:1px solid rgba(34,211,238,.25);background:repeating-linear-gradient(90deg,rgba(34,211,238,.08),rgba(34,211,238,.08) 4px,transparent 4px,transparent 13px)}
.liftLabel{position:absolute;top:4px;font-size:9px;color:#9dd7ee;writing-mode:vertical-rl;opacity:.8}
.car{position:absolute;width:17px;height:15px;border-radius:5px;background:linear-gradient(180deg,#d7fff1,#28f0a2);box-shadow:0 0 16px rgba(56,248,167,.85);transition:top .7s ease;cursor:pointer}
.feed{display:grid;grid-template-columns:170px 1fr;align-items:center}
.feedTitle{height:100%;display:flex;align-items:center;padding:0 12px;color:var(--gold);font-weight:bold;border-right:1px solid #1d5673}
.feedItems{display:flex;gap:10px;overflow:hidden;padding:12px}
.feedItem{min-width:210px;background:#061524;border:1px solid #123c55;border-radius:10px;padding:10px;font-size:12px}
.right{overflow:auto;padding:0 4px 0 0}
.panel{margin-bottom:10px;padding:12px;border:1px solid #1d5673;border-radius:12px;background:rgba(7,28,45,.92)}
.panelHead{display:flex;align-items:center;justify-content:space-between;cursor:pointer}
.panel h3{margin:0;font-size:15px}
.panelGrid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
.metric{background:#061524;border:1px solid #123c55;border-radius:9px;padding:10px;min-height:56px}
.metric .k{color:var(--muted);font-size:11px}
.metric .v{font-size:16px;font-weight:bold;margin-top:4px;color:var(--blue);overflow:hidden;text-overflow:ellipsis}
.metric .v.good{color:var(--green)} .metric .v.warn{color:var(--gold)} .metric .v.bad{color:var(--red)}
pre{margin:10px 0 0 0;background:#030911;border:1px solid #123c55;border-radius:9px;padding:10px;color:#d6f5ff;max-height:190px;overflow:auto;font-size:12px}
.banner{padding:11px;border:1px solid #8e6c16;border-radius:10px;background:rgba(77,49,8,.5);color:#ffe8a3;margin-bottom:10px}
.hidden{display:none}
</style>
</head>
<body>
<header>
  <div>
    <h1>QSB Tower V1.3 — Interactive Command Center</h1>
    <div class="sub">Animated skyscraper · floor inspection · lift inspection · packet trails · kernel reserved</div>
  </div>
  <div id="statusBadge">LOADING</div>
</header>

<main>
  <section class="left">
    <div class="card towerCard">
      <h2>Living 53-Floor AI Headquarters</h2>
      <div class="controls">
        <button onclick="jump('penthouse')">Penthouse</button>
        <button onclick="jump('zoneD')">Zone D Executive</button>
        <button onclick="jump('zoneC')">Zone C Infrastructure</button>
        <button onclick="jump('zoneB')">Zone B Services</button>
        <button onclick="jump('zoneA')">Zone A Operations</button>
        <button onclick="jump('vacant')">Vacant 41–45</button>
        <button onclick="jump('ground')">Ground/Basement</button>
      </div>
      <div class="towerWrap" id="towerWrap">
        <div id="towerRows"></div>
        <div class="liftBay" id="liftBay"></div>
      </div>
    </div>

    <div class="card feed">
      <div class="feedTitle">LIVE ACTIVITY FEED</div>
      <div class="feedItems" id="feedItems"></div>
    </div>
  </section>

  <section class="right" id="rightPanels">
    <div class="banner" id="kernelBanner">Reserved For Future QSB Kernel 4.5 Installation — Kernel Installed: false</div>

    <div class="panel">
      <div class="panelHead"><h3>Inspector</h3><span class="badge warn" id="inspectBadge">select floor or lift</span></div>
      <pre id="inspector">Click any floor, lift car, packet, roof, penthouse, ground, or basement level.</pre>
    </div>

    <div id="panels"></div>
  </section>
</main>

<script>
let DATA = null;

function safe(v){ return (v === undefined || v === null || v === "") ? "—" : v; }
function yesNo(v){ return v ? "true" : "false"; }

function metric(k,v,cls=""){
  return `<div class="metric"><div class="k">${k}</div><div class="v ${cls}">${safe(v)}</div></div>`;
}

function panel(title, badge, badgeClass, items){
  return `<div class="panel">
    <div class="panelHead"><h3>${title}</h3><span class="badge ${badgeClass}">${badge}</span></div>
    <div class="panelGrid">${items.join("")}</div>
  </div>`;
}

function inspect(label, obj){
  document.getElementById("inspectBadge").textContent = label;
  document.getElementById("inspector").textContent = JSON.stringify(obj, null, 2);
}

function rowClass(x){
  const dep = String(x.department || x.name || "").toLowerCase();
  const id = String(x.id || x.floor_id || "");
  const z = String(x.zone || "");
  let c = "floor";
  if(dep.includes("vacant")) c += " vacant";
  if(dep.includes("security") || dep.includes("guardian") || dep.includes("permission") || dep.includes("audit") || dep.includes("compliance")) c += " security";
  if(z.includes("D")) c += " executive";
  if(["roof","penthouse","ground","B1","B2","B3"].includes(id) || ["ROOF","PH","G","B1","B2","B3"].includes(String(x.number))) c += " service";
  if(id === "roof") c += " roof";
  if(!c.includes("vacant")) c += " active";
  return c;
}

function floorNumberToTop(pos){
  let n = 0;
  if(!pos) return 520;
  let s = String(pos);
  if(s === "roof") n = 56;
  else if(s === "penthouse" || s === "PH") n = 55;
  else if(s === "ground") n = 0;
  else if(s === "B1") n = -1;
  else if(s === "B2") n = -2;
  else if(s === "B3") n = -3;
  else {
    let m = s.match(/floor_(\d+)/);
    if(m) n = parseInt(m[1]);
  }
  return Math.max(8, 760 - ((n + 3) * 13));
}

function renderTower(data){
  const floors = Array.isArray(data.floors) ? data.floors.slice() : [];
  floors.sort((a,b)=>(b.number||0)-(a.number||0));

  const rows = [
    {id:"roof", number:"ROOF", department:"AIR LLM Cloud — external providers", zone:"external", status:"external"},
    {id:"penthouse", number:"PH", department:"Reserved For Future QSB Kernel 4.5", zone:"socket ready", status:"reserved"},
    ...floors,
    {id:"ground", number:"G", department:"Reception and Command Lobby", zone:"online", status:"online"},
    {id:"B1", number:"B1", department:"Core Services", zone:"online", status:"online"},
    {id:"B2", number:"B2", department:"Vault and Archives", zone:"online", status:"online"},
    {id:"B3", number:"B3", department:"Disaster Recovery", zone:"online", status:"online"},
  ];

  const tower = document.getElementById("towerRows");
  tower.innerHTML = "";
  rows.forEach(x=>{
    const div = document.createElement("div");
    div.className = rowClass(x);
    div.dataset.id = x.id || x.floor_id;
    div.dataset.zone = x.zone || "";
    div.innerHTML = `<div class="num">${safe(x.number)}</div><div class="name">${safe(x.department || x.name)}</div><div class="zone">${safe(x.zone)}</div><div class="dot"></div>`;
    div.onclick = ()=>inspect(String(x.id || x.floor_id || x.number), x);
    tower.appendChild(div);
  });

  const bay = document.getElementById("liftBay");
  bay.innerHTML = "";
  const lifts = Array.isArray(data.lifts) ? data.lifts : [];
  lifts.forEach((l, i)=>{
    const label = document.createElement("div");
    label.className = "liftLabel";
    label.style.left = (6 + i*12) + "px";
    label.textContent = (l.id || l.lift_id || "lift").replaceAll("_"," ");
    bay.appendChild(label);

    const car = document.createElement("div");
    car.className = "car";
    car.style.left = (4 + i*12) + "px";
    car.style.top = floorNumberToTop(l.current_position) + "px";
    car.title = `${l.id || l.lift_id} — ${l.current_position}`;
    car.onclick = ()=>inspect(l.id || l.lift_id || "lift", l);
    bay.appendChild(car);
  });
}

function renderFeed(data){
  const feed = document.getElementById("feedItems");
  const packets = Array.isArray(data.packets) ? data.packets.slice(-8).reverse() : [];
  if(!packets.length){
    feed.innerHTML = `<div class="feedItem">No recent live packets. Simulation and sandbox records remain safe.</div>`;
    return;
  }
  feed.innerHTML = packets.map(p=>{
    return `<div class="feedItem" onclick='inspect("packet", ${JSON.stringify(JSON.stringify(p))})'>
      <b>${safe(p.source)} → ${safe(p.target)}</b><br/>
      ${safe(p.lift || p.lift_id)} · priority ${safe(p.priority)} · ${safe(p.status || p.receipt)}
    </div>`;
  }).join("");
}

function renderPanels(data){
  const h = data.health || {};
  const p = data.penthouse || {};
  const sec = data.security_spine || {};
  const exp = data.expansion_planning || {};
  const infra = data.infrastructure_services || {};
  const mon = data.monitoring || {};
  const diag = data.diagnostics || {};
  const model = data.model_infrastructure || {};
  const agent = data.agent_coordination || {};
  const me = data.model_evaluation || {};
  const sim = data.simulation_labs || {};
  const sb = data.sandbox_operations || {};

  document.getElementById("kernelBanner").textContent =
    `Reserved For Future QSB Kernel 4.5 Installation — readiness: ${safe(p.readiness_status)} — kernel installed: ${yesNo(p.kernel_installed)}`;

  const panels = [];

  panels.push(panel("Building Core","live","good",[
    metric("Floors",h.floors,""),
    metric("Vacant Ready",h.vacant,"warn"),
    metric("Lifts",h.lifts,""),
    metric("Workers",h.workers,""),
    metric("Kernel Installed",yesNo(h.kernel_installed),"good"),
    metric("Server Time",new Date().toLocaleTimeString(),"")
  ]));

  panels.push(panel("Penthouse / Kernel Socket","reserved","warn",[
    metric("Readiness",p.readiness_status,"good"),
    metric("Socket",p.socket_status,"warn"),
    metric("Kernel Installed",yesNo(p.kernel_installed),"good"),
    metric("Kernel Logic",yesNo(p.kernel_logic_present),"good"),
    metric("Failures",p.critical_failures || 0,"good"),
    metric("Warnings",p.warnings || 0,"good")
  ]));

  panels.push(panel("Command Spine","healthy","good",[
    metric("Security",sec.status,sec.status==="healthy"?"good":"warn"),
    metric("Expansion",exp.expansion_status || exp.status,(exp.expansion_status==="healthy"||exp.status==="healthy")?"good":"warn"),
    metric("Diagnostics",diag.diagnostic_status || diag.status,"good"),
    metric("Monitoring",mon.monitoring_status || mon.status,"good")
  ]));

  panels.push(panel("Model / Provider Infrastructure","execution disabled","warn",[
    metric("Model Infra",model.discovered_local_models || model.status,""),
    metric("Worker Recruit",agent.status,agent.status==="healthy"?"good":"warn"),
    metric("Model Eval",me.status,me.status==="healthy"?"good":"warn"),
    metric("Model Calls",yesNo(me.model_inference_enabled),"good")
  ]));

  panels.push(panel("Floor 25 Worker Recruitment","candidate only","warn",[
    metric("Status",agent.status,agent.status==="healthy"?"good":"warn"),
    metric("Candidates",agent.candidate_workers,""),
    metric("Worker Slots",agent.worker_slots,""),
    metric("Live Dispatch",yesNo(agent.live_dispatch_enabled),"good")
  ]));

  panels.push(panel("Floor 26 Model Evaluation","static only","warn",[
    metric("Status",me.status,me.status==="healthy"?"good":"warn"),
    metric("Candidates",me.candidate_count,""),
    metric("Average Score",me.average_score,"warn"),
    metric("Recommendation",me.activation_recommendation,"")
  ]));

  panels.push(panel("Floor 37 Simulation Labs","dry-run","good",[
    metric("Status",sim.status,sim.status==="healthy"?"good":"warn"),
    metric("Scenarios",sim.scenario_count,""),
    metric("Passed",sim.passed_scenarios,"good"),
    metric("Packets Simulated",sim.packets_simulated,"warn")
  ]));

  panels.push(panel("Floor 38 Sandbox Operations","contained","good",[
    metric("Status",sb.status,sb.status==="healthy"?"good":"warn"),
    metric("Envelopes",sb.envelope_count,""),
    metric("Contained",sb.contained_envelopes,"good"),
    metric("Rejected",sb.rejected_envelopes,sb.rejected_envelopes ? "bad":"good"),
    metric("Network",yesNo(sb.network_enabled),"good"),
    metric("Mode",sb.dry_run_only ? "sealed_metadata" : "unknown","")
  ]));

  panels.push(panel("Lift Network","click lift","",[
    metric("Lift Count",(data.lifts || []).length,""),
    metric("Recent Packets",(data.packets || []).length,""),
  ]) + `<pre>${JSON.stringify(data.lifts || [], null, 2)}</pre>`);

  document.getElementById("panels").innerHTML = panels.join("");
}

function render(data){
  DATA = data;
  renderTower(data);
  renderPanels(data);
  renderFeed(data);
  const ok = data.health && data.health.floors === 53 && data.health.kernel_installed === false;
  const badge = document.getElementById("statusBadge");
  badge.textContent = ok ? "TOWER HEALTHY" : "CHECKING";
}

async function refresh(){
  try{
    const r = await fetch("/api/live?ts=" + Date.now());
    const data = await r.json();
    render(data);
  }catch(e){
    document.getElementById("statusBadge").textContent = "DASHBOARD ERROR";
    document.getElementById("inspector").textContent = String(e);
  }
}

function jump(where){
  const wrap = document.getElementById("towerWrap");
  const selector = {
    penthouse: '[data-id="penthouse"]',
    zoneD: '[data-zone="ZONE D"]',
    zoneC: '[data-zone="ZONE C"]',
    zoneB: '[data-zone="ZONE B"]',
    zoneA: '[data-zone="ZONE A"]',
    vacant: '[data-id="floor_45"]',
    ground: '[data-id="ground"]'
  }[where];
  const el = selector ? document.querySelector(selector) : null;
  if(el) wrap.scrollTop = Math.max(0, el.offsetTop - 80);
}

refresh();
setInterval(refresh, 2500);
</script>
</body>
</html>'''

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path in ["/", "/index.html"]:
                return self._send(200, HTML)

            if path == "/api/live":
                return self._send(200, json.dumps(live_payload(), indent=2), "application/json; charset=utf-8")

            endpoint_map = {
                "/api/sandbox_operations": ("tower.sandbox_operations", "SandboxOperations"),
                "/api/simulation_labs": ("tower.simulation_labs", "SimulationLabs"),
                "/api/model_evaluation_department": ("tower.model_evaluation_department", "ModelEvaluationDepartment"),
                "/api/agent_coordination": ("tower.agent_coordination", "AgentCoordination"),
            }

            if path in endpoint_map:
                mod, cls = endpoint_map[path]
                return self._send(200, json.dumps(safe_dashboard(mod, cls), indent=2), "application/json; charset=utf-8")

            return self._send(404, json.dumps({"error": "not found", "path": path}), "application/json; charset=utf-8")

        except Exception as e:
            return self._send(500, json.dumps({
                "error": str(e),
                "traceback": traceback.format_exc()
            }, indent=2), "application/json; charset=utf-8")

def main():
    os.chdir(ROOT)
    print(f"QSB Tower V1.3 dashboard running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
'''

SERVER.write_text(server_code, encoding="utf-8")
py_compile.compile(str(SERVER), doraise=True)

print("Clean dashboard server.py written and compiled.")
print("Dashboard restored to dynamic 53-floor renderer with Floor 38 panel.")
