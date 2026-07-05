from pathlib import Path
import textwrap
import os

ROOT = Path("/vaults/nvme0/qsb_tower_v1")

def write(rel, text):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")

print("Installing Dashboard V1.3 Interactive Command Center...")

server = ROOT / "src" / "dashboard" / "server.py"
if server.exists():
    backup = ROOT / "src" / "dashboard" / "server.py.backup_before_interactive_v13"
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
        "providers": reg.providers(),
        "workers": reg.workers()
    }

def live_payload():
    payload = {
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
    payload["activity"] = build_activity(payload)
    return payload

def build_activity(payload):
    activity = []
    ts = payload.get("server_ts", now())

    packets = payload.get("status", {}).get("packets", []) or []
    for p in packets[:12]:
        activity.append({
            "ts": p.get("ts", ts),
            "type": "packet",
            "title": f"{p.get('source')} → {p.get('target')}",
            "detail": f"{p.get('lift_id')} · priority {p.get('priority')} · {p.get('status')}",
            "status": p.get("status", "unknown")
        })

    sections = [
        ("penthouse", payload.get("penthouse", {}).get("readiness_status")),
        ("executive", payload.get("executive", {}).get("status")),
        ("security", payload.get("security", {}).get("status")),
        ("expansion", payload.get("expansion", {}).get("expansion_status")),
        ("infrastructure", payload.get("infrastructure", {}).get("infrastructure_status")),
        ("monitoring", payload.get("monitoring", {}).get("monitoring_status")),
        ("diagnostics", payload.get("diagnostics", {}).get("diagnostic_status"))
    ]

    for name, status in sections:
        if status:
            activity.append({
                "ts": ts,
                "type": "system",
                "title": name,
                "detail": str(status),
                "status": "healthy" if status in ["healthy", "ready_for_future_qsb_kernel_4_5"] else "watch"
            })

    return activity[:24]

HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>QSB Tower V1.3 Interactive Command Center</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{
  --bg:#030814;
  --panel:#07172a;
  --panel2:#0b213a;
  --line:#24476b;
  --line2:#356997;
  --text:#e8f2ff;
  --muted:#8ea9c7;
  --gold:#ffd45a;
  --green:#71ffb0;
  --blue:#74c7ff;
  --purple:#bd9cff;
  --red:#ff7373;
  --orange:#ffc17a;
  --cyan:#78e5ff;
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
  height:86px;
  padding:14px 20px;
  border-bottom:1px solid var(--line);
  background:rgba(7,23,42,.90);
  backdrop-filter: blur(10px);
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:12px;
}

h1{
  margin:0;
  color:var(--gold);
  font-size:24px;
  letter-spacing:.3px;
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
  white-space:nowrap;
}

.layout{
  height:calc(100vh - 86px);
  display:grid;
  grid-template-columns:minmax(670px, 1.25fr) minmax(455px, .82fr);
  grid-template-rows:1fr 118px;
  gap:12px;
  padding:12px;
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
  min-height:72px;
  display:grid;
  grid-template-columns:1fr auto;
  gap:10px;
  padding:10px 12px;
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

.mini-map{
  grid-column:1 / -1;
  display:flex;
  gap:7px;
  flex-wrap:wrap;
  align-items:center;
}

.zone-button{
  cursor:pointer;
  border:1px solid rgba(116,199,255,.28);
  background:rgba(6,17,31,.76);
  color:#dff1ff;
  border-radius:999px;
  padding:5px 10px;
  font-size:12px;
  transition:.2s ease;
}

.zone-button:hover{
  border-color:var(--gold);
  color:var(--gold);
}

.legend{
  margin-left:auto;
  display:flex;
  gap:8px;
  flex-wrap:wrap;
  color:var(--muted);
  font-size:11px;
}

.legend span{display:flex;align-items:center;gap:4px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot.active{background:var(--green);box-shadow:0 0 8px var(--green)}
.dot.vacant{background:#8fb7e8}
.dot.exec{background:#ff95df}
.dot.security{background:#ff7373}
.dot.service{background:#fff095}

.tower-viewport{
  position:relative;
  height:calc(100% - 72px);
  padding:12px 16px;
  overflow:auto;
}

.skyscraper-shell{
  position:relative;
  min-height:1260px;
  max-width:1010px;
  margin:0 auto;
  border-left:2px solid rgba(116,199,255,.25);
  border-right:2px solid rgba(116,199,255,.25);
  background:linear-gradient(90deg,rgba(255,255,255,.025),rgba(255,255,255,.075),rgba(255,255,255,.025));
  box-shadow:0 0 40px rgba(116,199,255,.08);
}

.packet-layer{
  position:absolute;
  inset:42px 125px 88px 0;
  pointer-events:none;
  overflow:hidden;
  z-index:4;
}

.packet-trail{
  position:absolute;
  width:2px;
  border-radius:99px;
  background:linear-gradient(180deg, transparent, rgba(120,229,255,.95), transparent);
  box-shadow:0 0 14px rgba(120,229,255,.6);
  animation:packetFlow 2.4s linear infinite;
  opacity:.78;
}

.packet-dot{
  position:absolute;
  width:8px;
  height:8px;
  border-radius:50%;
  background:var(--cyan);
  box-shadow:0 0 14px var(--cyan);
  animation:packetPulse 1s ease-in-out infinite;
}

.roof-row,.penthouse-row,.ground-row,.basement-row{
  height:28px;
  margin:2px 152px 2px 12px;
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
  cursor:pointer;
}
.ground-row{background:rgba(20,52,90,.85);border:1px solid rgba(116,199,255,.42)}
.basement-row{background:rgba(75,47,0,.72);border:1px solid rgba(255,212,90,.35)}

.floor-stack{
  position:relative;
  margin-right:152px;
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
  transition:all .22s ease;
  cursor:pointer;
  position:relative;
  z-index:6;
}

.floor-row:hover{
  transform:translateX(5px);
  border-color:rgba(255,212,90,.8);
  box-shadow:0 0 13px rgba(255,212,90,.2);
}

.floor-row.selected{
  border-color:var(--gold);
  box-shadow:0 0 20px rgba(255,212,90,.34), inset 0 0 18px rgba(255,212,90,.08);
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

.executive-floor{border-color:rgba(255,149,223,.34)}
.security-floor{border-color:rgba(255,115,115,.34)}
.service-floor{border-color:rgba(255,240,149,.34)}

.lift-overlay{
  position:absolute;
  top:42px;
  right:12px;
  width:140px;
  height:calc(100% - 95px);
  pointer-events:auto;
  z-index:10;
}

.lift-shaft{
  position:absolute;
  top:0;
  bottom:0;
  width:10px;
  border-left:1px solid rgba(116,199,255,.16);
  border-right:1px solid rgba(116,199,255,.16);
  background:rgba(0,0,0,.24);
  border-radius:8px;
  cursor:pointer;
}

.lift-shaft:hover{
  border-color:var(--gold);
  box-shadow:0 0 14px rgba(255,212,90,.25);
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

.lift-short{
  position:absolute;
  top:-18px;
  left:-12px;
  min-width:34px;
  text-align:center;
  color:#bfe8ff;
  font-size:9px;
  border:1px solid rgba(116,199,255,.25);
  background:rgba(6,17,31,.85);
  border-radius:6px;
  padding:2px 3px;
}

.inspector{
  border:1px solid rgba(255,212,90,.35);
  background:rgba(90,57,0,.10);
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

.banner{
  padding:10px 12px;
  border:1px solid rgba(255,212,90,.55);
  background:rgba(90,57,0,.22);
  color:#ffe49a;
  border-radius:12px;
  margin-bottom:12px;
  box-shadow:0 0 20px rgba(255,212,90,.10);
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
  cursor:pointer;
}

.list-item:hover{
  border-color:var(--gold);
}

.badge{
  border:1px solid rgba(116,199,255,.28);
  border-radius:999px;
  padding:2px 7px;
  color:#cce7ff;
  font-size:10px;
  white-space:nowrap;
}
.badge.good{border-color:rgba(113,255,176,.5);color:var(--green)}
.badge.gold{border-color:rgba(255,212,90,.5);color:var(--gold)}
.badge.warn{border-color:rgba(255,193,122,.5);color:var(--orange)}
.badge.bad{border-color:rgba(255,115,115,.5);color:var(--red)}
.badge.blue{border-color:rgba(116,199,255,.5);color:var(--blue)}

pre.inspect-json{
  background:rgba(5,12,22,.78);
  border:1px solid rgba(116,199,255,.14);
  border-radius:10px;
  padding:10px;
  margin:0;
  max-height:220px;
  overflow:auto;
  color:#dff1ff;
  font-size:12px;
}

.activity-feed{
  grid-column:1 / -1;
  border:1px solid var(--line);
  border-radius:16px;
  background:rgba(7,23,42,.86);
  overflow:hidden;
  display:grid;
  grid-template-columns:180px 1fr;
}

.activity-title{
  display:flex;
  align-items:center;
  justify-content:center;
  border-right:1px solid rgba(116,199,255,.16);
  color:var(--gold);
  font-weight:bold;
}

.activity-items{
  display:flex;
  gap:8px;
  overflow:hidden;
  align-items:center;
  padding:10px;
}

.activity-card{
  min-width:250px;
  max-width:320px;
  background:rgba(5,12,22,.78);
  border:1px solid rgba(116,199,255,.14);
  border-radius:12px;
  padding:8px 10px;
  font-size:12px;
  animation:activityGlow 3s infinite;
}

.activity-card b{color:#fff}
.activity-card div{color:var(--muted);margin-top:4px}

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
@keyframes packetFlow{
  0%{opacity:.05;transform:translateY(-16px)}
  50%{opacity:.95}
  100%{opacity:.05;transform:translateY(16px)}
}
@keyframes packetPulse{
  0%,100%{transform:scale(.8);opacity:.55}
  50%{transform:scale(1.45);opacity:1}
}
@keyframes activityGlow{
  0%,100%{box-shadow:0 0 8px rgba(116,199,255,.06)}
  50%{box-shadow:0 0 15px rgba(116,199,255,.18)}
}

@media(max-width:1150px){
  body{overflow:auto}
  .layout{height:auto;grid-template-columns:1fr;grid-template-rows:auto auto auto}
  .tower-scene{height:900px}
  .activity-feed{grid-template-columns:1fr}
  .activity-title{border-right:0;border-bottom:1px solid rgba(116,199,255,.16);padding:8px}
}
</style>
</head>
<body>
<header>
  <div>
    <h1>QSB Tower V1.3 — Interactive Command Center</h1>
    <div class="subtitle">Animated skyscraper · floor inspection · lift inspection · packet trails · kernel reserved</div>
  </div>
  <div id="topStatus" class="status-pill">LOADING</div>
</header>

<div class="layout">
  <section class="tower-scene">
    <div class="scene-head">
      <div>
        <div class="scene-title">Living 53-Floor AI Headquarters</div>
      </div>
      <div class="scene-metrics" id="sceneMetrics"></div>

      <div class="mini-map">
        <button class="zone-button" onclick="jumpToZone('penthouse')">Penthouse</button>
        <button class="zone-button" onclick="jumpToZone('D')">Zone D Executive</button>
        <button class="zone-button" onclick="jumpToZone('C')">Zone C Infrastructure</button>
        <button class="zone-button" onclick="jumpToZone('B')">Zone B Services</button>
        <button class="zone-button" onclick="jumpToZone('A')">Zone A Operations</button>
        <button class="zone-button" onclick="jumpToZone('vacant')">Vacant 41–45</button>
        <button class="zone-button" onclick="jumpToZone('ground')">Ground/Basement</button>
        <div class="legend">
          <span><i class="dot active"></i>active</span>
          <span><i class="dot vacant"></i>vacant-ready</span>
          <span><i class="dot exec"></i>executive</span>
          <span><i class="dot security"></i>security</span>
          <span><i class="dot service"></i>service</span>
        </div>
      </div>
    </div>

    <div class="tower-viewport" id="towerViewport">
      <div class="skyscraper-shell" id="skyscraperShell">
        <div class="scanline"></div>
        <div id="packetLayer" class="packet-layer"></div>
        <div id="liftOverlay" class="lift-overlay"></div>

        <div class="roof-row" id="roofRow" onclick="selectSpecial('roof')"><b>ROOF</b><span>AIR LLM Cloud — external providers</span><span>external</span></div>
        <div class="penthouse-row" id="penthouseRow" onclick="selectSpecial('penthouse')"><b>PH</b><span>Reserved For Future QSB Kernel 4.5</span><span>socket ready</span></div>

        <div id="floorStack" class="floor-stack"></div>

        <div class="ground-row" id="groundRow" onclick="selectSpecial('ground')"><b>G</b><span>Reception and Command Lobby</span><span>online</span></div>
        <div class="basement-row" id="b1Row" onclick="selectSpecial('B1')"><b>B1</b><span>Core Services</span><span>online</span></div>
        <div class="basement-row" id="b2Row" onclick="selectSpecial('B2')"><b>B2</b><span>Vault and Archives</span><span>online</span></div>
        <div class="basement-row" id="b3Row" onclick="selectSpecial('B3')"><b>B3</b><span>Disaster Recovery</span><span>online</span></div>
      </div>
    </div>
  </section>

  <section class="command-grid">
    <div class="banner" id="penthouseBanner">
      Reserved For Future QSB Kernel 4.5 Installation — Kernel Installed: false
    </div>

    <div class="panel inspector">
      <h2>Inspector <span class="badge gold" id="inspectorBadge">select floor or lift</span></h2>
      <pre class="inspect-json" id="inspectorPanel">Click any floor, lift shaft, lift list item, packet, vacant floor, roof, penthouse, ground, or basement.</pre>
    </div>

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
      <h2>Lift Network <span class="badge blue">click lift</span></h2>
      <div class="list" id="liftList"></div>
    </div>

    <div class="panel">
      <h2>Recent Sealed Packets <span class="badge blue">click packet</span></h2>
      <div class="list" id="packetList"></div>
    </div>

    <div class="panel">
      <h2>Vacant-Floor Activation Preview <span class="badge gold">preview only</span></h2>
      <div class="list" id="vacantList"></div>
    </div>
  </section>

  <section class="activity-feed">
    <div class="activity-title">LIVE ACTIVITY FEED</div>
    <div class="activity-items" id="activityItems"></div>
  </section>
</div>

<script>
let LAST_DATA = null;
let SELECTED = {type:"none", id:null};

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

const liftShort = {
  "main_low_rise":"LOW",
  "main_mid_rise":"MID",
  "main_high_rise":"HIGH",
  "executive_lift":"EXEC",
  "service_lift":"SVC",
  "memory_lift":"MEM",
  "model_lift":"MODEL",
  "security_lift":"SEC",
  "emergency_stairwell":"STAIR"
};

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

function departmentModuleForFloor(floorId){
  const map = {
    "floor_05": "coding",
    "floor_21": "adapters",
    "floor_22": "integration",
    "floor_23": "air_llm",
    "floor_24": "routing",
    "floor_27": "local_models",
    "floor_28": "security",
    "floor_29": "security",
    "floor_30": "security",
    "floor_31": "security",
    "floor_32": "security",
    "floor_33": "diagnostics",
    "floor_34": "monitoring",
    "floor_35": "infrastructure",
    "floor_36": "expansion",
    "floor_46": "executive",
    "floor_47": "executive",
    "floor_48": "executive",
    "floor_49": "executive",
    "floor_50": "executive",
    "floor_51": "executive",
    "floor_52": "executive",
    "floor_53": "executive"
  };
  return map[floorId];
}

function compactFloorDetails(floor, data){
  const moduleKey = departmentModuleForFloor(floor.id);
  const module = moduleKey ? data[moduleKey] : null;
  const packets = (data.status?.packets || []).filter(p => p.source === floor.id || p.target === floor.id);
  const liftsHere = (data.status?.lifts || []).filter(l => l.current_position === floor.id);

  let vacantPreview = null;
  if(floor.vacant){
    vacantPreview = (data.expansion?.vacant_floors || []).find(v => v.floor_id === floor.id) || null;
  }

  return {
    type: "floor",
    floor_id: floor.id,
    number: floor.number,
    department: floor.department,
    zone: floor.zone,
    status: floor.status,
    vacant: !!floor.vacant,
    active_packets: packets.slice(0,8),
    lifts_currently_here: liftsHere,
    module_panel: module || "No dedicated module panel yet. Floor is registered and visible.",
    vacant_activation_preview: vacantPreview
  };
}

function selectFloor(floorId){
  SELECTED = {type:"floor", id:floorId};
  updateSelection();
}

function selectLift(liftId){
  SELECTED = {type:"lift", id:liftId};
  updateSelection();
}

function selectPacket(packetId){
  SELECTED = {type:"packet", id:String(packetId)};
  updateSelection();
}

function selectVacant(floorId){
  SELECTED = {type:"vacant", id:floorId};
  updateSelection();
}

function selectSpecial(id){
  SELECTED = {type:"special", id:id};
  updateSelection();
}

function updateSelection(){
  if(!LAST_DATA) return;

  document.querySelectorAll(".floor-row").forEach(el => {
    el.classList.toggle("selected", SELECTED.type === "floor" && el.dataset.floorId === SELECTED.id);
  });

  const badge = document.getElementById("inspectorBadge");
  const panel = document.getElementById("inspectorPanel");

  if(SELECTED.type === "floor"){
    const floor = (LAST_DATA.status?.floors || []).find(f => f.id === SELECTED.id);
    const detail = floor ? compactFloorDetails(floor, LAST_DATA) : {error:"floor not found", id:SELECTED.id};
    badge.textContent = SELECTED.id;
    panel.textContent = JSON.stringify(detail, null, 2);
    return;
  }

  if(SELECTED.type === "lift"){
    const lift = (LAST_DATA.status?.lifts || []).find(l => l.lift_id === SELECTED.id);
    const packets = (LAST_DATA.status?.packets || []).filter(p => p.lift_id === SELECTED.id);
    const liftPerm = (LAST_DATA.security?.policy ? null : null);
    badge.textContent = SELECTED.id;
    panel.textContent = JSON.stringify({
      type:"lift",
      lift_id: SELECTED.id,
      lift: lift || null,
      route_summary: liftRouteSummary(SELECTED.id),
      packets: packets.slice(0,12),
      sealed_packet_rule: SELECTED.id === "emergency_stairwell" ? "emergency route, packets optional" : "sealed packets required"
    }, null, 2);
    return;
  }

  if(SELECTED.type === "packet"){
    const packet = (LAST_DATA.status?.packets || []).find(p => String(p.id) === SELECTED.id);
    badge.textContent = "packet " + SELECTED.id;
    panel.textContent = JSON.stringify({
      type:"sealed_packet",
      packet: packet || null,
      rule: "Passenger packets share lifts but cannot inspect each other."
    }, null, 2);
    return;
  }

  if(SELECTED.type === "vacant"){
    const vacant = (LAST_DATA.expansion?.vacant_floors || []).find(v => v.floor_id === SELECTED.id);
    badge.textContent = SELECTED.id + " preview";
    panel.textContent = JSON.stringify({
      type:"vacant_floor_activation_preview",
      floor: vacant || null,
      execution_enabled: false,
      activation_execution_enabled: false,
      message: "Preview only. No floor modification is executed."
    }, null, 2);
    return;
  }

  if(SELECTED.type === "special"){
    badge.textContent = SELECTED.id;
    let detail = {};
    if(SELECTED.id === "penthouse"){
      detail = {
        type:"penthouse",
        message:"Reserved For Future QSB Kernel 4.5 Installation",
        data:LAST_DATA.penthouse
      };
    } else if(SELECTED.id === "roof"){
      detail = {
        type:"roof",
        message:"AIR LLM Cloud is external to the building.",
        providers:LAST_DATA.status?.providers,
        air_llm:LAST_DATA.air_llm
      };
    } else {
      detail = {
        type:SELECTED.id,
        message:"Building access layer",
        kernel_installed:false
      };
    }
    panel.textContent = JSON.stringify(detail, null, 2);
    return;
  }

  badge.textContent = "select floor or lift";
  panel.textContent = "Click any floor, lift shaft, lift list item, packet, vacant floor, roof, penthouse, ground, or basement.";
}

function liftRouteSummary(id){
  const routes = {
    "main_low_rise":"Ground to Floor 15",
    "main_mid_rise":"Floor 15 to Floor 30",
    "main_high_rise":"Floor 30 to Floor 45",
    "executive_lift":"Floor 45 to Floor 53 and Penthouse",
    "service_lift":"Basement to Penthouse maintenance spine",
    "memory_lift":"Basement, Memory, Knowledge, Document, Audit, Archives",
    "model_lift":"Adapter, AIR LLM, Routing, Evaluation, Local Models, Roof",
    "security_lift":"Basement to Penthouse security-controlled route",
    "emergency_stairwell":"Direct safe route from Penthouse to Basement"
  };
  return routes[id] || "registered lift";
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
      <div id="row_${id}" data-floor-id="${id}" class="${classes}" title="Click to inspect ${id}" onclick="selectFloor('${id}')">
        <div class="floor-num">${f.number}</div>
        <div class="floor-name">${f.department || f.name || id}</div>
        <div class="floor-zone">${f.zone || ""}</div>
        <div class="floor-led"></div>
      </div>
    `;
  }).join("");

  updateSelection();
}

function setupLiftShafts(){
  const overlay = document.getElementById("liftOverlay");
  if(overlay.dataset.ready === "1") return;

  overlay.innerHTML = "";
  liftOrder.forEach((id, index) => {
    const left = 4 + index * 14;
    const shaft = document.createElement("div");
    shaft.className = "lift-shaft";
    shaft.style.left = left + "px";
    shaft.id = "shaft_" + id;
    shaft.title = liftRouteSummary(id);
    shaft.onclick = () => selectLift(id);

    const car = document.createElement("div");
    car.className = "lift-car";
    car.id = "car_" + id;
    car.style.top = topPercentForPosition("ground") + "%";

    const label = document.createElement("div");
    label.className = "lift-short";
    label.textContent = liftShort[id] || id.slice(0,3).toUpperCase();

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

function renderPacketTrails(data){
  const layer = document.getElementById("packetLayer");
  const packets = (data.status?.packets || []).slice(0,10);
  layer.innerHTML = "";

  packets.forEach((p, i) => {
    const sourceTop = topPercentForPosition(p.source);
    const targetTop = topPercentForPosition(p.target);
    const top = Math.min(sourceTop, targetTop);
    const height = Math.max(18, Math.abs(targetTop - sourceTop));
    const left = 18 + (i % 8) * 10;

    const trail = document.createElement("div");
    trail.className = "packet-trail";
    trail.style.left = left + "%";
    trail.style.top = top + "%";
    trail.style.height = height + "%";
    trail.style.animationDelay = (i * 0.16) + "s";
    layer.appendChild(trail);

    const dot = document.createElement("div");
    dot.className = "packet-dot";
    dot.style.left = `calc(${left}% - 3px)`;
    dot.style.top = targetTop + "%";
    dot.style.animationDelay = (i * 0.12) + "s";
    layer.appendChild(dot);
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

  document.getElementById("penthouseBanner").textContent =
    `${ph.visible_message || "Reserved For Future QSB Kernel 4.5 Installation"} — readiness: ${ph.readiness_status || "unknown"} — kernel installed: ${yesNo(ph.kernel_installed)}`;

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
    <div class="list-item" onclick="selectLift('${l.lift_id}')">
      <div>
        <b>${l.lift_id}</b><br>
        <span style="color:var(--muted)">${liftRouteSummary(l.lift_id)}<br>position: ${l.current_position} · traffic: ${l.traffic_count}</span>
      </div>
      <span class="badge ${l.status === "online" || l.status === "available" ? "good" : "warn"}">${l.status}</span>
    </div>
  `).join("");
}

function renderPackets(data){
  const packets = data.status?.packets || [];
  document.getElementById("packetList").innerHTML = packets.slice(0,12).map(p => `
    <div class="list-item" onclick="selectPacket('${p.id}')">
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
    <div class="list-item" onclick="selectVacant('${f.floor_id}')">
      <div>
        <b>${f.floor_id} — ${f.suggested_future_use}</b><br>
        <span style="color:var(--muted)">lifts: ${(f.lift_access || []).join(", ")}</span>
      </div>
      <span class="badge gold">${f.activation_status}</span>
    </div>
  `).join("");
}

function renderActivity(data){
  const activity = data.activity || [];
  document.getElementById("activityItems").innerHTML = activity.slice(0,10).map(a => `
    <div class="activity-card">
      <b>${a.title}</b>
      <div>${a.detail}</div>
    </div>
  `).join("");
}

function jumpToZone(zone){
  let target = null;
  if(zone === "penthouse") target = document.getElementById("penthouseRow");
  if(zone === "ground") target = document.getElementById("groundRow");
  if(zone === "vacant") target = document.getElementById("row_floor_45");
  if(zone === "D") target = document.getElementById("row_floor_53");
  if(zone === "C") target = document.getElementById("row_floor_36");
  if(zone === "B") target = document.getElementById("row_floor_24");
  if(zone === "A") target = document.getElementById("row_floor_15");

  if(target){
    target.scrollIntoView({behavior:"smooth", block:"center"});
  }
}

async function load(){
  try{
    const res = await fetch("/api/live", {cache:"no-store"});
    const data = await res.json();
    LAST_DATA = data;
    renderFloors(data);
    renderLifts(data);
    renderPacketTrails(data);
    renderPanels(data);
    renderLiftList(data);
    renderPackets(data);
    renderVacant(data);
    renderActivity(data);
    updateSelection();
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
    print("Interactive Command Center: http://127.0.0.1:8765")
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
''')

write("tests/test_interactive_dashboard_v13.py", """
import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src' / 'dashboard' / 'server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('interactive_dashboard_server', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

required = [
    'Interactive Command Center',
    'selectFloor',
    'selectLift',
    'packet-trail',
    'zone-button',
    'Vacant-Floor Activation Preview',
    'LIVE ACTIVITY FEED',
    'penthouseBanner',
    'inspectorPanel'
]

for item in required:
    assert item in mod.HTML, f'Missing dashboard feature: {item}'

payload = mod.live_payload()
assert payload['status']['counts']['floors'] == 53
assert payload['status']['counts']['lifts'] >= 9
assert payload['status']['counts']['kernel_installed'] is False
assert 'activity' in payload
assert 'penthouse' in payload
assert 'expansion' in payload

print('INTERACTIVE DASHBOARD V1.3 VALIDATION PASSED')
print('Floors:', payload['status']['counts']['floors'])
print('Lifts:', payload['status']['counts']['lifts'])
print('Kernel installed:', payload['status']['counts']['kernel_installed'])
print('Activity records:', len(payload['activity']))
""")

write("scripts/interactive_dashboard_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 tests/test_interactive_dashboard_v13.py
""")

os.chmod(ROOT / "scripts" / "interactive_dashboard_status.sh", 0o755)

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Interactive Command Center Dashboard V1.3

The dashboard now includes:
- Click a floor to inspect that floor
- Click a lift shaft or lift list item to inspect lift route and packets
- Click a packet to inspect sealed packet details
- Animated packet trails between floors
- Better compact lift labels
- Floor status legend
- Mini-map / zone selector
- Penthouse readiness banner
- Vacant-floor activation preview
- Live activity feed at the bottom

The dashboard still does not install or run QSB Kernel 4.5.
Kernel installed remains false.

Commands:
cd /vaults/nvme0/qsb_tower_v1
python3 tests/test_interactive_dashboard_v13.py
./scripts/interactive_dashboard_status.sh
./restart.sh
"""

if "Interactive Command Center Dashboard V1.3" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Interactive Command Center Dashboard V1.3 installed.")
print("Run:")
print("python3 tests/test_interactive_dashboard_v13.py")
print("./restart.sh")
