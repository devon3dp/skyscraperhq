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

print("Repairing and installing Model Infrastructure V1.1...")

for folder in [
    "floors/floor_05_coding_department/ports",
    "floors/floor_23_air_llm_operations_department/provider_sockets",
    "floors/floor_24_model_routing_department/routing_exchange",
    "floors/floor_27_local_model_operations_department/local_inventory",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower",
    "src/dashboard"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

provider_sockets = [
    {"id":"air_llm_cloud_socket","provider":"air_llm_cloud","display_name":"AIR LLM Cloud Socket","location":"roof_external_layer","building_floor":"floor_23","status":"socket_ready_not_connected","hardwired":False,"execution_enabled":False},
    {"id":"claude_socket","provider":"claude","display_name":"Claude Socket","location":"external_provider","building_floor":"floor_23","status":"socket_ready_not_connected","hardwired":False,"execution_enabled":False},
    {"id":"claude_code_socket","provider":"claude","display_name":"Claude Code Socket","location":"external_provider","building_floor":"floor_05","status":"socket_ready_not_connected","hardwired":False,"execution_enabled":False},
    {"id":"ollama_local_socket","provider":"ollama","display_name":"Ollama Local Socket","location":"local_machine_optional","building_floor":"floor_27","status":"optional_detectable","hardwired":False,"execution_enabled":False},
    {"id":"openai_socket","provider":"openai","display_name":"OpenAI Socket","location":"external_provider","building_floor":"floor_23","status":"socket_ready_not_connected","hardwired":False,"execution_enabled":False},
    {"id":"gemini_socket","provider":"gemini","display_name":"Gemini Socket","location":"external_provider","building_floor":"floor_23","status":"socket_ready_not_connected","hardwired":False,"execution_enabled":False},
    {"id":"deepseek_socket","provider":"deepseek","display_name":"DeepSeek Socket","location":"external_provider","building_floor":"floor_23","status":"socket_ready_not_connected","hardwired":False,"execution_enabled":False},
    {"id":"future_model_socket","provider":"future_models","display_name":"Future Model Socket","location":"future_external_or_local_provider","building_floor":"floor_23","status":"expansion_ready","hardwired":False,"execution_enabled":False}
]

model_worker_slots = [
    {"id":"general_reasoning_slot","name":"General Reasoning Worker Slot","role":"general_reasoning","preferred_floor":"floor_27","bound_provider":None,"bound_model":None,"status":"unbound_ready","hardwired":False},
    {"id":"coding_model_slot","name":"Coding Model Worker Slot","role":"coding","preferred_floor":"floor_27","bound_provider":None,"bound_model":None,"status":"unbound_ready","hardwired":False},
    {"id":"vision_model_slot","name":"Vision Model Worker Slot","role":"vision","preferred_floor":"floor_27","bound_provider":None,"bound_model":None,"status":"unbound_ready","hardwired":False},
    {"id":"research_model_slot","name":"Research Model Worker Slot","role":"research","preferred_floor":"floor_27","bound_provider":None,"bound_model":None,"status":"unbound_ready","hardwired":False},
    {"id":"claude_code_port_slot","name":"Claude Code Port Slot","role":"coding_external_port","preferred_floor":"floor_05","bound_provider":"claude","bound_model":None,"status":"socket_ready_not_connected","hardwired":False}
]

model_request_paths = [
    {"id":"coding_request_path","request_type":"coding","origin_floor":"floor_05","first_hop":"floor_24","first_lift":"service_lift","routing_floor":"floor_24","possible_targets":["floor_27","floor_23","roof"],"second_lift":"model_lift","sealed_packets":True,"direct_provider_access":False,"description":"Coding Department sends sealed requests to Floor 24 first. Floor 24 then routes to local or external provider sockets."},
    {"id":"general_request_path","request_type":"general","origin_floor":"ground","first_hop":"floor_24","first_lift":"service_lift","routing_floor":"floor_24","possible_targets":["floor_27","floor_23","roof"],"second_lift":"model_lift","sealed_packets":True,"direct_provider_access":False,"description":"General requests route from the lobby to Floor 24."},
    {"id":"vision_request_path","request_type":"vision","origin_floor":"floor_13","first_hop":"floor_24","first_lift":"service_lift","routing_floor":"floor_24","possible_targets":["floor_27","floor_23","roof"],"second_lift":"model_lift","sealed_packets":True,"direct_provider_access":False,"description":"Vision requests route to Floor 24 before any provider socket."},
    {"id":"local_inventory_path","request_type":"local_model_inventory","origin_floor":"floor_27","first_hop":"floor_27","first_lift":"none","routing_floor":"floor_27","possible_targets":["local_machine_optional"],"second_lift":"none","sealed_packets":False,"direct_provider_access":False,"description":"Floor 27 detects optional local models without being required for tower boot."}
]

write_json("data/registries/provider_sockets.json", provider_sockets)
write_json("data/registries/model_worker_slots.json", model_worker_slots)
write_json("data/registries/model_request_paths.json", model_request_paths)
write_json("data/registries/discovered_ollama_models.json", [])

providers = read_json("data/registries/providers.json", [])
existing = {p.get("id") for p in providers}
for socket in provider_sockets:
    pid = socket["provider"]
    if pid not in existing:
        providers.append({
            "id": pid,
            "name": socket["display_name"].replace(" Socket", ""),
            "location": socket["location"],
            "status": socket["status"],
            "hardwired": False
        })
write_json("data/registries/providers.json", providers)

write_json("floors/floor_05_coding_department/ports/claude_code_port.json", {
    "floor_id":"floor_05",
    "department":"Coding Department",
    "port":"Claude Code Port",
    "role":"coding_request_origin",
    "direct_provider_access":False,
    "routes_through":"floor_24",
    "first_lift":"service_lift",
    "status":"socket_ready_not_connected",
    "hardwired":False,
    "notice":"Floor 5 is a coding workspace. It is not the model routing core."
})

write_json("floors/floor_23_air_llm_operations_department/provider_sockets/manifest.json", {
    "floor_id":"floor_23",
    "department":"AIR LLM Operations Department",
    "role":"external_provider_socket_layer",
    "providers_are_external":True,
    "hardwired":False,
    "execution_enabled":False,
    "notice":"This floor manages provider sockets. Providers remain outside the building."
})

write_json("floors/floor_24_model_routing_department/routing_exchange/manifest.json", {
    "floor_id":"floor_24",
    "department":"Model Routing Department",
    "role":"routing_exchange",
    "routing_policy":"registry_driven",
    "direct_provider_access":False,
    "notice":"All model-bound requests pass through Floor 24 routing exchange."
})

write_json("floors/floor_27_local_model_operations_department/local_inventory/manifest.json", {
    "floor_id":"floor_27",
    "department":"Local Model Operations Department",
    "role":"optional_local_model_inventory",
    "requires_ollama":False,
    "tower_boot_requires_models":False,
    "status":"inventory_ready",
    "notice":"Local models are optional tenants. The tower runs without them."
})

write("config/model_infrastructure.yaml", """
model_infrastructure:
  version: 1.1
  principle: Models are temporary tenants. The tower owns the infrastructure.
  hardwire_providers: false
  tower_boot_requires_models: false

floors:
  coding_request_origin: floor_05
  air_llm_operations: floor_23
  model_routing_exchange: floor_24
  local_model_operations: floor_27

routing:
  direct_provider_access_from_departments: false
  all_model_requests_route_through: floor_24
  packets_are_sealed: true

lifts:
  floor_05_to_floor_24: service_lift
  floor_24_to_floor_23: model_lift
  floor_24_to_floor_27: model_lift
  floor_24_to_roof: model_lift
""")

write("src/tower/model_infrastructure.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3
import shutil
import subprocess

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "model_infrastructure.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_sockets (
    id TEXT PRIMARY KEY,
    provider TEXT,
    display_name TEXT,
    location TEXT,
    building_floor TEXT,
    status TEXT,
    hardwired INTEGER,
    execution_enabled INTEGER
);

CREATE TABLE IF NOT EXISTS model_worker_slots (
    id TEXT PRIMARY KEY,
    name TEXT,
    role TEXT,
    preferred_floor TEXT,
    bound_provider TEXT,
    bound_model TEXT,
    status TEXT,
    hardwired INTEGER
);

CREATE TABLE IF NOT EXISTS model_request_paths (
    id TEXT PRIMARY KEY,
    request_type TEXT,
    origin_floor TEXT,
    first_hop TEXT,
    first_lift TEXT,
    routing_floor TEXT,
    possible_targets_json TEXT,
    second_lift TEXT,
    sealed_packets INTEGER,
    direct_provider_access INTEGER,
    description TEXT
);
"""

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

class ModelInfrastructure:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.sync()

    def sync(self):
        for s in load_json("provider_sockets.json", []):
            self.conn.execute(
                "INSERT OR REPLACE INTO provider_sockets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (s["id"], s["provider"], s["display_name"], s["location"], s["building_floor"], s["status"], int(s["hardwired"]), int(s["execution_enabled"]))
            )

        for slot in load_json("model_worker_slots.json", []):
            self.conn.execute(
                "INSERT OR REPLACE INTO model_worker_slots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (slot["id"], slot["name"], slot["role"], slot["preferred_floor"], slot.get("bound_provider"), slot.get("bound_model"), slot["status"], int(slot["hardwired"]))
            )

        for p in load_json("model_request_paths.json", []):
            self.conn.execute(
                "INSERT OR REPLACE INTO model_request_paths VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p["id"], p["request_type"], p["origin_floor"], p["first_hop"], p["first_lift"], p["routing_floor"], json.dumps(p["possible_targets"]), p["second_lift"], int(p["sealed_packets"]), int(p["direct_provider_access"]), p["description"])
            )

        self.conn.commit()

    def detect_ollama(self):
        if shutil.which("ollama") is None:
            save_json("discovered_ollama_models.json", [])
            return {"available": False, "models": [], "note": "ollama command not found"}

        try:
            output = subprocess.check_output(["ollama", "list"], text=True, stderr=subprocess.STDOUT, timeout=10)
            models = []
            for line in output.splitlines()[1:]:
                parts = line.split()
                if parts:
                    models.append({"name": parts[0], "provider": "ollama", "status": "detected", "detected_ts": now()})
            save_json("discovered_ollama_models.json", models)
            return {"available": True, "models": models, "note": "ollama inventory synced"}
        except Exception as e:
            save_json("discovered_ollama_models.json", [])
            return {"available": False, "models": [], "note": str(e)}

    def sockets(self):
        rows = self.conn.execute("SELECT * FROM provider_sockets ORDER BY building_floor, provider").fetchall()
        return [dict(r) for r in rows]

    def slots(self):
        rows = self.conn.execute("SELECT * FROM model_worker_slots ORDER BY preferred_floor, role").fetchall()
        return [dict(r) for r in rows]

    def paths(self):
        rows = self.conn.execute("SELECT * FROM model_request_paths ORDER BY request_type").fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["possible_targets"] = json.loads(item.pop("possible_targets_json"))
            item["sealed_packets"] = bool(item["sealed_packets"])
            item["direct_provider_access"] = bool(item["direct_provider_access"])
            out.append(item)
        return out

    def route_plan(self, request_type):
        matches = [p for p in self.paths() if p["request_type"] == request_type]
        if not matches:
            return {"ok": False, "reason": "unknown_request_type", "request_type": request_type}
        path = matches[0]
        if request_type == "coding":
            wanted = ["coding", "coding_external_port"]
        elif request_type == "vision":
            wanted = ["vision"]
        else:
            wanted = ["general_reasoning", "research"]
        return {
            "ok": True,
            "request_type": request_type,
            "path": path,
            "candidate_slots": [s for s in self.slots() if s["role"] in wanted],
            "execution_enabled": False,
            "note": "Tower V1.1 plans routing only. Provider execution remains disabled."
        }

    def discovered_local_models(self):
        return load_json("discovered_ollama_models.json", [])

    def dashboard(self):
        return {
            "principle": "Models are temporary tenants. The tower owns the infrastructure.",
            "building_runs_without_models": True,
            "hardwired_providers": False,
            "execution_enabled": False,
            "sockets": self.sockets(),
            "worker_slots": self.slots(),
            "request_paths": self.paths(),
            "discovered_local_models": self.discovered_local_models()
        }

if __name__ == "__main__":
    print(json.dumps(ModelInfrastructure().dashboard(), indent=2))
''')

write("scripts/model_infrastructure_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.model_infrastructure
""")

