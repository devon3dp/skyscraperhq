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

print("Installing Floor 24 Model Routing Department V1.1...")

for folder in [
    "floors/floor_24_model_routing_department/routing_exchange",
    "floors/floor_24_model_routing_department/intake_queue",
    "floors/floor_24_model_routing_department/decision_records",
    "floors/floor_24_model_routing_department/fallback_plans",
    "floors/floor_24_model_routing_department/model_lift_handoff",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower",
    "src/dashboard"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

routing_policies = [
    {
        "id": "coding_policy",
        "request_type": "coding",
        "origin_floor": "floor_05",
        "routing_floor": "floor_24",
        "preferred_target": "floor_27",
        "fallback_target": "floor_23",
        "emergency_target": "roof",
        "preferred_lift": "model_lift",
        "execution_enabled": False,
        "direct_provider_access": False,
        "selection_rule": "Prefer local coding-capable models if detected. Otherwise route to external provider socket layer."
    },
    {
        "id": "claude_code_handoff_policy",
        "request_type": "claude_code_handoff",
        "origin_floor": "floor_05",
        "routing_floor": "floor_24",
        "preferred_target": "floor_23",
        "fallback_target": "roof",
        "emergency_target": "floor_27",
        "preferred_lift": "model_lift",
        "execution_enabled": False,
        "direct_provider_access": False,
        "selection_rule": "Claude Code remains external. Floor 24 prepares socket handoff only."
    },
    {
        "id": "vision_policy",
        "request_type": "vision",
        "origin_floor": "floor_13",
        "routing_floor": "floor_24",
        "preferred_target": "floor_27",
        "fallback_target": "floor_23",
        "emergency_target": "roof",
        "preferred_lift": "model_lift",
        "execution_enabled": False,
        "direct_provider_access": False,
        "selection_rule": "Prefer local vision model if detected. Otherwise use provider socket layer."
    },
    {
        "id": "general_policy",
        "request_type": "general",
        "origin_floor": "ground",
        "routing_floor": "floor_24",
        "preferred_target": "floor_27",
        "fallback_target": "floor_23",
        "emergency_target": "roof",
        "preferred_lift": "model_lift",
        "execution_enabled": False,
        "direct_provider_access": False,
        "selection_rule": "Prefer local general model if detected. Otherwise use provider socket layer."
    }
]

routing_worker_slots = [
    {
        "id": "routing_intake_worker",
        "name": "Routing Intake Worker",
        "floor_id": "floor_24",
        "role": "sealed_packet_intake",
        "status": "simulation_ready",
        "model_bound": False
    },
    {
        "id": "provider_selection_worker",
        "name": "Provider Selection Worker",
        "floor_id": "floor_24",
        "role": "provider_selection_simulation",
        "status": "simulation_ready",
        "model_bound": False
    },
    {
        "id": "fallback_planning_worker",
        "name": "Fallback Planning Worker",
        "floor_id": "floor_24",
        "role": "fallback_route_planning",
        "status": "simulation_ready",
        "model_bound": False
    },
    {
        "id": "model_lift_handoff_worker",
        "name": "Model Lift Handoff Worker",
        "floor_id": "floor_24",
        "role": "model_lift_handoff",
        "status": "simulation_ready",
        "model_bound": False
    },
    {
        "id": "route_audit_worker",
        "name": "Route Audit Worker",
        "floor_id": "floor_24",
        "role": "route_decision_audit",
        "status": "simulation_ready",
        "model_bound": False
    }
]

write_json("data/registries/model_routing_policies.json", routing_policies)
write_json("data/registries/model_routing_worker_slots.json", routing_worker_slots)

write_json("floors/floor_24_model_routing_department/floor_manifest.json", {
    "floor_id": "floor_24",
    "department": "Model Routing Department",
    "version": "1.1",
    "role": "model_routing_exchange",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "direct_provider_access": False,
    "receives_from": ["floor_05", "ground", "floor_13"],
    "hands_off_to": ["floor_27", "floor_23", "roof"],
    "incoming_lift": "service_lift",
    "outgoing_lift": "model_lift",
    "notice": "Floor 24 decides routing paths only. It does not execute model/provider calls."
})

write_json("floors/floor_24_model_routing_department/routing_exchange/manifest.json", {
    "floor_id": "floor_24",
    "department": "Model Routing Department",
    "routing_policy": "registry_driven",
    "policies": "data/registries/model_routing_policies.json",
    "worker_slots": "data/registries/model_routing_worker_slots.json",
    "sealed_packets_required": True,
    "execution_enabled": False,
    "provider_execution": "disabled",
    "notice": "This exchange prepares route decisions and model-lift handoffs only."
})

write("config/model_routing_department.yaml", """
model_routing_department:
  version: 1.1
  floor_id: floor_24
  role: model_routing_exchange
  direct_provider_access: false
  execution_enabled: false
  models_required: false
  kernel_required: false

lifts:
  incoming_from_departments: service_lift
  outgoing_to_model_services: model_lift

targets:
  local_model_operations: floor_27
  external_provider_sockets: floor_23
  air_llm_cloud_roof: roof

principle: Floor 24 routes sealed packets. It does not execute providers.
""")

write("src/tower/model_routing_department.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "model_routing_department.sqlite"
CODING_DB = ROOT / "data" / "db" / "coding_department.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS route_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    source_system TEXT,
    source_request_id INTEGER,
    request_type TEXT,
    origin_floor TEXT,
    routing_floor TEXT,
    selected_target TEXT,
    selected_lift TEXT,
    selected_socket TEXT,
    selected_model TEXT,
    fallback_target TEXT,
    emergency_target TEXT,
    execution_enabled INTEGER,
    status TEXT,
    lift_receipt TEXT,
    notes TEXT,
    UNIQUE(source_system, source_request_id)
);

CREATE TABLE IF NOT EXISTS routing_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    event_type TEXT,
    details TEXT
);
"""

class ModelRoutingDepartment:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policies(self):
        return load_json("model_routing_policies.json", [])

    def worker_slots(self):
        return load_json("model_routing_worker_slots.json", [])

    def discovered_local_models(self):
        return load_json("discovered_ollama_models.json", [])

    def sockets(self):
        return load_json("provider_sockets.json", [])

    def policy_for(self, request_type):
        policies = self.policies()
        for p in policies:
            if p["request_type"] == request_type:
                return p
        for p in policies:
            if p["request_type"] == "general":
                return p
        return {
            "request_type": request_type,
            "origin_floor": "ground",
            "routing_floor": "floor_24",
            "preferred_target": "floor_27",
            "fallback_target": "floor_23",
            "emergency_target": "roof",
            "preferred_lift": "model_lift",
            "execution_enabled": False,
            "direct_provider_access": False,
            "selection_rule": "Default safe routing policy."
        }

    def choose_socket_and_model(self, request_type):
        models = self.discovered_local_models()
        names = [m.get("name", "") for m in models]

        coding_markers = ["coder", "codellama", "deepseek"]
        vision_markers = ["llava", "vision"]
        general_markers = ["qwen", "llama", "mistral", "neural"]

        if request_type in ["coding", "code_generation", "bug_fix", "refactor", "code_review", "test_generation"]:
            for name in names:
                if any(marker in name.lower() for marker in coding_markers):
                    return "floor_27", "ollama_local_socket", name

        if request_type == "vision":
            for name in names:
                if any(marker in name.lower() for marker in vision_markers):
                    return "floor_27", "ollama_local_socket", name

        if request_type == "claude_code_handoff":
            return "floor_23", "claude_socket", None

        for name in names:
            if any(marker in name.lower() for marker in general_markers):
                return "floor_27", "ollama_local_socket", name

        return "floor_23", "air_llm_cloud_socket", None

    def create_route_decision(self, source_system, source_request_id, request_type, origin_floor, title="", description=""):
        existing = self.conn.execute(
            "SELECT * FROM route_decisions WHERE source_system=? AND source_request_id=?",
            (source_system, source_request_id)
        ).fetchone()
        if existing:
            return dict(existing)

        policy = self.policy_for(request_type)
        selected_target, selected_socket, selected_model = self.choose_socket_and_model(request_type)

        fallback_target = policy.get("fallback_target", "floor_23")
        emergency_target = policy.get("emergency_target", "roof")
        selected_lift = policy.get("preferred_lift", "model_lift")

        receipt = "not_sent"
        try:
            from tower.lifts import LiftNetwork
            lift_result = LiftNetwork().send("floor_24", selected_target, selected_lift, int(5))
            receipt = json.dumps(lift_result)
        except Exception as e:
            receipt = json.dumps({"error": str(e)})

        notes = {
            "title": title,
            "description": description,
            "selection_rule": policy.get("selection_rule", ""),
            "provider_execution": "disabled",
            "routing_only": True
        }

        self.conn.execute(
            """
            INSERT INTO route_decisions
            (ts, source_system, source_request_id, request_type, origin_floor, routing_floor,
             selected_target, selected_lift, selected_socket, selected_model, fallback_target,
             emergency_target, execution_enabled, status, lift_receipt, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now(), source_system, int(source_request_id), request_type, origin_floor, "floor_24",
                selected_target, selected_lift, selected_socket, selected_model, fallback_target,
                emergency_target, 0, "routed_to_socket_layer", receipt, json.dumps(notes)
            )
        )
        self.conn.commit()

        return dict(self.conn.execute(
            "SELECT * FROM route_decisions WHERE source_system=? AND source_request_id=?",
            (source_system, source_request_id)
        ).fetchone())

    def coding_requests(self):
        if not CODING_DB.exists():
            return []
        c = sqlite3.connect(CODING_DB)
        c.row_factory = sqlite3.Row
        try:
            rows = c.execute("SELECT * FROM coding_requests ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            c.close()

    def process_coding_requests(self, limit=20):
        processed = []
        requests = self.coding_requests()
        for req in requests[:limit]:
            decision = self.create_route_decision(
                source_system="coding_department",
                source_request_id=req["id"],
                request_type=req.get("request_type", "coding"),
                origin_floor=req.get("origin_floor", "floor_05"),
                title=req.get("title", ""),
                description=req.get("description", "")
            )
            processed.append(decision)

        self.conn.execute(
            "INSERT INTO routing_events(ts, event_type, details) VALUES (?, ?, ?)",
            (now(), "process_coding_requests", json.dumps({"processed": len(processed)}))
        )
        self.conn.commit()
        return processed

    def recent_decisions(self, limit=20):
        rows = self.conn.execute("SELECT * FROM route_decisions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def recent_events(self, limit=20):
        rows = self.conn.execute("SELECT * FROM routing_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        total = self.conn.execute("SELECT COUNT(*) AS c FROM route_decisions").fetchone()["c"]
        by_target_rows = self.conn.execute(
            "SELECT selected_target, COUNT(*) AS c FROM route_decisions GROUP BY selected_target ORDER BY c DESC"
        ).fetchall()
        by_socket_rows = self.conn.execute(
            "SELECT selected_socket, COUNT(*) AS c FROM route_decisions GROUP BY selected_socket ORDER BY c DESC"
        ).fetchall()

        return {
            "database": str(DB),
            "floor": "floor_24",
            "department": "Model Routing Department",
            "version": "1.1",
            "execution_enabled": False,
            "direct_provider_access": False,
            "incoming_lift": "service_lift",
            "outgoing_lift": "model_lift",
            "route_decisions": total,
            "policies": self.policies(),
            "worker_slots": self.worker_slots(),
            "by_target": [dict(r) for r in by_target_rows],
            "by_socket": [dict(r) for r in by_socket_rows],
            "recent_decisions": self.recent_decisions(10),
            "recent_events": self.recent_events(10)
        }

if __name__ == "__main__":
    dept = ModelRoutingDepartment()
    print(json.dumps(dept.dashboard(), indent=2))
''')

write("scripts/model_routing_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.model_routing_department
""")

write("scripts/process_model_routes.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.model_routing_department import ModelRoutingDepartment
import json
dept = ModelRoutingDepartment()
processed = dept.process_coding_requests()
print(json.dumps({
    "processed": len(processed),
    "decisions": processed
}, indent=2))
PY2
""")

for script in ["scripts/model_routing_status.sh", "scripts/process_model_routes.sh"]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_model_routing_department_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.model_routing_department import ModelRoutingDepartment

dept = ModelRoutingDepartment()
processed = dept.process_coding_requests()
dash = dept.dashboard()

assert dash['floor'] == 'floor_24'
assert dash['execution_enabled'] is False
assert dash['direct_provider_access'] is False
assert dash['incoming_lift'] == 'service_lift'
assert dash['outgoing_lift'] == 'model_lift'
assert len(dash['policies']) >= 4
assert len(dash['worker_slots']) >= 5

decision = dept.create_route_decision(
    source_system='test_suite',
    source_request_id=999001,
    request_type='coding',
    origin_floor='floor_05',
    title='Validation route',
    description='Test Floor 24 routing decision.'
)

assert decision['routing_floor'] == 'floor_24'
assert decision['selected_lift'] == 'model_lift'
assert decision['execution_enabled'] == 0
assert decision['status'] == 'routed_to_socket_layer'

print('MODEL ROUTING DEPARTMENT V1.1 VALIDATION PASSED')
print('Processed coding requests:', len(processed))
print('Route decisions:', dept.dashboard()['route_decisions'])
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
from tower.model_routing_department import ModelRoutingDepartment

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
.model{background:#143d5a;border:1px solid #50bfff}
.coding{background:#17365a;border:1px solid #7fb7ff}
.routing{background:#174a5a;border:1px solid #78e5ff}
pre{background:#050c16;padding:10px;border-radius:8px;max-height:235px;overflow:auto}
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
<div class="panel"><h2>Model Infrastructure</h2><pre id="model"></pre></div>
<div class="panel"><h2>Model Request Paths</h2><pre id="paths"></pre></div>
<div class="panel"><h2>Lift Network</h2><pre id="lifts"></pre></div>
<div class="panel"><h2>Providers</h2><pre id="providers"></pre></div>
<div class="panel"><h2>Packets</h2><pre id="packets"></pre></div>
</div>
</div>

<script>
function floorClass(f){
  if(f.id==="floor_24") return "routing";
  if(["floor_23","floor_27"].includes(f.id)) return "model";
  if(f.id==="floor_05") return "coding";
  return f.status;
}

async function load(){
  let s = await (await fetch("/api/status")).json();
  let m = await (await fetch("/api/model_infrastructure")).json();
  let c = await (await fetch("/api/coding_department")).json();
  let r = await (await fetch("/api/model_routing_department")).json();

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
    direct_provider_access:c.direct_provider_access,
    routes_through:c.routes_through,
    requests:c.requests,
    patch_queue:c.patch_queue,
    review_queue:c.review_queue,
    test_queue:c.test_queue,
    workspaces:c.workspaces.length,
    worker_slots:c.worker_slots.length,
    recent_requests:c.recent_requests
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
    by_socket:r.by_socket,
    recent_decisions:r.recent_decisions
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
Model Routing Department V1.1

Floor 24 is now a routing exchange.

It includes:
- Sealed packet intake
- Provider selection simulation
- Route decision records
- Fallback route planning
- Model Lift handoff records
- Routing worker slots
- Dashboard panel

Floor 24 does not execute AI providers.
It only decides where sealed model-bound packets should go.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/process_model_routes.sh
./scripts/model_routing_status.sh
python3 tests/test_model_routing_department_v11.py
"""

if "Model Routing Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Floor 24 Model Routing Department V1.1 installed.")
print("Run:")
print("./scripts/process_model_routes.sh")
print("./scripts/model_routing_status.sh")
