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

print("Installing Floor 5 Coding Department V1.1...")

for folder in [
    "floors/floor_05_coding_department/ports",
    "floors/floor_05_coding_department/workspaces",
    "floors/floor_05_coding_department/request_queue",
    "floors/floor_05_coding_department/patch_queue",
    "floors/floor_05_coding_department/review_queue",
    "floors/floor_05_coding_department/test_queue",
    "floors/floor_05_coding_department/handoff",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower",
    "src/dashboard"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

coding_workspaces = [
    {
        "id": "default_workspace",
        "name": "Default Coding Workspace",
        "floor_id": "floor_05",
        "status": "ready",
        "purpose": "General coding requests, future project work, patches, reviews, and tests.",
        "direct_provider_access": False,
        "routes_through": "floor_24"
    },
    {
        "id": "claude_code_workspace",
        "name": "Claude Code Workspace Port",
        "floor_id": "floor_05",
        "status": "socket_ready_not_connected",
        "purpose": "Future Claude Code handoff workspace. No Claude execution is hardwired.",
        "direct_provider_access": False,
        "routes_through": "floor_24"
    },
    {
        "id": "local_coder_workspace",
        "name": "Local Coder Workspace Port",
        "floor_id": "floor_05",
        "status": "socket_ready_not_connected",
        "purpose": "Future local coder handoff workspace. Routes to Floor 24 first.",
        "direct_provider_access": False,
        "routes_through": "floor_24"
    }
]

coding_worker_slots = [
    {
        "id": "coding_intake_worker",
        "name": "Coding Intake Worker",
        "floor_id": "floor_05",
        "role": "request_intake",
        "status": "simulation_ready",
        "model_bound": False
    },
    {
        "id": "patch_queue_worker",
        "name": "Patch Queue Worker",
        "floor_id": "floor_05",
        "role": "patch_preparation",
        "status": "simulation_ready",
        "model_bound": False
    },
    {
        "id": "review_queue_worker",
        "name": "Review Queue Worker",
        "floor_id": "floor_05",
        "role": "code_review_preparation",
        "status": "simulation_ready",
        "model_bound": False
    },
    {
        "id": "test_queue_worker",
        "name": "Test Queue Worker",
        "floor_id": "floor_05",
        "role": "test_preparation",
        "status": "simulation_ready",
        "model_bound": False
    },
    {
        "id": "handoff_worker",
        "name": "Model Handoff Worker",
        "floor_id": "floor_05",
        "role": "sealed_packet_handoff_to_floor_24",
        "status": "simulation_ready",
        "model_bound": False
    }
]

coding_request_types = [
    {
        "id": "code_generation",
        "label": "Code Generation",
        "default_priority": 5,
        "routes_to": "floor_24",
        "first_lift": "service_lift"
    },
    {
        "id": "bug_fix",
        "label": "Bug Fix",
        "default_priority": 6,
        "routes_to": "floor_24",
        "first_lift": "service_lift"
    },
    {
        "id": "refactor",
        "label": "Refactor",
        "default_priority": 5,
        "routes_to": "floor_24",
        "first_lift": "service_lift"
    },
    {
        "id": "code_review",
        "label": "Code Review",
        "default_priority": 4,
        "routes_to": "floor_24",
        "first_lift": "service_lift"
    },
    {
        "id": "test_generation",
        "label": "Test Generation",
        "default_priority": 5,
        "routes_to": "floor_24",
        "first_lift": "service_lift"
    },
    {
        "id": "claude_code_handoff",
        "label": "Claude Code Handoff",
        "default_priority": 7,
        "routes_to": "floor_24",
        "first_lift": "service_lift"
    }
]

write_json("data/registries/coding_workspaces.json", coding_workspaces)
write_json("data/registries/coding_worker_slots.json", coding_worker_slots)
write_json("data/registries/coding_request_types.json", coding_request_types)

write_json("floors/floor_05_coding_department/floor_manifest.json", {
    "floor_id": "floor_05",
    "department": "Coding Department",
    "version": "1.1",
    "role": "coding_workspace_and_request_origin",
    "kernel_required": False,
    "models_required": False,
    "direct_provider_access": False,
    "routes_through": "floor_24",
    "first_lift": "service_lift",
    "queues": [
        "request_queue",
        "patch_queue",
        "review_queue",
        "test_queue"
    ],
    "ports": [
        "claude_code_port",
        "local_coder_port",
        "future_coding_provider_port"
    ],
    "notice": "Floor 5 prepares coding work and sends sealed requests to Floor 24. It does not execute AI providers directly."
})

write_json("floors/floor_05_coding_department/ports/claude_code_port.json", {
    "port": "Claude Code Port",
    "provider": "claude",
    "status": "socket_ready_not_connected",
    "hardwired": False,
    "execution_enabled": False,
    "direct_provider_access": False,
    "routes_through": "floor_24",
    "notice": "Claude Code can connect later as an external tenant. The tower owns the port."
})

write_json("floors/floor_05_coding_department/ports/local_coder_port.json", {
    "port": "Local Coder Port",
    "provider": "local_models",
    "status": "socket_ready_not_connected",
    "hardwired": False,
    "execution_enabled": False,
    "direct_provider_access": False,
    "routes_through": "floor_24",
    "notice": "Local coder models can connect later through routing infrastructure."
})

write("config/coding_department.yaml", """
coding_department:
  version: 1.1
  floor_id: floor_05
  role: coding_workspace_and_request_origin
  direct_provider_access: false
  routes_through: floor_24
  first_lift: service_lift
  models_required: false
  kernel_required: false

queues:
  request_queue: active
  patch_queue: active
  review_queue: active
  test_queue: active

ports:
  claude_code_port: socket_ready_not_connected
  local_coder_port: socket_ready_not_connected
  future_coding_provider_port: expansion_ready

principle: Floor 5 creates coding work packets. Floor 24 routes them. Providers remain external tenants.
""")

write("src/tower/coding_department.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "coding_department.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS coding_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    title TEXT,
    request_type TEXT,
    priority INTEGER,
    description TEXT,
    origin_floor TEXT,
    routing_floor TEXT,
    first_lift TEXT,
    status TEXT,
    lift_receipt TEXT
);

CREATE TABLE IF NOT EXISTS patch_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    request_id INTEGER,
    title TEXT,
    status TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    request_id INTEGER,
    title TEXT,
    status TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS test_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    request_id INTEGER,
    title TEXT,
    status TEXT,
    notes TEXT
);
"""

class CodingDepartment:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def request_types(self):
        return load_json("coding_request_types.json", [])

    def workspaces(self):
        return load_json("coding_workspaces.json", [])

    def worker_slots(self):
        return load_json("coding_worker_slots.json", [])

    def create_request(self, title, request_type="code_generation", description="", priority=None, send_lift=True):
        types = {t["id"]: t for t in self.request_types()}
        if request_type not in types:
            request_type = "code_generation"

        cfg = types[request_type]
        if priority is None:
            priority = int(cfg.get("default_priority", 5))

        origin = "floor_05"
        routing = cfg.get("routes_to", "floor_24")
        first_lift = cfg.get("first_lift", "service_lift")
        receipt = "not_sent"

        if send_lift:
            try:
                from tower.lifts import LiftNetwork
                lift_result = LiftNetwork().send(origin, routing, first_lift, priority)
                receipt = json.dumps(lift_result)
            except Exception as e:
                receipt = json.dumps({"error": str(e)})

        self.conn.execute(
            """
            INSERT INTO coding_requests
            (ts, title, request_type, priority, description, origin_floor, routing_floor, first_lift, status, lift_receipt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now(), title, request_type, priority, description, origin, routing, first_lift, "queued_for_routing", receipt)
        )
        self.conn.commit()
        request_id = self.conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

        queue_title = f"{request_type}: {title}"

        if request_type in ["bug_fix", "refactor", "code_generation", "claude_code_handoff"]:
            self.conn.execute(
                "INSERT INTO patch_queue(ts, request_id, title, status, notes) VALUES (?, ?, ?, ?, ?)",
                (now(), request_id, queue_title, "pending", "Awaiting future coding worker.")
            )

        if request_type in ["code_review", "refactor", "claude_code_handoff"]:
            self.conn.execute(
                "INSERT INTO review_queue(ts, request_id, title, status, notes) VALUES (?, ?, ?, ?, ?)",
                (now(), request_id, queue_title, "pending", "Awaiting future review worker.")
            )

        if request_type in ["test_generation", "bug_fix", "refactor"]:
            self.conn.execute(
                "INSERT INTO test_queue(ts, request_id, title, status, notes) VALUES (?, ?, ?, ?, ?)",
                (now(), request_id, queue_title, "pending", "Awaiting future test worker.")
            )

        self.conn.commit()
        return self.get_request(request_id)

    def get_request(self, request_id):
        row = self.conn.execute("SELECT * FROM coding_requests WHERE id=?", (request_id,)).fetchone()
        return dict(row) if row else None

    def recent_requests(self, limit=20):
        rows = self.conn.execute("SELECT * FROM coding_requests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def queue_rows(self, table, limit=20):
        rows = self.conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        req_count = self.conn.execute("SELECT COUNT(*) AS c FROM coding_requests").fetchone()["c"]
        patch_count = self.conn.execute("SELECT COUNT(*) AS c FROM patch_queue").fetchone()["c"]
        review_count = self.conn.execute("SELECT COUNT(*) AS c FROM review_queue").fetchone()["c"]
        test_count = self.conn.execute("SELECT COUNT(*) AS c FROM test_queue").fetchone()["c"]

        return {
            "database": str(DB),
            "floor": "floor_05",
            "department": "Coding Department",
            "version": "1.1",
            "direct_provider_access": False,
            "routes_through": "floor_24",
            "first_lift": "service_lift",
            "models_required": False,
            "kernel_required": False,
            "requests": req_count,
            "patch_queue": patch_count,
            "review_queue": review_count,
            "test_queue": test_count,
            "workspaces": self.workspaces(),
            "worker_slots": self.worker_slots(),
            "recent_requests": self.recent_requests(10)
        }

if __name__ == "__main__":
    dept = CodingDepartment()
    print(json.dumps(dept.dashboard(), indent=2))
''')

write("scripts/coding_department_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.coding_department
""")

write("scripts/create_coding_request.py", """
import sys
import json
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.coding_department import CodingDepartment

title = sys.argv[1] if len(sys.argv) > 1 else 'Build future coding worker scaffold'
request_type = sys.argv[2] if len(sys.argv) > 2 else 'code_generation'
description = ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else 'Generated from Floor 5 Coding Department script.'

dept = CodingDepartment()
result = dept.create_request(title, request_type, description)
print(json.dumps(result, indent=2))
""")

write("scripts/seed_coding_department.sh", """
#!/usr/bin/env bash
set -e
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

python3 scripts/create_coding_request.py "Prepare Claude Code port wiring" claude_code_handoff "Create future handoff path from Floor 5 to Floor 24."
python3 scripts/create_coding_request.py "Prepare local coder slot" code_generation "Create future local coder queue path through Floor 24."
python3 scripts/create_coding_request.py "Prepare test queue structure" test_generation "Generate future test worker queue."
""")

for script in [
    "scripts/coding_department_status.sh",
    "scripts/seed_coding_department.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_coding_department_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.coding_department import CodingDepartment

dept = CodingDepartment()
dash = dept.dashboard()

assert dash['floor'] == 'floor_05'
assert dash['direct_provider_access'] is False
assert dash['routes_through'] == 'floor_24'
assert dash['models_required'] is False
assert dash['kernel_required'] is False
assert len(dash['workspaces']) >= 3
assert len(dash['worker_slots']) >= 5

req = dept.create_request(
    'Validation coding request',
    'code_generation',
    'Test sealed path from Floor 5 to Floor 24.',
    send_lift=True
)

assert req['origin_floor'] == 'floor_05'
assert req['routing_floor'] == 'floor_24'
assert req['first_lift'] == 'service_lift'
assert req['status'] == 'queued_for_routing'

print('CODING DEPARTMENT V1.1 VALIDATION PASSED')
print('Requests:', dept.dashboard()['requests'])
print('Patch queue:', dept.dashboard()['patch_queue'])
print('Review queue:', dept.dashboard()['review_queue'])
print('Test queue:', dept.dashboard()['test_queue'])
""")

# Replace dashboard server with V1.1 plus Coding Department panel.
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
pre{background:#050c16;padding:10px;border-radius:8px;max-height:240px;overflow:auto}
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
<div class="panel"><h2>Model Infrastructure</h2><pre id="model"></pre></div>
<div class="panel"><h2>Model Request Paths</h2><pre id="paths"></pre></div>
<div class="panel"><h2>Lift Network</h2><pre id="lifts"></pre></div>
<div class="panel"><h2>Providers</h2><pre id="providers"></pre></div>
<div class="panel"><h2>Packets</h2><pre id="packets"></pre></div>
</div>
</div>

<script>
function floorClass(f){
  if(["floor_23","floor_24","floor_27"].includes(f.id)) return "model";
  if(f.id==="floor_05") return "coding";
  return f.status;
}

async function load(){
  let s = await (await fetch("/api/status")).json();
  let m = await (await fetch("/api/model_infrastructure")).json();
  let c = await (await fetch("/api/coding_department")).json();

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
Coding Department V1.1

Floor 5 is now a real coding workspace floor.

It includes:
- Claude Code Port
- Local Coder Port
- Coding request queue
- Patch queue
- Review queue
- Test queue
- Workspace registry
- Worker-slot registry
- Sealed handoff path to Floor 24 through the Service Lift

Floor 5 does not directly access providers.
All coding requests route to Floor 24 first.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/coding_department_status.sh
./scripts/seed_coding_department.sh
python3 scripts/create_coding_request.py "Build parser" code_generation "Prepare parser scaffold."
"""

if "Coding Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Floor 5 Coding Department V1.1 installed.")
print("Coding Department status command:")
print("./scripts/coding_department_status.sh")
