from pathlib import Path
from datetime import datetime, UTC
import json
import os
import sqlite3
import textwrap

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"

def now():
    return datetime.now(UTC).isoformat()

def write(rel, text):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")

def write_json(rel, obj):
    write(rel, json.dumps(obj, indent=2))

def read_json(rel, fallback):
    path = ROOT / rel
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

print("Installing Floor 23 AIR LLM Operations Department V1.1...")

for folder in [
    "floors/floor_23_air_llm_operations_department/provider_sockets",
    "floors/floor_23_air_llm_operations_department/provider_health",
    "floors/floor_23_air_llm_operations_department/provider_capabilities",
    "floors/floor_23_air_llm_operations_department/external_handoff",
    "floors/floor_23_air_llm_operations_department/roof_links",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower",
    "src/dashboard"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

external_provider_capabilities = [
    {
        "provider": "air_llm_cloud",
        "display_name": "AIR LLM Cloud",
        "socket_id": "air_llm_cloud_socket",
        "location": "roof_external_layer",
        "capabilities": ["external_gateway", "future_multi_provider", "cloud_router"],
        "execution_enabled": False,
        "hardwired": False,
        "status": "not_connected"
    },
    {
        "provider": "claude",
        "display_name": "Claude",
        "socket_id": "claude_socket",
        "location": "external_provider",
        "capabilities": ["reasoning", "writing", "coding", "analysis", "claude_code_handoff"],
        "execution_enabled": False,
        "hardwired": False,
        "status": "not_connected"
    },
    {
        "provider": "openai",
        "display_name": "OpenAI",
        "socket_id": "openai_socket",
        "location": "external_provider",
        "capabilities": ["reasoning", "writing", "coding", "vision", "tool_use"],
        "execution_enabled": False,
        "hardwired": False,
        "status": "not_connected"
    },
    {
        "provider": "gemini",
        "display_name": "Gemini",
        "socket_id": "gemini_socket",
        "location": "external_provider",
        "capabilities": ["reasoning", "vision", "long_context", "multimodal"],
        "execution_enabled": False,
        "hardwired": False,
        "status": "not_connected"
    },
    {
        "provider": "deepseek",
        "display_name": "DeepSeek",
        "socket_id": "deepseek_socket",
        "location": "external_provider",
        "capabilities": ["coding", "reasoning", "analysis"],
        "execution_enabled": False,
        "hardwired": False,
        "status": "not_connected"
    },
    {
        "provider": "future_models",
        "display_name": "Future Models",
        "socket_id": "future_model_socket",
        "location": "future_external_or_local_provider",
        "capabilities": ["expansion_ready"],
        "execution_enabled": False,
        "hardwired": False,
        "status": "expansion_ready"
    }
]

external_provider_policy = {
    "version": "1.1",
    "floor_id": "floor_23",
    "department": "AIR LLM Operations Department",
    "role": "external_provider_socket_layer",
    "providers_are_external": True,
    "tower_owns": ["sockets", "registries", "health_records", "capability_records", "handoff_paths"],
    "tower_does_not_own": ["external_models", "cloud_inference", "provider_accounts", "provider_runtime"],
    "execution_enabled": False,
    "hardwired_providers": False,
    "kernel_required": False,
    "models_required": False,
    "receives_from": ["floor_24"],
    "incoming_lift": "model_lift",
    "hands_off_to": ["roof"],
    "notice": "Floor 23 manages provider sockets only. External providers remain outside the building."
}

external_handoff_paths = [
    {
        "id": "floor_24_to_air_llm_cloud",
        "source_floor": "floor_24",
        "target_floor": "floor_23",
        "external_target": "roof",
        "provider": "air_llm_cloud",
        "lift": "model_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "description": "Model Routing may hand off to AIR LLM Cloud socket, but no external call is executed."
    },
    {
        "id": "floor_24_to_claude_socket",
        "source_floor": "floor_24",
        "target_floor": "floor_23",
        "external_target": "external_provider",
        "provider": "claude",
        "lift": "model_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "description": "Claude socket is ready for future provider connection."
    },
    {
        "id": "floor_05_to_claude_code_port_to_floor_24_to_floor_23",
        "source_floor": "floor_05",
        "routing_floor": "floor_24",
        "target_floor": "floor_23",
        "provider": "claude",
        "provider_port": "claude_code_socket",
        "first_lift": "service_lift",
        "second_lift": "model_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "description": "Future Claude Code handoff path without direct provider execution."
    },
    {
        "id": "floor_24_to_openai_socket",
        "source_floor": "floor_24",
        "target_floor": "floor_23",
        "provider": "openai",
        "lift": "model_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "description": "OpenAI socket is ready but disconnected."
    },
    {
        "id": "floor_24_to_gemini_socket",
        "source_floor": "floor_24",
        "target_floor": "floor_23",
        "provider": "gemini",
        "lift": "model_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "description": "Gemini socket is ready but disconnected."
    },
    {
        "id": "floor_24_to_deepseek_socket",
        "source_floor": "floor_24",
        "target_floor": "floor_23",
        "provider": "deepseek",
        "lift": "model_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "description": "DeepSeek socket is ready but disconnected."
    }
]

write_json("data/registries/external_provider_capabilities.json", external_provider_capabilities)
write_json("data/registries/external_provider_policy.json", external_provider_policy)
write_json("data/registries/external_handoff_paths.json", external_handoff_paths)

# Ensure provider_sockets exists and contains all Floor 23 sockets.
provider_sockets = read_json("data/registries/provider_sockets.json", [])
existing_socket_ids = {s.get("id") for s in provider_sockets}

required_sockets = [
    {
        "id": "air_llm_cloud_socket",
        "provider": "air_llm_cloud",
        "display_name": "AIR LLM Cloud Socket",
        "location": "roof_external_layer",
        "building_floor": "floor_23",
        "status": "socket_ready_not_connected",
        "hardwired": False,
        "execution_enabled": False
    },
    {
        "id": "claude_socket",
        "provider": "claude",
        "display_name": "Claude Socket",
        "location": "external_provider",
        "building_floor": "floor_23",
        "status": "socket_ready_not_connected",
        "hardwired": False,
        "execution_enabled": False
    },
    {
        "id": "openai_socket",
        "provider": "openai",
        "display_name": "OpenAI Socket",
        "location": "external_provider",
        "building_floor": "floor_23",
        "status": "socket_ready_not_connected",
        "hardwired": False,
        "execution_enabled": False
    },
    {
        "id": "gemini_socket",
        "provider": "gemini",
        "display_name": "Gemini Socket",
        "location": "external_provider",
        "building_floor": "floor_23",
        "status": "socket_ready_not_connected",
        "hardwired": False,
        "execution_enabled": False
    },
    {
        "id": "deepseek_socket",
        "provider": "deepseek",
        "display_name": "DeepSeek Socket",
        "location": "external_provider",
        "building_floor": "floor_23",
        "status": "socket_ready_not_connected",
        "hardwired": False,
        "execution_enabled": False
    },
    {
        "id": "future_model_socket",
        "provider": "future_models",
        "display_name": "Future Model Socket",
        "location": "future_external_or_local_provider",
        "building_floor": "floor_23",
        "status": "expansion_ready",
        "hardwired": False,
        "execution_enabled": False
    }
]

for sock in required_sockets:
    if sock["id"] not in existing_socket_ids:
        provider_sockets.append(sock)

write_json("data/registries/provider_sockets.json", provider_sockets)

# Ensure providers registry has each provider.
providers = read_json("data/registries/providers.json", [])
existing_providers = {p.get("id") for p in providers}
for cap in external_provider_capabilities:
    if cap["provider"] not in existing_providers:
        providers.append({
            "id": cap["provider"],
            "name": cap["display_name"],
            "location": cap["location"],
            "status": cap["status"],
            "hardwired": False
        })
write_json("data/registries/providers.json", providers)

write_json("floors/floor_23_air_llm_operations_department/floor_manifest.json", {
    "floor_id": "floor_23",
    "department": "AIR LLM Operations Department",
    "version": "1.1",
    "role": "external_provider_socket_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "receives_from": ["floor_24"],
    "incoming_lift": "model_lift",
    "roof_link": "roof/air_llm_cloud",
    "notice": "Floor 23 manages sockets, capabilities, health records, and future handoff paths. It does not execute providers."
})

write_json("floors/floor_23_air_llm_operations_department/provider_sockets/manifest.json", {
    "floor_id": "floor_23",
    "socket_count": len(required_sockets),
    "sockets": required_sockets,
    "execution_enabled": False,
    "hardwired": False
})

write_json("floors/floor_23_air_llm_operations_department/provider_capabilities/capabilities.json", external_provider_capabilities)
write_json("floors/floor_23_air_llm_operations_department/external_handoff/handoff_paths.json", external_handoff_paths)

write("config/air_llm_operations.yaml", """
air_llm_operations:
  version: 1.1
  floor_id: floor_23
  role: external_provider_socket_layer
  providers_are_external: true
  execution_enabled: false
  hardwired_providers: false
  models_required: false
  kernel_required: false

lifts:
  incoming_from_model_routing: model_lift
  roof_link: external_air_llm_cloud

principle: Floor 23 owns provider sockets and health records only. External providers remain outside the building.
""")

write("src/tower/air_llm_operations.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "air_llm_operations.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(name, obj):
    path = REG / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")

SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_health (
    provider TEXT PRIMARY KEY,
    display_name TEXT,
    socket_id TEXT,
    location TEXT,
    status TEXT,
    execution_enabled INTEGER,
    hardwired INTEGER,
    last_checked_ts TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS provider_capabilities (
    provider TEXT PRIMARY KEY,
    display_name TEXT,
    socket_id TEXT,
    capabilities_json TEXT,
    status TEXT,
    execution_enabled INTEGER,
    hardwired INTEGER
);

CREATE TABLE IF NOT EXISTS handoff_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    provider TEXT,
    source_floor TEXT,
    target_floor TEXT,
    socket_id TEXT,
    status TEXT,
    details TEXT
);
"""

class AirLLMOperations:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.sync()

    def sync(self):
        caps = load_json("external_provider_capabilities.json", [])
        sockets = load_json("provider_sockets.json", [])

        socket_by_provider = {}
        for s in sockets:
            if s.get("building_floor") == "floor_23":
                socket_by_provider[s.get("provider")] = s

        for cap in caps:
            provider = cap["provider"]
            sock = socket_by_provider.get(provider, {})
            socket_id = cap.get("socket_id") or sock.get("id")
            display = cap.get("display_name", provider)
            location = cap.get("location", sock.get("location", "external_provider"))
            status = cap.get("status", sock.get("status", "not_connected"))

            self.conn.execute(
                "INSERT OR REPLACE INTO provider_health VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    provider,
                    display,
                    socket_id,
                    location,
                    status,
                    int(bool(cap.get("execution_enabled", False))),
                    int(bool(cap.get("hardwired", False))),
                    now(),
                    "Socket registered. External execution disabled."
                )
            )

            self.conn.execute(
                "INSERT OR REPLACE INTO provider_capabilities VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    provider,
                    display,
                    socket_id,
                    json.dumps(cap.get("capabilities", [])),
                    status,
                    int(bool(cap.get("execution_enabled", False))),
                    int(bool(cap.get("hardwired", False)))
                )
            )

        self.conn.commit()

    def health(self):
        rows = self.conn.execute("SELECT * FROM provider_health ORDER BY provider").fetchall()
        return [dict(r) for r in rows]

    def capabilities(self):
        rows = self.conn.execute("SELECT * FROM provider_capabilities ORDER BY provider").fetchall()
        output = []
        for r in rows:
            item = dict(r)
            item["capabilities"] = json.loads(item.pop("capabilities_json"))
            output.append(item)
        return output

    def handoff_paths(self):
        return load_json("external_handoff_paths.json", [])

    def record_handoff(self, provider, source_floor="floor_24", target_floor="floor_23", details=None):
        details = details or {}
        socket = None
        for cap in self.capabilities():
            if cap["provider"] == provider:
                socket = cap.get("socket_id")
                break

        status = "prepared_not_executed"
        self.conn.execute(
            "INSERT INTO handoff_events(ts, provider, source_floor, target_floor, socket_id, status, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now(), provider, source_floor, target_floor, socket, status, json.dumps(details))
        )
        self.conn.commit()

        return {
            "provider": provider,
            "source_floor": source_floor,
            "target_floor": target_floor,
            "socket_id": socket,
            "status": status,
            "execution_enabled": False
        }

    def recent_handoffs(self, limit=20):
        rows = self.conn.execute("SELECT * FROM handoff_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def refresh_provider_health(self):
        self.sync()
        results = []
        for h in self.health():
            status = h["status"]
            if h["provider"] == "future_models":
                status = "expansion_ready"
            elif h["provider"] == "air_llm_cloud":
                status = "socket_ready_not_connected"
            else:
                status = "socket_ready_not_connected"

            self.conn.execute(
                "UPDATE provider_health SET status=?, last_checked_ts=?, notes=? WHERE provider=?",
                (status, now(), "Health simulated. No external call performed.", h["provider"])
            )
            results.append({
                "provider": h["provider"],
                "status": status,
                "external_call_performed": False
            })

        self.conn.commit()
        return results

    def dashboard(self):
        self.sync()
        health = self.health()
        caps = self.capabilities()
        paths = self.handoff_paths()

        return {
            "database": str(DB),
            "floor": "floor_23",
            "department": "AIR LLM Operations Department",
            "version": "1.1",
            "providers_are_external": True,
            "execution_enabled": False,
            "hardwired_providers": False,
            "models_required": False,
            "kernel_required": False,
            "incoming_lift": "model_lift",
            "roof_link": "AIR LLM Cloud external layer",
            "provider_count": len(health),
            "socket_count": len([p for p in health if p.get("socket_id")]),
            "health": health,
            "capabilities": caps,
            "handoff_paths": paths,
            "recent_handoffs": self.recent_handoffs(10)
        }

if __name__ == "__main__":
    dept = AirLLMOperations()
    print(json.dumps(dept.dashboard(), indent=2))
''')

write("scripts/air_llm_operations_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.air_llm_operations
""")

write("scripts/refresh_provider_health.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.air_llm_operations import AirLLMOperations
import json
dept = AirLLMOperations()
print(json.dumps(dept.refresh_provider_health(), indent=2))
PY2
""")

write("scripts/prepare_provider_handoff.py", """
import sys
import json
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.air_llm_operations import AirLLMOperations

provider = sys.argv[1] if len(sys.argv) > 1 else 'claude'
dept = AirLLMOperations()
print(json.dumps(dept.record_handoff(provider, details={'manual_test': True}), indent=2))
""")

for script in [
    "scripts/air_llm_operations_status.sh",
    "scripts/refresh_provider_health.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_air_llm_operations_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.air_llm_operations import AirLLMOperations

dept = AirLLMOperations()
dash = dept.dashboard()

assert dash['floor'] == 'floor_23'
assert dash['providers_are_external'] is True
assert dash['execution_enabled'] is False
assert dash['hardwired_providers'] is False
assert dash['models_required'] is False
assert dash['kernel_required'] is False
assert dash['incoming_lift'] == 'model_lift'
assert dash['provider_count'] >= 6
assert dash['socket_count'] >= 6

handoff = dept.record_handoff('claude', details={'test': 'validation'})
assert handoff['provider'] == 'claude'
assert handoff['status'] == 'prepared_not_executed'
assert handoff['execution_enabled'] is False

print('AIR LLM OPERATIONS V1.1 VALIDATION PASSED')
print('Providers:', dash['provider_count'])
print('Sockets:', dash['socket_count'])
""")

# Update dashboard with Floor 23 panel.
write("src/dashboard/server.py", r'''
import sys
import json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

from tower.registry import Registry
from tower.database import init_db
from tower.lifts import LiftNetwork
from tower.diagnostics import Diagnostics
from tower.model_infrastructure import ModelInfrastructure
from tower.coding_department import CodingDepartment
from tower.model_routing_department import ModelRoutingDepartment
from tower.local_model_operations import LocalModelOperations
from tower.air_llm_operations import AirLLMOperations

HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>QSB Tower V1.1</title>
<style>
body{background:#06111f;color:#e8f2ff;font-family:Arial;margin:0}
header{background:#0d1d33;padding:18px;border-bottom:1px solid #28476b}
h1{color:#ffd45a;margin:0}
.grid{display:grid;grid-template-columns:1.05fr 1fr;gap:14px;padding:14px}
.panel{background:#0b1a2d;border:1px solid #28476b;border-radius:12px;padding:12px;margin-bottom:14px}
.tower{display:flex;flex-direction:column-reverse;gap:3px;max-height:82vh;overflow:auto}
.floor{display:grid;grid-template-columns:55px 1fr 100px;gap:8px;padding:5px;border-radius:6px;font-size:13px}
.occupied{background:#14345a}
.vacant_ready{background:#1f2937;border:1px dashed #8fb7e8}
.special{background:#4b2f00;color:#ffd45a}
.air{background:#18385f;border:1px solid #9ac7ff}
.model{background:#143d5a;border:1px solid #50bfff}
.coding{background:#17365a;border:1px solid #7fb7ff}
.routing{background:#174a5a;border:1px solid #78e5ff}
.localmodel{background:#163f46;border:1px solid #6fffe0}
pre{background:#050c16;padding:10px;border-radius:8px;max-height:225px;overflow:auto}
</style>
</head>
<body>
<header>
<h1>QSB Tower V1.1 - AI Headquarters Infrastructure</h1>
<div>Reserved For Future QSB Kernel 4.5 Installation</div>
</header>

<div class="grid">
<div class="panel">
<h2>53-Floor Tower</h2>
<div id="tower" class="tower"></div>
</div>

<div>
<div class="panel"><h2>Health</h2><pre id="health"></pre></div>
<div class="panel"><h2>Floor 5 Coding Department</h2><pre id="coding"></pre></div>
<div class="panel"><h2>Floor 24 Model Routing Department</h2><pre id="routing"></pre></div>
<div class="panel"><h2>Floor 27 Local Model Operations</h2><pre id="localmodels"></pre></div>
<div class="panel"><h2>Floor 23 AIR LLM Operations</h2><pre id="airllm"></pre></div>
<div class="panel"><h2>Model Infrastructure</h2><pre id="model"></pre></div>
<div class="panel"><h2>Model Request Paths</h2><pre id="paths"></pre></div>
<div class="panel"><h2>Lift Network</h2><pre id="lifts"></pre></div>
<div class="panel"><h2>Providers</h2><pre id="providers"></pre></div>
<div class="panel"><h2>Packets</h2><pre id="packets"></pre></div>
</div>
</div>

<script>
function floorClass(f){
  if(f.id==="floor_23") return "air";
  if(f.id==="floor_24") return "routing";
  if(f.id==="floor_27") return "localmodel";
  if(f.id==="floor_05") return "coding";
  return f.status;
}

async function load(){
  let s = await (await fetch("/api/status")).json();
  let m = await (await fetch("/api/model_infrastructure")).json();
  let c = await (await fetch("/api/coding_department")).json();
  let r = await (await fetch("/api/model_routing_department")).json();
  let lm = await (await fetch("/api/local_model_operations")).json();
  let air = await (await fetch("/api/air_llm_operations")).json();

  let t = document.getElementById("tower");
  t.innerHTML = "";

  function row(a,b,c,cls){
    let d=document.createElement("div");
    d.className="floor "+cls;
    d.innerHTML="<b>"+a+"</b><span>"+b+"</span><span>"+c+"</span>";
    t.appendChild(d);
  }

  row("ROOF","AIR LLM Cloud - external providers","external","special");
  row("PH","Reserved For Future QSB Kernel 4.5","socket ready","special");

  s.floors.forEach(f => row(f.number, f.department, f.zone, floorClass(f)));

  row("G","Reception and Command Lobby","online","occupied");
  row("B1","Core Services","online","special");
  row("B2","Vault and Archives","online","special");
  row("B3","Disaster Recovery","online","special");

  health.textContent = JSON.stringify(s.counts,null,2);

  coding.textContent = JSON.stringify({
    floor:c.floor,
    department:c.department,
    routes_through:c.routes_through,
    requests:c.requests,
    patch_queue:c.patch_queue,
    review_queue:c.review_queue,
    test_queue:c.test_queue,
    workspaces:c.workspaces.length,
    worker_slots:c.worker_slots.length
  },null,2);

  routing.textContent = JSON.stringify({
    floor:r.floor,
    department:r.department,
    execution_enabled:r.execution_enabled,
    direct_provider_access:r.direct_provider_access,
    incoming_lift:r.incoming_lift,
    outgoing_lift:r.outgoing_lift,
    route_decisions:r.route_decisions,
    by_target:r.by_target,
    by_socket:r.by_socket
  },null,2);

  localmodels.textContent = JSON.stringify({
    floor:lm.floor,
    department:lm.department,
    models_required:lm.models_required,
    execution_enabled:lm.execution_enabled,
    hardwired_models:lm.hardwired_models,
    incoming_lift:lm.incoming_lift,
    detected_models:lm.detected_models,
    role_summary:lm.role_summary,
    recommendations:lm.recommendations
  },null,2);

  airllm.textContent = JSON.stringify({
    floor:air.floor,
    department:air.department,
    providers_are_external:air.providers_are_external,
    execution_enabled:air.execution_enabled,
    hardwired_providers:air.hardwired_providers,
    incoming_lift:air.incoming_lift,
    roof_link:air.roof_link,
    provider_count:air.provider_count,
    socket_count:air.socket_count,
    health:air.health,
    recent_handoffs:air.recent_handoffs
  },null,2);

  model.textContent = JSON.stringify({
    principle:m.principle,
    building_runs_without_models:m.building_runs_without_models,
    hardwired_providers:m.hardwired_providers,
    execution_enabled:m.execution_enabled,
    sockets:m.sockets.length,
    worker_slots:m.worker_slots.length,
    discovered_local_models:m.discovered_local_models.length
  },null,2);

  paths.textContent = JSON.stringify(m.request_paths,null,2);
  lifts.textContent = JSON.stringify(s.lifts,null,2);
  providers.textContent = JSON.stringify(s.providers,null,2);
  packets.textContent = JSON.stringify(s.packets,null,2);
}

load();
setInterval(load,2500);
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

    def do_GET(self):
        init_db()
        reg = Registry()
        lifts = LiftNetwork()

        if self.path.startswith("/api/diagnostics"):
            return self.send_json(Diagnostics().run())

        if self.path.startswith("/api/model_infrastructure"):
            return self.send_json(ModelInfrastructure().dashboard())

        if self.path.startswith("/api/coding_department"):
            return self.send_json(CodingDepartment().dashboard())

        if self.path.startswith("/api/model_routing_department"):
            return self.send_json(ModelRoutingDepartment().dashboard())

        if self.path.startswith("/api/local_model_operations"):
            return self.send_json(LocalModelOperations().dashboard())

        if self.path.startswith("/api/air_llm_operations"):
            return self.send_json(AirLLMOperations().dashboard())

        if self.path.startswith("/api/status"):
            floors = reg.floors()
            return self.send_json({
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
            })

        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    print("Dashboard: http://127.0.0.1:8765")
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
''')

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
AIR LLM Operations Department V1.1

Floor 23 is now an external provider socket layer.

It includes:
- AIR LLM Cloud socket
- Claude socket
- Claude Code handoff path
- OpenAI socket
- Gemini socket
- DeepSeek socket
- Future provider socket
- Provider health records
- Provider capability registry
- External handoff records
- Dashboard panel

Floor 23 does not execute provider calls.
External providers remain outside the building.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/refresh_provider_health.sh
./scripts/air_llm_operations_status.sh
python3 scripts/prepare_provider_handoff.py claude
python3 tests/test_air_llm_operations_v11.py
"""

if "AIR LLM Operations Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Floor 23 AIR LLM Operations Department V1.1 installed.")
print("Run:")
print("./scripts/refresh_provider_health.sh")
print("./scripts/air_llm_operations_status.sh")
