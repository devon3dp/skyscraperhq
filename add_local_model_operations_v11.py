from pathlib import Path
from datetime import datetime, UTC
import json
import os
import sqlite3
import subprocess
import shutil
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

print("Installing Floor 27 Local Model Operations Department V1.1...")

for folder in [
    "floors/floor_27_local_model_operations_department/local_inventory",
    "floors/floor_27_local_model_operations_department/role_catalog",
    "floors/floor_27_local_model_operations_department/model_readiness",
    "floors/floor_27_local_model_operations_department/recommended_bindings",
    "floors/floor_27_local_model_operations_department/handoff_from_floor_24",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower",
    "src/dashboard"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

local_model_roles = [
    {
        "role": "general_reasoning",
        "purpose": "General response, planning, and reasoning tasks.",
        "preferred_markers": ["qwen", "llama", "mistral", "neural"],
        "floor": "floor_27"
    },
    {
        "role": "coding",
        "purpose": "Code generation, bug fixing, refactoring, and test scaffolding.",
        "preferred_markers": ["coder", "codellama", "deepseek"],
        "floor": "floor_27"
    },
    {
        "role": "vision",
        "purpose": "Image and screenshot interpretation.",
        "preferred_markers": ["llava", "vision"],
        "floor": "floor_27"
    },
    {
        "role": "research",
        "purpose": "Research summaries, comparison, analysis, and synthesis.",
        "preferred_markers": ["mistral", "qwen", "neural"],
        "floor": "floor_27"
    },
    {
        "role": "embedding",
        "purpose": "Semantic memory, indexing, similarity search, retrieval.",
        "preferred_markers": ["embed", "nomic"],
        "floor": "floor_27"
    },
    {
        "role": "heavy_coding",
        "purpose": "Larger coding and architecture tasks.",
        "preferred_markers": ["13b", "40b", "iquest", "codellama"],
        "floor": "floor_27"
    },
    {
        "role": "fast_fallback",
        "purpose": "Fast lightweight local fallback.",
        "preferred_markers": ["1b", "3.2", "7b"],
        "floor": "floor_27"
    }
]

inventory_policy = {
    "version": "1.1",
    "floor_id": "floor_27",
    "department": "Local Model Operations Department",
    "models_required_for_tower_boot": False,
    "execution_enabled": False,
    "hardwired_models": False,
    "provider": "ollama_optional",
    "principle": "Local models are optional tenants. The tower owns the inventory, role catalog, and readiness records.",
    "receives_from": ["floor_24"],
    "incoming_lift": "model_lift",
    "does_not_execute_models_yet": True
}

write_json("data/registries/local_model_roles.json", local_model_roles)
write_json("data/registries/local_model_inventory_policy.json", inventory_policy)
write_json("data/registries/local_model_catalog.json", [])
write_json("data/registries/local_model_role_recommendations.json", [])

write_json("floors/floor_27_local_model_operations_department/floor_manifest.json", {
    "floor_id": "floor_27",
    "department": "Local Model Operations Department",
    "version": "1.1",
    "role": "optional_local_model_inventory_and_readiness",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_models": False,
    "receives_from": ["floor_24"],
    "incoming_lift": "model_lift",
    "notice": "Floor 27 inventories local models and recommends roles. It does not execute model calls yet."
})

write("config/local_model_operations.yaml", """
local_model_operations:
  version: 1.1
  floor_id: floor_27
  role: optional_local_model_inventory
  models_required: false
  kernel_required: false
  execution_enabled: false
  hardwired_models: false
  provider: ollama_optional

lifts:
  incoming_from_model_routing: model_lift

principle: Floor 27 inventories optional local models and recommends worker roles. It does not execute inference yet.
""")

write("src/tower/local_model_operations.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3
import subprocess
import shutil

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "local_model_operations.sqlite"

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
CREATE TABLE IF NOT EXISTS local_models (
    name TEXT PRIMARY KEY,
    provider TEXT,
    primary_role TEXT,
    capabilities_json TEXT,
    size_hint TEXT,
    status TEXT,
    detected_ts TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS role_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    slot_id TEXT,
    recommended_model TEXT,
    role TEXT,
    reason TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS inventory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    event_type TEXT,
    provider TEXT,
    discovered_count INTEGER,
    details TEXT
);
"""

class LocalModelOperations:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def classify(self, name):
        n = name.lower()
        caps = []

        if "embed" in n or "nomic" in n:
            caps.append("embedding")

        if "llava" in n or "vision" in n:
            caps.append("vision")

        if "coder" in n or "codellama" in n or "deepseek" in n:
            caps.append("coding")

        if "13b" in n or "40b" in n or "iquest" in n:
            caps.append("heavy_coding")

        if "mistral" in n or "qwen" in n or "neural" in n:
            caps.append("research")

        if "qwen" in n or "llama" in n or "mistral" in n or "neural" in n:
            caps.append("general_reasoning")

        if "1b" in n or "3.2" in n or "7b" in n:
            caps.append("fast_fallback")

        if not caps:
            caps.append("general_reasoning")

        priority = ["embedding", "vision", "coding", "heavy_coding", "research", "general_reasoning", "fast_fallback"]
        primary = next((r for r in priority if r in caps), caps[0])

        if "40b" in n:
            size_hint = "large"
        elif "13b" in n:
            size_hint = "medium_large"
        elif "7b" in n or "8b" in n or "9b" in n:
            size_hint = "medium"
        elif "3.2" in n or "1b" in n:
            size_hint = "small"
        elif "embed" in n or "nomic" in n:
            size_hint = "embedding"
        else:
            size_hint = "unknown"

        return primary, caps, size_hint

    def parse_ollama_list(self, output):
        models = []
        lines = output.splitlines()
        for line in lines[1:]:
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            primary, caps, size_hint = self.classify(name)
            models.append({
                "name": name,
                "provider": "ollama",
                "primary_role": primary,
                "capabilities": caps,
                "size_hint": size_hint,
                "status": "detected",
                "detected_ts": now(),
                "notes": "Detected from ollama list."
            })
        return models

    def detect_ollama(self):
        if shutil.which("ollama") is None:
            save_json("local_model_catalog.json", [])
            self.record_event("inventory_failed", "ollama", 0, {"note": "ollama command not found"})
            return {"available": False, "models": [], "note": "ollama command not found"}

        try:
            output = subprocess.check_output(
                ["ollama", "list"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=10
            )
            models = self.parse_ollama_list(output)
            self.save_catalog(models)
            self.record_event("inventory_synced", "ollama", len(models), {"source": "ollama list"})
            self.recommend_bindings()
            return {"available": True, "models": models, "note": "local model inventory synced"}
        except Exception as e:
            self.record_event("inventory_failed", "ollama", 0, {"error": str(e)})
            return {"available": False, "models": [], "note": str(e)}

    def sync_from_existing_discovery(self):
        discovered = load_json("discovered_ollama_models.json", [])
        models = []
        for item in discovered:
            name = item.get("name")
            if not name:
                continue
            primary, caps, size_hint = self.classify(name)
            models.append({
                "name": name,
                "provider": "ollama",
                "primary_role": primary,
                "capabilities": caps,
                "size_hint": size_hint,
                "status": "detected",
                "detected_ts": item.get("detected_ts", now()),
                "notes": "Imported from discovered_ollama_models.json."
            })
        self.save_catalog(models)
        self.record_event("inventory_imported", "ollama", len(models), {"source": "discovered_ollama_models.json"})
        self.recommend_bindings()
        return {"available": bool(models), "models": models, "note": "imported existing discovery"}

    def save_catalog(self, models):
        save_json("local_model_catalog.json", models)
        for m in models:
            self.conn.execute(
                "INSERT OR REPLACE INTO local_models VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    m["name"],
                    m["provider"],
                    m["primary_role"],
                    json.dumps(m["capabilities"]),
                    m["size_hint"],
                    m["status"],
                    m["detected_ts"],
                    m.get("notes", "")
                )
            )
        self.conn.commit()

    def record_event(self, event_type, provider, count, details):
        self.conn.execute(
            "INSERT INTO inventory_events(ts, event_type, provider, discovered_count, details) VALUES (?, ?, ?, ?, ?)",
            (now(), event_type, provider, int(count), json.dumps(details))
        )
        self.conn.commit()

    def catalog(self):
        catalog = load_json("local_model_catalog.json", [])
        if catalog:
            return catalog

        rows = self.conn.execute("SELECT * FROM local_models ORDER BY primary_role, name").fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["capabilities"] = json.loads(item.pop("capabilities_json"))
            out.append(item)
        return out

    def role_summary(self):
        summary = {}
        for m in self.catalog():
            for cap in m.get("capabilities", []):
                summary[cap] = summary.get(cap, 0) + 1
        return summary

    def pick_model_for_role(self, role):
        models = self.catalog()

        exact = [m for m in models if m.get("primary_role") == role]
        if exact:
            return exact[0]

        capable = [m for m in models if role in m.get("capabilities", [])]
        if capable:
            return capable[0]

        if role == "general_reasoning":
            fallback = [m for m in models if "general_reasoning" in m.get("capabilities", [])]
            if fallback:
                return fallback[0]

        return None

    def recommend_bindings(self):
        slots = load_json("model_worker_slots.json", [])
        role_map = {
            "general_reasoning_slot": "general_reasoning",
            "coding_model_slot": "coding",
            "vision_model_slot": "vision",
            "research_model_slot": "research"
        }

        recommendations = []

        self.conn.execute("DELETE FROM role_recommendations")

        for slot in slots:
            slot_id = slot.get("id")
            wanted = role_map.get(slot_id)
            if not wanted:
                continue

            model = self.pick_model_for_role(wanted)
            if model:
                rec = {
                    "slot_id": slot_id,
                    "role": wanted,
                    "recommended_model": model["name"],
                    "status": "recommended_not_bound",
                    "reason": f"Model has capability for {wanted}. Binding is not automatic."
                }
            else:
                rec = {
                    "slot_id": slot_id,
                    "role": wanted,
                    "recommended_model": None,
                    "status": "no_candidate",
                    "reason": f"No local model candidate found for {wanted}."
                }

            recommendations.append(rec)
            self.conn.execute(
                "INSERT INTO role_recommendations(ts, slot_id, recommended_model, role, reason, status) VALUES (?, ?, ?, ?, ?, ?)",
                (now(), rec["slot_id"], rec["recommended_model"], rec["role"], rec["reason"], rec["status"])
            )

        self.conn.commit()
        save_json("local_model_role_recommendations.json", recommendations)
        return recommendations

    def recommendations(self):
        recs = load_json("local_model_role_recommendations.json", [])
        if recs:
            return recs

        rows = self.conn.execute("SELECT slot_id, recommended_model, role, reason, status FROM role_recommendations ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def recent_events(self, limit=10):
        rows = self.conn.execute("SELECT * FROM inventory_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        catalog = self.catalog()
        if not catalog:
            self.sync_from_existing_discovery()
            catalog = self.catalog()

        return {
            "database": str(DB),
            "floor": "floor_27",
            "department": "Local Model Operations Department",
            "version": "1.1",
            "models_required": False,
            "kernel_required": False,
            "execution_enabled": False,
            "hardwired_models": False,
            "incoming_lift": "model_lift",
            "detected_models": len(catalog),
            "role_summary": self.role_summary(),
            "recommendations": self.recommendations(),
            "catalog": catalog,
            "recent_events": self.recent_events(10)
        }

if __name__ == "__main__":
    dept = LocalModelOperations()
    dept.sync_from_existing_discovery()
    print(json.dumps(dept.dashboard(), indent=2))
''')

write("scripts/local_model_operations_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.local_model_operations
""")

write("scripts/sync_local_model_inventory.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.local_model_operations import LocalModelOperations
import json
dept = LocalModelOperations()
print(json.dumps(dept.detect_ollama(), indent=2))
print(json.dumps({
    "recommendations": dept.recommend_bindings()
}, indent=2))
PY2
""")

write("scripts/recommend_local_model_bindings.py", """
import sys
import json
from pathlib import Path
ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))
from tower.local_model_operations import LocalModelOperations
dept = LocalModelOperations()
print(json.dumps(dept.recommend_bindings(), indent=2))
""")

for script in [
    "scripts/local_model_operations_status.sh",
    "scripts/sync_local_model_inventory.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_local_model_operations_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.local_model_operations import LocalModelOperations

dept = LocalModelOperations()
dept.sync_from_existing_discovery()
dash = dept.dashboard()

assert dash['floor'] == 'floor_27'
assert dash['models_required'] is False
assert dash['kernel_required'] is False
assert dash['execution_enabled'] is False
assert dash['hardwired_models'] is False
assert dash['incoming_lift'] == 'model_lift'
assert isinstance(dash['catalog'], list)
assert isinstance(dash['recommendations'], list)

print('LOCAL MODEL OPERATIONS V1.1 VALIDATION PASSED')
print('Detected models:', dash['detected_models'])
print('Role summary:', dash['role_summary'])
print('Recommendations:', len(dash['recommendations']))
""")

