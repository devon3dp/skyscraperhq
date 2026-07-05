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

print("Installing Floor 22 Integration Services Department V1.1...")

for folder in [
    "floors/floor_22_integration_services_department/service_map",
    "floors/floor_22_integration_services_department/integration_paths",
    "floors/floor_22_integration_services_department/dependency_graph",
    "floors/floor_22_integration_services_department/readiness_checks",
    "floors/floor_22_integration_services_department/handoff_records",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower",
    "src/dashboard"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

integration_policy = {
    "version": "1.1",
    "floor_id": "floor_22",
    "department": "Integration Services Department",
    "role": "cross_floor_service_integration_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "principle": "Floor 22 connects building services structurally. It does not execute providers, adapters, tools, or models.",
    "receives_from": ["floor_05", "floor_21", "floor_24", "floor_27", "floor_23"],
    "hands_off_to": ["floor_21", "floor_24", "floor_27", "floor_23", "floor_35"],
    "notice": "Integration records are coordination records only. No external execution is enabled."
}

integration_service_map = [
    {
        "id": "coding_to_adapter_to_routing",
        "name": "Coding to Adapter to Routing",
        "source_floor": "floor_05",
        "via_floor": "floor_21",
        "target_floor": "floor_24",
        "service_path": ["floor_05", "service_lift", "floor_21", "service_lift", "floor_24"],
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "integration_ready"
    },
    {
        "id": "routing_to_local_models",
        "name": "Routing to Local Model Operations",
        "source_floor": "floor_24",
        "via_floor": None,
        "target_floor": "floor_27",
        "service_path": ["floor_24", "model_lift", "floor_27"],
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "integration_ready"
    },
    {
        "id": "routing_to_external_provider_sockets",
        "name": "Routing to External Provider Sockets",
        "source_floor": "floor_24",
        "via_floor": None,
        "target_floor": "floor_23",
        "service_path": ["floor_24", "model_lift", "floor_23"],
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "integration_ready"
    },
    {
        "id": "external_sockets_to_roof",
        "name": "External Provider Socket to Roof Layer",
        "source_floor": "floor_23",
        "via_floor": None,
        "target_floor": "roof",
        "service_path": ["floor_23", "model_lift", "roof"],
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "socket_ready_not_connected"
    },
    {
        "id": "adapter_to_infrastructure_services",
        "name": "Adapter to Infrastructure Services",
        "source_floor": "floor_21",
        "via_floor": None,
        "target_floor": "floor_35",
        "service_path": ["floor_21", "service_lift", "floor_35"],
        "sealed_packets": True,
        "execution_enabled": False,
        "status": "disabled_until_enabled_later"
    }
]

integration_dependency_graph = [
    {
        "component": "Floor 5 Coding Department",
        "floor_id": "floor_05",
        "depends_on": ["service_lift", "Floor 24 Model Routing Department"],
        "optional_depends_on": ["Floor 21 Adapter Systems Department"],
        "execution_enabled": False
    },
    {
        "component": "Floor 21 Adapter Systems Department",
        "floor_id": "floor_21",
        "depends_on": ["service_lift", "adapter_sockets registry"],
        "optional_depends_on": ["Floor 23 AIR LLM Operations", "Floor 27 Local Model Operations"],
        "execution_enabled": False
    },
    {
        "component": "Floor 22 Integration Services Department",
        "floor_id": "floor_22",
        "depends_on": ["integration_service_map registry", "dependency_graph registry"],
        "optional_depends_on": ["all model-service floors"],
        "execution_enabled": False
    },
    {
        "component": "Floor 24 Model Routing Department",
        "floor_id": "floor_24",
        "depends_on": ["service_lift", "model_lift", "model_routing_policies registry"],
        "optional_depends_on": ["Floor 27 Local Model Operations", "Floor 23 AIR LLM Operations"],
        "execution_enabled": False
    },
    {
        "component": "Floor 27 Local Model Operations",
        "floor_id": "floor_27",
        "depends_on": ["model_lift", "local_model_roles registry"],
        "optional_depends_on": ["Ollama local installation"],
        "execution_enabled": False
    },
    {
        "component": "Floor 23 AIR LLM Operations",
        "floor_id": "floor_23",
        "depends_on": ["model_lift", "provider_sockets registry"],
        "optional_depends_on": ["external provider accounts", "roof AIR LLM Cloud"],
        "execution_enabled": False
    }
]

integration_readiness_checks = [
    {"id": "check_floor_05", "description": "Coding Department module and registry present.", "required_file": "src/tower/coding_department.py"},
    {"id": "check_floor_21", "description": "Adapter Systems module and registry present.", "required_file": "src/tower/adapter_systems.py"},
    {"id": "check_floor_23", "description": "AIR LLM Operations module and registry present.", "required_file": "src/tower/air_llm_operations.py"},
    {"id": "check_floor_24", "description": "Model Routing module and registry present.", "required_file": "src/tower/model_routing_department.py"},
    {"id": "check_floor_27", "description": "Local Model Operations module and registry present.", "required_file": "src/tower/local_model_operations.py"},
    {"id": "check_lifts", "description": "Lift Network module present.", "required_file": "src/tower/lifts.py"},
    {"id": "check_model_infra", "description": "Model Infrastructure module present.", "required_file": "src/tower/model_infrastructure.py"}
]

write_json("data/registries/integration_policy.json", integration_policy)
write_json("data/registries/integration_service_map.json", integration_service_map)
write_json("data/registries/integration_dependency_graph.json", integration_dependency_graph)
write_json("data/registries/integration_readiness_checks.json", integration_readiness_checks)

write_json("floors/floor_22_integration_services_department/floor_manifest.json", {
    "floor_id": "floor_22",
    "department": "Integration Services Department",
    "version": "1.1",
    "role": "cross_floor_service_integration_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "service_paths": len(integration_service_map),
    "dependency_records": len(integration_dependency_graph),
    "notice": "Floor 22 integrates service paths and dependency records only. It does not execute providers, tools, adapters, or models."
})

write_json("floors/floor_22_integration_services_department/service_map/service_map.json", integration_service_map)
write_json("floors/floor_22_integration_services_department/dependency_graph/dependency_graph.json", integration_dependency_graph)
write_json("floors/floor_22_integration_services_department/readiness_checks/readiness_checks.json", integration_readiness_checks)

write("config/integration_services_department.yaml", """
integration_services_department:
  version: 1.1
  floor_id: floor_22
  role: cross_floor_service_integration_layer
  execution_enabled: false
  hardwired_providers: false
  models_required: false
  kernel_required: false
  providers_are_external: true

principle: Floor 22 coordinates service paths and dependency records. It does not execute providers, tools, adapters, CLI commands, file operations, or model calls.

primary_paths:
  coding_to_adapter_to_routing: floor_05 -> floor_21 -> floor_24
  routing_to_local_models: floor_24 -> floor_27
  routing_to_external_provider_sockets: floor_24 -> floor_23
  external_sockets_to_roof: floor_23 -> roof
""")

write("src/tower/integration_services.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "integration_services.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS integration_services (
    id TEXT PRIMARY KEY,
    name TEXT,
    source_floor TEXT,
    via_floor TEXT,
    target_floor TEXT,
    service_path_json TEXT,
    sealed_packets INTEGER,
    execution_enabled INTEGER,
    status TEXT,
    last_checked_ts TEXT
);

CREATE TABLE IF NOT EXISTS dependency_graph (
    component TEXT PRIMARY KEY,
    floor_id TEXT,
    depends_on_json TEXT,
    optional_depends_on_json TEXT,
    execution_enabled INTEGER,
    status TEXT
);

CREATE TABLE IF NOT EXISTS integration_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    event_type TEXT,
    service_id TEXT,
    status TEXT,
    details TEXT
);
"""

class IntegrationServices:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.sync()

    def policy(self):
        return load_json("integration_policy.json", {})

    def service_map_registry(self):
        return load_json("integration_service_map.json", [])

    def dependency_registry(self):
        return load_json("integration_dependency_graph.json", [])

    def readiness_checks(self):
        return load_json("integration_readiness_checks.json", [])

    def sync(self):
        for svc in self.service_map_registry():
            self.conn.execute(
                """
                INSERT OR REPLACE INTO integration_services
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    svc["id"],
                    svc["name"],
                    svc["source_floor"],
                    svc.get("via_floor"),
                    svc["target_floor"],
                    json.dumps(svc.get("service_path", [])),
                    int(bool(svc.get("sealed_packets", True))),
                    int(bool(svc.get("execution_enabled", False))),
                    svc.get("status", "unknown"),
                    now()
                )
            )

        for dep in self.dependency_registry():
            self.conn.execute(
                """
                INSERT OR REPLACE INTO dependency_graph
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    dep["component"],
                    dep["floor_id"],
                    json.dumps(dep.get("depends_on", [])),
                    json.dumps(dep.get("optional_depends_on", [])),
                    int(bool(dep.get("execution_enabled", False))),
                    "registered"
                )
            )

        self.conn.commit()

    def service_map(self):
        rows = self.conn.execute("SELECT * FROM integration_services ORDER BY id").fetchall()
        output = []
        for r in rows:
            item = dict(r)
            item["service_path"] = json.loads(item.pop("service_path_json"))
            item["sealed_packets"] = bool(item["sealed_packets"])
            item["execution_enabled"] = bool(item["execution_enabled"])
            output.append(item)
        return output

    def dependency_graph(self):
        rows = self.conn.execute("SELECT * FROM dependency_graph ORDER BY floor_id").fetchall()
        output = []
        for r in rows:
            item = dict(r)
            item["depends_on"] = json.loads(item.pop("depends_on_json"))
            item["optional_depends_on"] = json.loads(item.pop("optional_depends_on_json"))
            item["execution_enabled"] = bool(item["execution_enabled"])
            output.append(item)
        return output

    def run_readiness_checks(self):
        results = []
        for check in self.readiness_checks():
            required = ROOT / check["required_file"]
            ok = required.exists()
            results.append({
                "id": check["id"],
                "description": check["description"],
                "required_file": check["required_file"],
                "ok": ok,
                "status": "pass" if ok else "missing"
            })

        self.conn.execute(
            "INSERT INTO integration_events(ts, event_type, service_id, status, details) VALUES (?, ?, ?, ?, ?)",
            (now(), "readiness_checks", "all", "complete", json.dumps(results))
        )
        self.conn.commit()
        return results

    def prepare_integration_handoff(self, service_id, details=None):
        details = details or {}
        service = None
        for svc in self.service_map():
            if svc["id"] == service_id:
                service = svc
                break

        if service is None:
            status = "unknown_service"
            event_details = {"service_id": service_id, "error": "service not found", **details}
        else:
            status = "prepared_not_executed"
            event_details = {
                "service": service,
                "execution_enabled": False,
                "routing_only": True,
                **details
            }

        self.conn.execute(
            "INSERT INTO integration_events(ts, event_type, service_id, status, details) VALUES (?, ?, ?, ?, ?)",
            (now(), "prepare_integration_handoff", service_id, status, json.dumps(event_details))
        )
        self.conn.commit()

        return {
            "service_id": service_id,
            "status": status,
            "execution_enabled": False,
            "details": event_details
        }

    def refresh_health(self):
        checks = self.run_readiness_checks()
        missing = [c for c in checks if not c["ok"]]
        status = "healthy" if not missing else "degraded"

        self.conn.execute(
            "INSERT INTO integration_events(ts, event_type, service_id, status, details) VALUES (?, ?, ?, ?, ?)",
            (now(), "integration_health_refresh", "floor_22", status, json.dumps({"missing": missing}))
        )
        self.conn.commit()

        return {
            "status": status,
            "checks": checks,
            "missing_count": len(missing),
            "execution_enabled": False
        }

    def recent_events(self, limit=20):
        rows = self.conn.execute("SELECT * FROM integration_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        self.sync()
        services = self.service_map()
        deps = self.dependency_graph()
        checks = self.run_readiness_checks()
        missing = [c for c in checks if not c["ok"]]

        return {
            "database": str(DB),
            "floor": "floor_22",
            "department": "Integration Services Department",
            "version": "1.1",
            "role": "cross_floor_service_integration_layer",
            "execution_enabled": False,
            "hardwired_providers": False,
            "models_required": False,
            "kernel_required": False,
            "providers_are_external": True,
            "integration_health": "healthy" if not missing else "degraded",
            "service_paths": len(services),
            "dependency_records": len(deps),
            "readiness_checks": checks,
            "service_map": services,
            "dependency_graph": deps,
            "recent_events": self.recent_events(10),
            "policy": self.policy()
        }

if __name__ == "__main__":
    print(json.dumps(IntegrationServices().dashboard(), indent=2))
''')

write("scripts/integration_services_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.integration_services
""")