write("scripts/sync_ollama_inventory.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.model_infrastructure import ModelInfrastructure
import json
print(json.dumps(ModelInfrastructure().detect_ollama(), indent=2))
PY2
""")

write("scripts/route_model_request.py", """
import sys
from pathlib import Path
import json
ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))
from tower.model_infrastructure import ModelInfrastructure
request_type = sys.argv[1] if len(sys.argv) > 1 else 'coding'
print(json.dumps(ModelInfrastructure().route_plan(request_type), indent=2))
""")

for script in ["scripts/model_infrastructure_status.sh", "scripts/sync_ollama_inventory.sh"]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_model_infrastructure_v11.py", """
import sys
from pathlib import Path
ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))
from tower.model_infrastructure import ModelInfrastructure

infra = ModelInfrastructure()
dash = infra.dashboard()

assert dash['building_runs_without_models'] is True
assert dash['hardwired_providers'] is False
assert dash['execution_enabled'] is False
assert len(dash['sockets']) >= 7
assert len(dash['worker_slots']) >= 5
assert len(dash['request_paths']) >= 4

coding = infra.route_plan('coding')
assert coding['ok'] is True
assert coding['path']['origin_floor'] == 'floor_05'
assert coding['path']['first_hop'] == 'floor_24'
assert coding['path']['direct_provider_access'] is False
assert coding['execution_enabled'] is False

print('MODEL INFRASTRUCTURE V1.1 VALIDATION PASSED')
print('Sockets:', len(dash['sockets']))
print('Worker slots:', len(dash['worker_slots']))
print('Request paths:', len(dash['request_paths']))
""")

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""
addition = """
Model Infrastructure V1.1

Correct architectural separation:
- Floor 5: Coding Department. Consumer/workspace floor.
- Floor 23: AIR LLM Operations. External provider sockets.
- Floor 24: Model Routing Department. Routing exchange.
- Floor 27: Local Model Operations. Optional local model inventory.

Floor 5 does not directly access providers.
Coding requests travel as sealed packets to Floor 24 first.

Path:
Floor 5 -> Service Lift -> Floor 24 -> Model Lift -> Floor 27, Floor 23, or Roof

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/model_infrastructure_status.sh
./scripts/sync_ollama_inventory.sh
python3 scripts/route_model_request.py coding
"""
if "Model Infrastructure V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Model Infrastructure V1.1 repaired and installed.")