# Update dashboard with Floor 27 panel.
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
.localmodel{background:#163f46;border:1px solid #6fffe0}
pre{background:#050c16;padding:10px;border-radius:8px;max-height:230px;overflow:auto}
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
  if(f.id==="floor_27") return "localmodel";
  if(f.id==="floor_23") return "model";
  if(f.id==="floor_05") return "coding";
  return f.status;
}

async function load(){
  let s = await (await fetch("/api/status")).json();
  let m = await (await fetch("/api/model_infrastructure")).json();
  let c = await (await fetch("/api/coding_department")).json();
  let r = await (await fetch("/api/model_routing_department")).json();
  let lm = await (await fetch("/api/local_model_operations")).json();

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
Local Model Operations Department V1.1

Floor 27 is now a local model inventory and readiness floor.

It includes:
- Optional Ollama model inventory
- Role classification
- Local model catalog
- Worker-slot recommendations
- Local model readiness records
- Dashboard panel

Floor 27 does not execute model inference yet.
It only inventories models and recommends future bindings.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/sync_local_model_inventory.sh
./scripts/local_model_operations_status.sh
python3 tests/test_local_model_operations_v11.py
"""

if "Local Model Operations Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Floor 27 Local Model Operations Department V1.1 installed.")
print("Run:")
print("./scripts/sync_local_model_inventory.sh")
print("./scripts/local_model_operations_status.sh")
