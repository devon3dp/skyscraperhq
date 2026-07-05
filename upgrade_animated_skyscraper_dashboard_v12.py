from pathlib import Path
import textwrap
import os

ROOT = Path("/vaults/nvme0/qsb_tower_v1")

def write(rel, text):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")

print("Installing Animated Skyscraper Dashboard V1.2...")

server = ROOT / "src" / "dashboard" / "server.py"
if server.exists():
    backup = ROOT / "src" / "dashboard" / "server.py.backup_before_animated_v12"
    backup.write_text(server.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Backup written: {backup}")

write("src/dashboard/server.py", r'''
import sys
import json
import importlib
from pathlib import Path
from datetime import datetime, UTC
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

from tower.registry import Registry
from tower.database import init_db
from tower.lifts import LiftNetwork

def now():
    return datetime.now(UTC).isoformat()

def safe_dashboard(module_name, class_name):
    try:
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        return cls().dashboard()
    except Exception as e:
        return {
            "status": "error",
            "module": module_name,
            "class": class_name,
            "error": str(e)
        }

def core_status():
    init_db()
    reg = Registry()
    lifts = LiftNetwork()
    floors = reg.floors()
    return {
        "building": reg.building(),
        "floors": floors,
        "counts": {
            "floors": len(floors),
            "vacant": len([f for f in floors if f.get("vacant")]),
            "lifts": len(reg.lifts()),
            "workers": len(reg.workers()),
            "kernel_installed": False
        },
        "lifts": lifts.states(),
        "packets": lifts.packets(),
        "providers": reg.providers()
    }

def live_payload():
    return {
        "server_ts": now(),
        "status": core_status(),
        "penthouse": safe_dashboard("tower.penthouse_readiness", "PenthouseReadiness"),
        "executive": safe_dashboard("tower.executive_command", "ExecutiveCommand"),
        "security": safe_dashboard("tower.security_spine", "SecuritySpine"),
        "expansion": safe_dashboard("tower.expansion_planning", "ExpansionPlanning"),
        "infrastructure": safe_dashboard("tower.infrastructure_services", "InfrastructureServices"),
        "monitoring": safe_dashboard("tower.monitoring_department", "MonitoringDepartment"),
        "diagnostics": safe_dashboard("tower.diagnostics_department", "DiagnosticsDepartment"),
        "integration": safe_dashboard("tower.integration_services", "IntegrationServices"),
        "adapters": safe_dashboard("tower.adapter_systems", "AdapterSystems"),
        "coding": safe_dashboard("tower.coding_department", "CodingDepartment"),
        "routing": safe_dashboard("tower.model_routing_department", "ModelRoutingDepartment"),
        "local_models": safe_dashboard("tower.local_model_operations", "LocalModelOperations"),
        "air_llm": safe_dashboard("tower.air_llm_operations", "AirLLMOperations"),
        "model_infrastructure": safe_dashboard("tower.model_infrastructure", "ModelInfrastructure")
    }

HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>QSB Tower V1.2 Animated Skyscraper</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{
  --bg:#030814;
  --panel:#07172a;
  --panel2:#0b213a;
  --line:#24476b;
  --text:#e8f2ff;
  --muted:#8ea9c7;
  --gold:#ffd45a;
  --green:#71ffb0;
  --blue:#74c7ff;
  --purple:#bd9cff;
  --red:#ff7373;
  --orange:#ffc17a;
}

*{box-sizing:border-box}
body{
  margin:0;
  background:
    radial-gradient(circle at 20% 10%, rgba(63,120,255,.22), transparent 35%),
    radial-gradient(circle at 80% 20%, rgba(255,212,90,.12), transparent 30%),
    linear-gradient(180deg,#030814,#06111f 55%,#02050b);
  color:var(--text);
  font-family:Arial, Helvetica, sans-serif;
  overflow:hidden;
}

header{
  height:78px;
  padding:16px 22px;
  border-bottom:1px solid var(--line);
  background:rgba(7,23,42,.88);
  backdrop-filter: blur(10px);
  display:flex;
  justify-content:space-between;
  align-items:center;
}

h1{
  margin:0;
  color:var(--gold);
  font-size:25px;
  letter-spacing:.4px;
}

.subtitle{color:var(--muted);font-size:13px;margin-top:5px}
.status-pill{
  padding:9px 13px;
  border:1px solid rgba(113,255,176,.5);
  border-radius:999px;
  color:var(--green);
  background:rgba(28,77,53,.35);
  font-weight:bold;
  box-shadow:0 0 18px rgba(113,255,176,.15);
}

.layout{
  height:calc(100vh - 78px);
  display:grid;
  grid-template-columns:minmax(600px, 1.25fr) minmax(430px, .8fr);
  gap:14px;
  padding:14px;
}

.tower-scene{
  position:relative;
  overflow:hidden;
  border:1px solid var(--line);
  border-radius:18px;
  background:
    linear-gradient(90deg, rgba(255,255,255,.03) 1px, transparent 1px),
    linear-gradient(180deg, rgba(255,255,255,.03) 1px, transparent 1px),
    linear-gradient(180deg, rgba(10,32,56,.95), rgba(3,8,20,.96));
  background-size:40px 40px,40px 40px,auto;
  box-shadow:0 0 35px rgba(0,0,0,.35), inset 0 0 70px rgba(116,199,255,.04);
}

.scene-head{
  height:54px;
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:10px 14px;
  border-bottom:1px solid rgba(116,199,255,.18);
  background:rgba(0,0,0,.18);
}

.scene-title{font-size:17px;font-weight:bold;color:#dff1ff}
.scene-metrics{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.metric{
  border:1px solid rgba(116,199,255,.28);
  background:rgba(6,17,31,.72);
  border-radius:10px;
  padding:6px 9px;
  font-size:12px;
  color:#cce7ff;
}

.tower-viewport{
  position:relative;
  height:calc(100% - 54px);
  padding:12px 16px 12px 16px;
  overflow:auto;
}

.skyscraper-shell{
  position:relative;
  min-height:1260px;
  max-width:980px;
  margin:0 auto;
  border-left:2px solid rgba(116,199,255,.25);
  border-right:2px solid rgba(116,199,255,.25);
  background:linear-gradient(90deg,rgba(255,255,255,.025),rgba(255,255,255,.075),rgba(255,255,255,.025));
  box-shadow:0 0 40px rgba(116,199,255,.08);
}

.roof-row,.penthouse-row,.ground-row,.basement-row{
  height:28px;
  margin:2px 120px 2px 12px;
  border-radius:7px;
  display:grid;
  grid-template-columns:58px 1fr 100px;
  align-items:center;
  gap:8px;
  padding:0 8px;
  font-size:12px;
  font-weight:bold;
}

.roof-row{background:rgba(24,56,95,.78);border:1px solid rgba(154,199,255,.75)}
.penthouse-row{
  background:rgba(90,57,0,.88);
  border:1px solid var(--gold);
  color:#ffe49a;
  animation:goldPulse 2.8s infinite;
}
.ground-row{background:rgba(20,52,90,.85);border:1px solid rgba(116,199,255,.42)}
.basement-row{background:rgba(75,47,0,.72);border:1px solid rgba(255,212,90,.35)}

.floor-stack{
  position:relative;
  margin-right:120px;
  padding:3px 0;
}

.floor-row{
  height:19px;
  margin:2px 12px;
  border-radius:6px;
  display:grid;
  grid-template-columns:42px minmax(220px,1fr) 72px 56px;
  align-items:center;
  gap:6px;
  padding:0 7px;
  font-size:11px;
  border:1px solid rgba(116,199,255,.12);
  background:rgba(20,52,90,.55);
  transition:all .35s ease;
}

.floor-row:hover{
  transform:translateX(4px);
  border-color:rgba(255,212,90,.7);
}

.floor-num{color:#fff;font-weight:bold}
.floor-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.floor-zone{color:var(--muted);font-size:10px}
.floor-led{
  width:9px;height:9px;border-radius:50%;
  justify-self:end;
  background:rgba(142,169,199,.45);
  box-shadow:0 0 8px rgba(142,169,199,.1);
}

.zone-a{background:rgba(18,55,96,.56)}
.zone-b{background:rgba(20,71,90,.55)}
.zone-c{background:rgba(37,62,45,.55)}
.zone-d{background:rgba(61,27,49,.62)}
.vacant{
  background:rgba(31,41,55,.68);
  border:1px dashed rgba(143,183,232,.65);
}
.active-floor{
  border-color:rgba(113,255,176,.82);
  box-shadow:0 0 12px rgba(113,255,176,.22), inset 0 0 14px rgba(113,255,176,.07);
}
.active-floor .floor-led{
  background:var(--green);
  animation:ledPulse 1.2s infinite;
}
.executive-floor{
  border-color:rgba(255,149,223,.34);
}
.security-floor{
  border-color:rgba(255,115,115,.34);
}
.service-floor{
  border-color:rgba(255,240,149,.34);
}

.lift-overlay{
  position:absolute;
  top:42px;
  right:13px;
  width:110px;
  height:calc(100% - 95px);
  pointer-events:none;
}

.lift-shaft{
  position:absolute;
  top:0;
  bottom:0;
  width:10px;
  border-left:1px solid rgba(116,199,255,.16);
  border-right:1px solid rgba(116,199,255,.16);
  background:rgba(0,0,0,.22);
  border-radius:8px;
}

.lift-car{
  position:absolute;
  left:-5px;
  width:20px;
  height:15px;
  border-radius:5px;
  background:linear-gradient(180deg,#dff6ff,#74c7ff);
  box-shadow:0 0 14px rgba(116,199,255,.7);
  transition:top 1.4s cubic-bezier(.22,.61,.36,1);
}

.lift-car.active{
  background:linear-gradient(180deg,#eafff2,#71ffb0);
  box-shadow:0 0 18px rgba(113,255,176,.8);
  animation:elevatorPulse 1.4s infinite;
}

.lift-label{
  position:absolute;
  left:-30px;
  top:16px;
  width:70px;
  transform:rotate(-90deg);
  transform-origin:left top;
  color:#9ec8ff;
  font-size:9px;
  opacity:.7;
}

.command-grid{
  overflow:auto;
  padding-right:3px;
}

.panel{
  background:rgba(7,23,42,.82);
  border:1px solid var(--line);
  border-radius:14px;
  padding:12px;
  margin-bottom:12px;
  box-shadow:0 0 22px rgba(0,0,0,.22);
}

.panel h2{
  margin:0 0 8px 0;
  font-size:15px;
  color:#dff1ff;
  display:flex;
  justify-content:space-between;
  gap:8px;
}

.panel-grid{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px;
}

.kv{
  background:rgba(5,12,22,.78);
  border:1px solid rgba(116,199,255,.16);
  border-radius:10px;
  padding:8px;
  min-height:56px;
}

.kv .label{color:var(--muted);font-size:11px;margin-bottom:4px}
.kv .value{font-size:16px;font-weight:bold;color:#fff;word-break:break-word}
.kv.good .value{color:var(--green)}
.kv.gold .value{color:var(--gold)}
.kv.blue .value{color:var(--blue)}
.kv.warn .value{color:var(--orange)}
.kv.bad .value{color:var(--red)}

.list{
  display:flex;
  flex-direction:column;
  gap:6px;
  max-height:245px;
  overflow:auto;
}

.list-item{
  display:grid;
  grid-template-columns:1fr auto;
  gap:8px;
  background:rgba(5,12,22,.72);
  border:1px solid rgba(116,199,255,.13);
  border-radius:9px;
  padding:7px 8px;
  font-size:12px;
}

.badge{
  border:1px solid rgba(116,199,255,.28);
  border-radius:999px;
  padding:2px 7px;
  color:#cce7ff;
  font-size:10px;
}
.badge.good{border-color:rgba(113,255,176,.5);color:var(--green)}
.badge.gold{border-color:rgba(255,212,90,.5);color:var(--gold)}
.badge.warn{border-color:rgba(255,193,122,.5);color:var(--orange)}

.scanline{
  position:absolute;
  inset:0;
  background:linear-gradient(180deg, transparent, rgba(116,199,255,.08), transparent);
  animation:scan 7s linear infinite;
  pointer-events:none;
}

@keyframes scan{
  0%{transform:translateY(-100%)}
  100%{transform:translateY(100%)}
}
@keyframes ledPulse{
  0%,100%{box-shadow:0 0 5px rgba(113,255,176,.4)}
  50%{box-shadow:0 0 18px rgba(113,255,176,.95)}
}
@keyframes elevatorPulse{
  0%,100%{transform:scale(1)}
  50%{transform:scale(1.12)}
}
@keyframes goldPulse{
  0%,100%{box-shadow:0 0 10px rgba(255,212,90,.15)}
  50%{box-shadow:0 0 24px rgba(255,212,90,.38)}
}

@media(max-width:1050px){
  body{overflow:auto}
  .layout{height:auto;grid-template-columns:1fr}
  .tower-scene{height:900px}
}
</style>
</head>
<body>
<header>
  <div>
    <h1>QSB Tower V1.2 — Animated Skyscraper Cockpit</h1>
    <div class="subtitle">Reserved For Future QSB Kernel 4.5 Installation — infrastructure only, kernel not installed</div>
  </div>
  <div id="topStatus" class="status-pill">LOADING</div>
</header>

<div class="layout">
  <section class="tower-scene">
    <div class="scene-head">
      <div class="scene-title">Living 53-Floor AI Headquarters</div>
      <div class="scene-metrics" id="sceneMetrics"></div>
    </div>

    <div class="tower-viewport">
      <div class="skyscraper-shell" id="skyscraperShell">
        <div class="scanline"></div>
        <div id="liftOverlay" class="lift-overlay"></div>

        <div class="roof-row"><b>ROOF</b><span>AIR LLM Cloud — external providers</span><span>external</span></div>
        <div class="penthouse-row"><b>PH</b><span>Reserved For Future QSB Kernel 4.5</span><span>socket ready</span></div>

        <div id="floorStack" class="floor-stack"></div>

        <div class="ground-row"><b>G</b><span>Reception and Command Lobby</span><span>online</span></div>
        <div class="basement-row"><b>B1</b><span>Core Services</span><span>online</span></div>
        <div class="basement-row"><b>B2</b><span>Vault and Archives</span><span>online</span></div>
        <div class="basement-row"><b>B3</b><span>Disaster Recovery</span><span>online</span></div>
      </div>
    </div>
  </section>

  <section class="command-grid">
    <div class="panel">
      <h2>Building Core <span class="badge good">live</span></h2>
      <div class="panel-grid" id="coreGrid"></div>
    </div>

    <div class="panel">
      <h2>Penthouse / Kernel Socket <span class="badge gold">reserved</span></h2>
      <div class="panel-grid" id="penthouseGrid"></div>
    </div>

    <div class="panel">
      <h2>Command Spine <span class="badge good">healthy</span></h2>
      <div class="panel-grid" id="commandGrid"></div>
    </div>

    <div class="panel">
      <h2>Building Services <span class="badge good">watching</span></h2>
      <div class="panel-grid" id="servicesGrid"></div>
    </div>

    <div class="panel">
      <h2>Model / Provider Infrastructure <span class="badge warn">execution disabled</span></h2>
      <div class="panel-grid" id="modelGrid"></div>
    </div>

    <div class="panel">
      <h2>Lift Network <span class="badge blue">animated</span></h2>
      <div class="list" id="liftList"></div>
    </div>

    <div class="panel">
      <h2>Recent Sealed Packets <span class="badge blue">lift traffic</span></h2>
      <div class="list" id="packetList"></div>
    </div>

    <div class="panel">
      <h2>Expansion Floors <span class="badge gold">serviced vacant</span></h2>
      <div class="list" id="vacantList"></div>
    </div>
  </section>
</div>

<script>
const liftOrder = [
  "main_low_rise",
  "main_mid_rise",
  "main_high_rise",
  "executive_lift",
  "service_lift",
  "memory_lift",
  "model_lift",
  "security_lift",
  "emergency_stairwell"
];

function levelForPosition(pos){
  if(!pos) return 0;
  if(pos === "roof") return 55;
  if(pos === "penthouse") return 54;
  if(pos === "ground") return 0;
  if(pos === "B1") return -1;
  if(pos === "B2") return -2;
  if(pos === "B3") return -3;
  const m = String(pos).match(/floor_(\d+)/);
  if(m) return parseInt(m[1],10);
  return 0;
}

function topPercentForPosition(pos){
  const max = 55;
  const min = -3;
  const level = levelForPosition(pos);
  return 2 + ((max - level) / (max - min)) * 94;
}

function zoneClass(zone){
  const z = (zone || "").toLowerCase();
  if(z.includes("a")) return "zone-a";
  if(z.includes("b")) return "zone-b";
  if(z.includes("c")) return "zone-c";
  if(z.includes("d")) return "zone-d";
  return "";
}

function isExecutiveFloor(id){
  return ["floor_46","floor_47","floor_48","floor_49","floor_50","floor_51","floor_52","floor_53"].includes(id);
}

function isSecurityFloor(id){
  return ["floor_28","floor_29","floor_30","floor_31","floor_32"].includes(id);
}

function isServiceFloor(id){
  return ["floor_33","floor_34","floor_35","floor_36"].includes(id);
}

function importantFloors(){
  return new Set([
    "floor_05","floor_21","floor_22","floor_23","floor_24","floor_27",
    "floor_28","floor_29","floor_30","floor_31","floor_32",
    "floor_33","floor_34","floor_35","floor_36",
    "floor_46","floor_47","floor_48","floor_49","floor_50","floor_51","floor_52","floor_53"
  ]);
}

function packetActiveFloors(data){
  const active = importantFloors();
  const packets = data.status?.packets || [];
  packets.slice(0,20).forEach(p => {
    if(p.source && String(p.source).startsWith("floor_")) active.add(p.source);
    if(p.target && String(p.target).startsWith("floor_")) active.add(p.target);
  });
  const lifts = data.status?.lifts || [];
  lifts.forEach(l => {
    if(l.current_position && String(l.current_position).startsWith("floor_") && Number(l.traffic_count || 0) > 0){
      active.add(l.current_position);
    }
  });
  return active;
}

function renderFloors(data){
  const floors = [...(data.status?.floors || [])].sort((a,b) => Number(b.number) - Number(a.number));
  const stack = document.getElementById("floorStack");
  const active = packetActiveFloors(data);

  stack.innerHTML = floors.map(f => {
    const id = f.id || `floor_${String(f.number).padStart(2,"0")}`;
    const classes = [
      "floor-row",
      zoneClass(f.zone),
      f.vacant ? "vacant" : "",
      active.has(id) ? "active-floor" : "",
      isExecutiveFloor(id) ? "executive-floor" : "",
      isSecurityFloor(id) ? "security-floor" : "",
      isServiceFloor(id) ? "service-floor" : ""
    ].filter(Boolean).join(" ");

    return `
      <div class="${classes}" title="${id}">
        <div class="floor-num">${f.number}</div>
        <div class="floor-name">${f.department || f.name || id}</div>
        <div class="floor-zone">${f.zone || ""}</div>
        <div class="floor-led"></div>
      </div>
    `;
  }).join("");
}

function setupLiftShafts(){
  const overlay = document.getElementById("liftOverlay");
  if(overlay.dataset.ready === "1") return;

  overlay.innerHTML = "";
  liftOrder.forEach((id, index) => {
    const left = 4 + index * 12;
    const shaft = document.createElement("div");
    shaft.className = "lift-shaft";
    shaft.style.left = left + "px";
    shaft.id = "shaft_" + id;

    const car = document.createElement("div");
    car.className = "lift-car";
    car.id = "car_" + id;
    car.style.top = topPercentForPosition("ground") + "%";

    const label = document.createElement("div");
    label.className = "lift-label";
    label.textContent = id.replaceAll("_"," ");

    shaft.appendChild(car);
    shaft.appendChild(label);
    overlay.appendChild(shaft);
  });

  overlay.dataset.ready = "1";
}

function renderLifts(data){
  setupLiftShafts();

  const lifts = data.status?.lifts || [];
  const byId = {};
  lifts.forEach(l => byId[l.lift_id] = l);

  liftOrder.forEach(id => {
    const car = document.getElementById("car_" + id);
    const lift = byId[id];
    if(!car || !lift) return;
    car.style.top = topPercentForPosition(lift.current_position) + "%";
    if(Number(lift.traffic_count || 0) > 0 || id === "model_lift" || id === "service_lift"){
      car.classList.add("active");
    } else {
      car.classList.remove("active");
    }
  });
}

function kv(label, value, cls=""){
  return `<div class="kv ${cls}"><div class="label">${label}</div><div class="value">${value}</div></div>`;
}

function renderGrid(id, entries){
  document.getElementById(id).innerHTML = entries.map(e => kv(e[0], e[1], e[2] || "")).join("");
}

function yesNo(v){ return v ? "true" : "false"; }
function safe(v, fallback="—"){ return (v === undefined || v === null) ? fallback : v; }

function renderPanels(data){
  const counts = data.status?.counts || {};
  const ph = data.penthouse || {};
  const exec = data.executive || {};
  const sec = data.security || {};
  const exp = data.expansion || {};
  const infra = data.infrastructure || {};
  const mon = data.monitoring || {};
  const diag = data.diagnostics || {};
  const coding = data.coding || {};
  const routing = data.routing || {};
  const local = data.local_models || {};
  const air = data.air_llm || {};
  const adapters = data.adapters || {};
  const integration = data.integration || {};

  const towerHealthy =
    counts.floors === 53 &&
    ph.critical_failures === 0 &&
    sec.critical_failures === 0 &&
    diag.critical_failures === 0;

  document.getElementById("topStatus").textContent = towerHealthy ? "TOWER HEALTHY" : "CHECK TOWER";
  document.getElementById("topStatus").style.borderColor = towerHealthy ? "rgba(113,255,176,.5)" : "rgba(255,115,115,.6)";
  document.getElementById("topStatus").style.color = towerHealthy ? "var(--green)" : "var(--red)";

  document.getElementById("sceneMetrics").innerHTML = [
    `<div class="metric">${counts.floors || 0} Floors</div>`,
    `<div class="metric">${counts.lifts || 0} Lifts</div>`,
    `<div class="metric">${counts.workers || 0} Workers</div>`,
    `<div class="metric">${counts.vacant || 0} Vacant Ready</div>`,
    `<div class="metric">Kernel: ${counts.kernel_installed ? "installed" : "not installed"}</div>`
  ].join("");

  renderGrid("coreGrid", [
    ["Floors", counts.floors, "blue"],
    ["Vacant Ready", counts.vacant, "gold"],
    ["Lifts", counts.lifts, "blue"],
    ["Workers", counts.workers, "blue"],
    ["Kernel Installed", yesNo(counts.kernel_installed), counts.kernel_installed ? "bad" : "good"],
    ["Server Time", (data.server_ts || "").slice(11,19), "blue"]
  ]);

  renderGrid("penthouseGrid", [
    ["Readiness", safe(ph.readiness_status), "good"],
    ["Socket", safe(ph.socket_status || ph.socket?.status), "gold"],
    ["Kernel Installed", yesNo(ph.kernel_installed), ph.kernel_installed ? "bad" : "good"],
    ["Kernel Logic", yesNo(ph.kernel_logic_present), ph.kernel_logic_present ? "bad" : "good"],
    ["Checks", safe(ph.checks_run), "blue"],
    ["Failures", safe(ph.critical_failures), ph.critical_failures ? "bad" : "good"]
  ]);

  renderGrid("commandGrid", [
    ["Executive", safe(exec.status), exec.status === "healthy" ? "good" : "warn"],
    ["Security", safe(sec.status), sec.status === "healthy" ? "good" : "warn"],
    ["Expansion", safe(exp.expansion_status), exp.expansion_status === "healthy" ? "good" : "warn"],
    ["Exec Floors", safe(exec.executive_floors), "blue"],
    ["Security Gates", safe(sec.security_gates), "blue"],
    ["Vacant Floors", safe(exp.managed_vacant_floors), "gold"]
  ]);

  renderGrid("servicesGrid", [
    ["Infrastructure", safe(infra.infrastructure_status), infra.infrastructure_status === "healthy" ? "good" : "warn"],
    ["Monitoring", safe(mon.monitoring_status), mon.monitoring_status === "healthy" ? "good" : "warn"],
    ["Diagnostics", safe(diag.diagnostic_status), diag.diagnostic_status === "healthy" ? "good" : "warn"],
    ["Dashboard Online", yesNo(mon.dashboard_online), mon.dashboard_online ? "good" : "bad"],
    ["Memory %", safe(mon.memory_percent), "blue"],
    ["Free GB", safe(mon.tower_free_gb), "blue"]
  ]);

  renderGrid("modelGrid", [
    ["Adapters", safe(adapters.adapter_count), "blue"],
    ["Integration", safe(integration.integration_health), integration.integration_health === "healthy" ? "good" : "warn"],
    ["Routes", safe(routing.route_decisions), "blue"],
    ["Local Models", safe(local.detected_models), "gold"],
    ["Providers", safe(air.provider_count), "blue"],
    ["Execution", yesNo(air.execution_enabled || adapters.execution_enabled), (air.execution_enabled || adapters.execution_enabled) ? "bad" : "good"]
  ]);
}

function renderLiftList(data){
  const lifts = data.status?.lifts || [];
  document.getElementById("liftList").innerHTML = lifts.map(l => `
    <div class="list-item">
      <div>
        <b>${l.lift_id}</b><br>
        <span style="color:var(--muted)">position: ${l.current_position} · traffic: ${l.traffic_count}</span>
      </div>
      <span class="badge ${l.status === "online" || l.status === "available" ? "good" : "warn"}">${l.status}</span>
    </div>
  `).join("");
}

function renderPackets(data){
  const packets = data.status?.packets || [];
  document.getElementById("packetList").innerHTML = packets.slice(0,12).map(p => `
    <div class="list-item">
      <div>
        <b>${p.source} → ${p.target}</b><br>
        <span style="color:var(--muted)">${p.lift_id} · priority ${p.priority}</span>
      </div>
      <span class="badge ${p.status === "delivered" ? "good" : "warn"}">${p.status}</span>
    </div>
  `).join("") || `<div class="list-item"><div>No packets yet</div><span class="badge">idle</span></div>`;
}

function renderVacant(data){
  const floors = data.expansion?.vacant_floors || [];
  document.getElementById("vacantList").innerHTML = floors.map(f => `
    <div class="list-item">
      <div>
        <b>${f.floor_id} — ${f.suggested_future_use}</b><br>
        <span style="color:var(--muted)">lifts: ${(f.lift_access || []).join(", ")}</span>
      </div>
      <span class="badge gold">${f.activation_status}</span>
    </div>
  `).join("");
}

async function load(){
  try{
    const res = await fetch("/api/live", {cache:"no-store"});
    const data = await res.json();
    renderFloors(data);
    renderLifts(data);
    renderPanels(data);
    renderLiftList(data);
    renderPackets(data);
    renderVacant(data);
  }catch(e){
    document.getElementById("topStatus").textContent = "DASHBOARD ERROR";
    document.getElementById("topStatus").style.color = "var(--red)";
    console.error(e);
  }
}

load();
setInterval(load, 2200);
</script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    def send_json(self, obj):
        body = json.dumps(obj, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self):
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/live":
            return self.send_json(live_payload())

        if path == "/api/status":
            return self.send_json(core_status())

        endpoint_map = {
            "/api/penthouse_readiness": ("tower.penthouse_readiness", "PenthouseReadiness"),
            "/api/executive_command": ("tower.executive_command", "ExecutiveCommand"),
            "/api/security_spine": ("tower.security_spine", "SecuritySpine"),
            "/api/expansion_planning": ("tower.expansion_planning", "ExpansionPlanning"),
            "/api/infrastructure_services": ("tower.infrastructure_services", "InfrastructureServices"),
            "/api/monitoring_department": ("tower.monitoring_department", "MonitoringDepartment"),
            "/api/diagnostics_department": ("tower.diagnostics_department", "DiagnosticsDepartment"),
            "/api/integration_services": ("tower.integration_services", "IntegrationServices"),
            "/api/adapter_systems": ("tower.adapter_systems", "AdapterSystems"),
            "/api/coding_department": ("tower.coding_department", "CodingDepartment"),
            "/api/model_routing_department": ("tower.model_routing_department", "ModelRoutingDepartment"),
            "/api/local_model_operations": ("tower.local_model_operations", "LocalModelOperations"),
            "/api/air_llm_operations": ("tower.air_llm_operations", "AirLLMOperations"),
            "/api/model_infrastructure": ("tower.model_infrastructure", "ModelInfrastructure")
        }

        if path in endpoint_map:
            module_name, class_name = endpoint_map[path]
            return self.send_json(safe_dashboard(module_name, class_name))

        return self.send_html()

if __name__ == "__main__":
    print("Animated Dashboard: http://127.0.0.1:8765")
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
''')

write("tests/test_animated_dashboard_v12.py", """
import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src' / 'dashboard' / 'server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('animated_dashboard_server', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

assert 'Animated Skyscraper Cockpit' in mod.HTML
assert 'tower-viewport' in mod.HTML
assert 'lift-car' in mod.HTML
assert '/api/live' in mod.HTML

payload = mod.live_payload()
assert payload['status']['counts']['floors'] == 53
assert payload['status']['counts']['lifts'] >= 9
assert payload['status']['counts']['kernel_installed'] is False
assert 'penthouse' in payload
assert 'monitoring' in payload
assert 'status' in payload

print('ANIMATED DASHBOARD V1.2 VALIDATION PASSED')
print('Floors:', payload['status']['counts']['floors'])
print('Lifts:', payload['status']['counts']['lifts'])
print('Kernel installed:', payload['status']['counts']['kernel_installed'])
""")

write("scripts/animated_dashboard_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 tests/test_animated_dashboard_v12.py
""")

os.chmod(ROOT / "scripts" / "animated_dashboard_status.sh", 0o755)

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Animated Skyscraper Dashboard V1.2

The dashboard now renders the tower as a living animated skyscraper cockpit.

It includes:
- Animated 53-floor tower
- Roof and Penthouse visual layers
- Active floor glow
- Vacant expansion-ready floors
- Zone coloring
- Animated lift shafts and lift cars
- Lift traffic visualization
- Sealed packet traffic feed
- Penthouse readiness panel
- Executive Command Spine panel
- Security Spine panel
- Expansion Planning panel
- Infrastructure, Monitoring, and Diagnostics panels
- Model/provider infrastructure visibility

The dashboard still does not install or run the QSB Kernel.
Kernel installed remains false.

Commands:
cd /vaults/nvme0/qsb_tower_v1
python3 tests/test_animated_dashboard_v12.py
./scripts/animated_dashboard_status.sh
./restart.sh
"""

if "Animated Skyscraper Dashboard V1.2" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Animated Skyscraper Dashboard V1.2 installed.")
print("Run:")
print("python3 tests/test_animated_dashboard_v12.py")
print("./restart.sh")