write("scripts/refresh_integration_health.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.integration_services import IntegrationServices
import json
dept = IntegrationServices()
print(json.dumps(dept.refresh_health(), indent=2))
PY2
""")

write("scripts/prepare_integration_handoff.py", """
import sys
import json
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.integration_services import IntegrationServices

service_id = sys.argv[1] if len(sys.argv) > 1 else 'coding_to_adapter_to_routing'
dept = IntegrationServices()
print(json.dumps(dept.prepare_integration_handoff(service_id, details={'manual_test': True}), indent=2))
""")

for script in [
    "scripts/integration_services_status.sh",
    "scripts/refresh_integration_health.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_integration_services_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.integration_services import IntegrationServices

dept = IntegrationServices()
dash = dept.dashboard()

assert dash['floor'] == 'floor_22'
assert dash['department'] == 'Integration Services Department'
assert dash['execution_enabled'] is False
assert dash['hardwired_providers'] is False
assert dash['models_required'] is False
assert dash['kernel_required'] is False
assert dash['providers_are_external'] is True
assert dash['service_paths'] >= 5
assert dash['dependency_records'] >= 6

health = dept.refresh_health()
assert health['execution_enabled'] is False
assert health['missing_count'] == 0, health

handoff = dept.prepare_integration_handoff('coding_to_adapter_to_routing', details={'test': 'validation'})
assert handoff['service_id'] == 'coding_to_adapter_to_routing'
assert handoff['status'] == 'prepared_not_executed'
assert handoff['execution_enabled'] is False

print('INTEGRATION SERVICES V1.1 VALIDATION PASSED')
print('Service paths:', dash['service_paths'])
print('Dependency records:', dash['dependency_records'])
print('Health:', health['status'])
""")

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
from tower.adapter_systems import AdapterSystems
from tower.integration_services import IntegrationServices
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
.adapter{background:#1c315f;border:1px solid #bd9cff}
.integration{background:#24315f;border:1px solid #ffc17a}
.air{background:#18385f;border:1px solid #9ac7ff}
.model{background:#143d5a;border:1px solid #50bfff}
.coding{background:#17365a;border:1px solid #7fb7ff}
.routing{background:#174a5a;border:1px solid #78e5ff}
.localmodel{background:#163f46;border:1px solid #6fffe0}
pre{background:#050c16;padding:10px;border-radius:8px;max-height:215px;overflow:auto}
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
<div class="panel"><h2>Floor 21 Adapter Systems</h2><pre id="adapters"></pre></div>
<div class="panel"><h2>Floor 22 Integration Services</h2><pre id="integration"></pre></div>
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
  if(f.id==="floor_21") return "adapter";
  if(f.id==="floor_22") return "integration";
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
  let a = await (await fetch("/api/adapter_systems")).json();
  let i = await (await fetch("/api/integration_services")).json();
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

  document.getElementById("health").textContent = JSON.stringify(s.counts,null,2);

  document.getElementById("coding").textContent = JSON.stringify({
    floor:c.floor, department:c.department, routes_through:c.routes_through,
    requests:c.requests, patch_queue:c.patch_queue, review_queue:c.review_queue,
    test_queue:c.test_queue, workspaces:c.workspaces.length, worker_slots:c.worker_slots.length
  },null,2);

  document.getElementById("adapters").textContent = JSON.stringify({
    floor:a.floor, department:a.department, execution_enabled:a.execution_enabled,
    hardwired_adapters:a.hardwired_adapters, providers_are_external:a.providers_are_external,
    adapter_count:a.adapter_count, capability_records:a.capability_records,
    recent_handoffs:a.recent_handoffs
  },null,2);

  document.getElementById("integration").textContent = JSON.stringify({
    floor:i.floor, department:i.department, integration_health:i.integration_health,
    execution_enabled:i.execution_enabled, hardwired_providers:i.hardwired_providers,
    service_paths:i.service_paths, dependency_records:i.dependency_records,
    readiness_checks:i.readiness_checks, recent_events:i.recent_events
  },null,2);

  document.getElementById("routing").textContent = JSON.stringify({
    floor:r.floor, department:r.department, execution_enabled:r.execution_enabled,
    direct_provider_access:r.direct_provider_access, incoming_lift:r.incoming_lift,
    outgoing_lift:r.outgoing_lift, route_decisions:r.route_decisions,
    by_target:r.by_target, by_socket:r.by_socket
  },null,2);

  document.getElementById("localmodels").textContent = JSON.stringify({
    floor:lm.floor, department:lm.department, models_required:lm.models_required,
    execution_enabled:lm.execution_enabled, hardwired_models:lm.hardwired_models,
    incoming_lift:lm.incoming_lift, detected_models:lm.detected_models,
    role_summary:lm.role_summary, recommendations:lm.recommendations
  },null,2);

  document.getElementById("airllm").textContent = JSON.stringify({
    floor:air.floor, department:air.department, providers_are_external:air.providers_are_external,
    execution_enabled:air.execution_enabled, hardwired_providers:air.hardwired_providers,
    incoming_lift:air.incoming_lift, roof_link:air.roof_link,
    provider_count:air.provider_count, socket_count:air.socket_count,
    recent_handoffs:air.recent_handoffs
  },null,2);

  document.getElementById("model").textContent = JSON.stringify({
    principle:m.principle, building_runs_without_models:m.building_runs_without_models,
    hardwired_providers:m.hardwired_providers, execution_enabled:m.execution_enabled,
    sockets:m.sockets.length, worker_slots:m.worker_slots.length,
    discovered_local_models:m.discovered_local_models.length
  },null,2);

  document.getElementById("paths").textContent = JSON.stringify(m.request_paths,null,2);
  document.getElementById("lifts").textContent = JSON.stringify(s.lifts,null,2);
  document.getElementById("providers").textContent = JSON.stringify(s.providers,null,2);
  document.getElementById("packets").textContent = JSON.stringify(s.packets,null,2);
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
        if self.path.startswith("/api/adapter_systems"):
            return self.send_json(AdapterSystems().dashboard())
        if self.path.startswith("/api/integration_services"):
            return self.send_json(IntegrationServices().dashboard())
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
Integration Services Department V1.1

Floor 22 is now the cross-floor service integration layer.

It includes:
- Integration registry
- Cross-floor service map
- Floor 5 -> Floor 21 -> Floor 24 path records
- Floor 24 -> Floor 27 / Floor 23 route records
- Provider integration readiness records
- Service dependency graph
- Integration health dashboard panel

Floor 22 does not execute providers, tools, adapters, CLI commands, file operations, or model calls.
It only coordinates service paths and readiness records.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/refresh_integration_health.sh
./scripts/integration_services_status.sh
python3 scripts/prepare_integration_handoff.py coding_to_adapter_to_routing
python3 tests/test_integration_services_v11.py
"""

if "Integration Services Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Floor 22 Integration Services Department V1.1 installed.")
print("Run:")
print("./scripts/refresh_integration_health.sh")
print("./scripts/integration_services_status.sh")
