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

print("Installing Floor 21 Adapter Systems Department V1.1...")

for folder in [
    "floors/floor_21_adapter_systems_department/adapter_sockets",
    "floors/floor_21_adapter_systems_department/adapter_health",
    "floors/floor_21_adapter_systems_department/adapter_capabilities",
    "floors/floor_21_adapter_systems_department/handoff_paths",
    "floors/floor_21_adapter_systems_department/future_bridges",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower",
    "src/dashboard"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

adapter_sockets = [
    {
        "id": "claude_adapter_socket",
        "adapter": "claude_adapter",
        "display_name": "Claude Adapter Socket",
        "floor_id": "floor_21",
        "target_provider": "claude",
        "target_floor": "floor_23",
        "adapter_type": "external_provider_adapter",
        "status": "socket_ready_not_connected",
        "execution_enabled": False,
        "hardwired": False,
        "notes": "Neutral adapter socket for future Claude connection. No Claude call is executed."
    },
    {
        "id": "claude_code_adapter_socket",
        "adapter": "claude_code_adapter",
        "display_name": "Claude Code Adapter Socket",
        "floor_id": "floor_21",
        "target_provider": "claude",
        "target_floor": "floor_05",
        "adapter_type": "coding_tool_adapter",
        "status": "socket_ready_not_connected",
        "execution_enabled": False,
        "hardwired": False,
        "notes": "Future Claude Code bridge. Floor 5 remains the coding workspace."
    },
    {
        "id": "ollama_adapter_socket",
        "adapter": "ollama_adapter",
        "display_name": "Ollama Adapter Socket",
        "floor_id": "floor_21",
        "target_provider": "ollama",
        "target_floor": "floor_27",
        "adapter_type": "local_model_adapter",
        "status": "socket_ready_optional",
        "execution_enabled": False,
        "hardwired": False,
        "notes": "Ollama may exist locally, but the tower must run without it."
    },
    {
        "id": "openai_adapter_socket",
        "adapter": "openai_adapter",
        "display_name": "OpenAI Adapter Socket",
        "floor_id": "floor_21",
        "target_provider": "openai",
        "target_floor": "floor_23",
        "adapter_type": "external_provider_adapter",
        "status": "socket_ready_not_connected",
        "execution_enabled": False,
        "hardwired": False,
        "notes": "Neutral adapter socket. No OpenAI call is executed."
    },
    {
        "id": "gemini_adapter_socket",
        "adapter": "gemini_adapter",
        "display_name": "Gemini Adapter Socket",
        "floor_id": "floor_21",
        "target_provider": "gemini",
        "target_floor": "floor_23",
        "adapter_type": "external_provider_adapter",
        "status": "socket_ready_not_connected",
        "execution_enabled": False,
        "hardwired": False,
        "notes": "Neutral adapter socket. No Gemini call is executed."
    },
    {
        "id": "deepseek_adapter_socket",
        "adapter": "deepseek_adapter",
        "display_name": "DeepSeek Adapter Socket",
        "floor_id": "floor_21",
        "target_provider": "deepseek",
        "target_floor": "floor_23",
        "adapter_type": "external_provider_adapter",
        "status": "socket_ready_not_connected",
        "execution_enabled": False,
        "hardwired": False,
        "notes": "Neutral adapter socket. No DeepSeek call is executed."
    },
    {
        "id": "local_cli_adapter_socket",
        "adapter": "local_cli_adapter",
        "display_name": "Local CLI Adapter Socket",
        "floor_id": "floor_21",
        "target_provider": "local_cli",
        "target_floor": "floor_35",
        "adapter_type": "local_command_adapter",
        "status": "socket_ready_disabled",
        "execution_enabled": False,
        "hardwired": False,
        "notes": "Future local command bridge. Execution remains disabled."
    },
    {
        "id": "filesystem_adapter_socket",
        "adapter": "filesystem_adapter",
        "display_name": "Filesystem Adapter Socket",
        "floor_id": "floor_21",
        "target_provider": "filesystem",
        "target_floor": "floor_35",
        "adapter_type": "local_filesystem_adapter",
        "status": "socket_ready_disabled",
        "execution_enabled": False,
        "hardwired": False,
        "notes": "Future file-operation bridge. Execution remains disabled."
    },
    {
        "id": "future_adapter_socket",
        "adapter": "future_adapter",
        "display_name": "Future Adapter Socket",
        "floor_id": "floor_21",
        "target_provider": "future_provider",
        "target_floor": "floor_23",
        "adapter_type": "future_adapter",
        "status": "expansion_ready",
        "execution_enabled": False,
        "hardwired": False,
        "notes": "Expansion-ready adapter pattern for future tools/providers."
    }
]

adapter_capabilities = [
    {
        "adapter": "claude_adapter",
        "socket_id": "claude_adapter_socket",
        "capabilities": ["external_provider_bridge", "reasoning_handoff", "coding_handoff", "analysis_handoff"],
        "execution_enabled": False
    },
    {
        "adapter": "claude_code_adapter",
        "socket_id": "claude_code_adapter_socket",
        "capabilities": ["coding_workspace_handoff", "patch_handoff", "review_handoff"],
        "execution_enabled": False
    },
    {
        "adapter": "ollama_adapter",
        "socket_id": "ollama_adapter_socket",
        "capabilities": ["local_model_inventory", "future_local_inference_bridge"],
        "execution_enabled": False
    },
    {
        "adapter": "openai_adapter",
        "socket_id": "openai_adapter_socket",
        "capabilities": ["external_provider_bridge", "future_tool_use_bridge", "vision_handoff"],
        "execution_enabled": False
    },
    {
        "adapter": "gemini_adapter",
        "socket_id": "gemini_adapter_socket",
        "capabilities": ["external_provider_bridge", "vision_handoff", "long_context_handoff"],
        "execution_enabled": False
    },
    {
        "adapter": "deepseek_adapter",
        "socket_id": "deepseek_adapter_socket",
        "capabilities": ["external_provider_bridge", "coding_handoff", "reasoning_handoff"],
        "execution_enabled": False
    },
    {
        "adapter": "local_cli_adapter",
        "socket_id": "local_cli_adapter_socket",
        "capabilities": ["future_local_command_bridge"],
        "execution_enabled": False
    },
    {
        "adapter": "filesystem_adapter",
        "socket_id": "filesystem_adapter_socket",
        "capabilities": ["future_file_bridge", "future_project_workspace_bridge"],
        "execution_enabled": False
    },
    {
        "adapter": "future_adapter",
        "socket_id": "future_adapter_socket",
        "capabilities": ["expansion_ready"],
        "execution_enabled": False
    }
]

adapter_handoff_paths = [
    {
        "id": "floor_24_to_floor_21_to_floor_27_local_model",
        "source_floor": "floor_24",
        "adapter_floor": "floor_21",
        "target_floor": "floor_27",
        "adapter": "ollama_adapter",
        "incoming_lift": "service_lift",
        "outgoing_lift": "model_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "description": "Future route where Floor 24 asks Floor 21 to prepare Ollama/local-model adapter handoff."
    },
    {
        "id": "floor_24_to_floor_21_to_floor_23_external_provider",
        "source_floor": "floor_24",
        "adapter_floor": "floor_21",
        "target_floor": "floor_23",
        "adapter": "claude_adapter",
        "incoming_lift": "service_lift",
        "outgoing_lift": "model_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "description": "Future route where Floor 21 prepares external provider adapter handoff before Floor 23 socket layer."
    },
    {
        "id": "floor_05_to_floor_21_claude_code_port",
        "source_floor": "floor_05",
        "adapter_floor": "floor_21",
        "target_floor": "floor_24",
        "adapter": "claude_code_adapter",
        "incoming_lift": "service_lift",
        "outgoing_lift": "service_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "description": "Future route where Floor 5 coding packets can be adapter-prepared before Floor 24 routing."
    },
    {
        "id": "floor_35_to_floor_21_local_cli_bridge",
        "source_floor": "floor_35",
        "adapter_floor": "floor_21",
        "target_floor": "floor_35",
        "adapter": "local_cli_adapter",
        "incoming_lift": "service_lift",
        "outgoing_lift": "service_lift",
        "sealed_packets": True,
        "execution_enabled": False,
        "description": "Future local CLI bridge. Disabled until explicitly enabled later."
    }
]

adapter_policy = {
    "version": "1.1",
    "floor_id": "floor_21",
    "department": "Adapter Systems Department",
    "role": "neutral_adapter_socket_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_adapters": False,
    "providers_are_external": True,
    "receives_from": ["floor_24", "floor_05", "floor_35"],
    "hands_off_to": ["floor_23", "floor_27", "floor_35"],
    "notice": "Floor 21 registers adapter sockets and future bridge paths. It does not execute adapters or providers."
}

write_json("data/registries/adapter_sockets.json", adapter_sockets)
write_json("data/registries/adapter_capabilities.json", adapter_capabilities)
write_json("data/registries/adapter_handoff_paths.json", adapter_handoff_paths)
write_json("data/registries/adapter_policy.json", adapter_policy)

write_json("floors/floor_21_adapter_systems_department/floor_manifest.json", {
    "floor_id": "floor_21",
    "department": "Adapter Systems Department",
    "version": "1.1",
    "role": "neutral_adapter_socket_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_adapters": False,
    "providers_are_external": True,
    "adapter_count": len(adapter_sockets),
    "notice": "Floor 21 owns adapter sockets, health records, capability records, and future handoff paths only."
})

write_json("floors/floor_21_adapter_systems_department/adapter_sockets/manifest.json", {
    "floor_id": "floor_21",
    "socket_count": len(adapter_sockets),
    "sockets": adapter_sockets,
    "execution_enabled": False,
    "hardwired": False
})

write_json("floors/floor_21_adapter_systems_department/adapter_capabilities/capabilities.json", adapter_capabilities)
write_json("floors/floor_21_adapter_systems_department/handoff_paths/handoff_paths.json", adapter_handoff_paths)

write("config/adapter_systems_department.yaml", """
adapter_systems_department:
  version: 1.1
  floor_id: floor_21
  role: neutral_adapter_socket_layer
  execution_enabled: false
  hardwired_adapters: false
  models_required: false
  kernel_required: false
  providers_are_external: true

principle: Floor 21 owns adapter sockets and bridge records only. It does not execute providers, tools, CLI commands, or file operations.
""")

write("src/tower/adapter_systems.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "adapter_systems.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS adapter_health (
    adapter TEXT PRIMARY KEY,
    socket_id TEXT,
    display_name TEXT,
    adapter_type TEXT,
    target_provider TEXT,
    target_floor TEXT,
    status TEXT,
    execution_enabled INTEGER,
    hardwired INTEGER,
    last_checked_ts TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS adapter_capabilities (
    adapter TEXT PRIMARY KEY,
    socket_id TEXT,
    capabilities_json TEXT,
    execution_enabled INTEGER
);

CREATE TABLE IF NOT EXISTS adapter_handoff_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    adapter TEXT,
    source_floor TEXT,
    target_floor TEXT,
    socket_id TEXT,
    status TEXT,
    details TEXT
);
"""

class AdapterSystems:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.sync()

    def sockets(self):
        return load_json("adapter_sockets.json", [])

    def capability_registry(self):
        return load_json("adapter_capabilities.json", [])

    def handoff_paths(self):
        return load_json("adapter_handoff_paths.json", [])

    def policy(self):
        return load_json("adapter_policy.json", {})

    def sync(self):
        for s in self.sockets():
            self.conn.execute(
                """
                INSERT OR REPLACE INTO adapter_health
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s["adapter"],
                    s["id"],
                    s["display_name"],
                    s["adapter_type"],
                    s["target_provider"],
                    s["target_floor"],
                    s["status"],
                    int(bool(s.get("execution_enabled", False))),
                    int(bool(s.get("hardwired", False))),
                    now(),
                    s.get("notes", "Adapter socket registered. Execution disabled.")
                )
            )

        for c in self.capability_registry():
            self.conn.execute(
                "INSERT OR REPLACE INTO adapter_capabilities VALUES (?, ?, ?, ?)",
                (
                    c["adapter"],
                    c["socket_id"],
                    json.dumps(c.get("capabilities", [])),
                    int(bool(c.get("execution_enabled", False)))
                )
            )

        self.conn.commit()

    def health(self):
        rows = self.conn.execute("SELECT * FROM adapter_health ORDER BY adapter").fetchall()
        return [dict(r) for r in rows]

    def capabilities(self):
        rows = self.conn.execute("SELECT * FROM adapter_capabilities ORDER BY adapter").fetchall()
        output = []
        for r in rows:
            item = dict(r)
            item["capabilities"] = json.loads(item.pop("capabilities_json"))
            output.append(item)
        return output

    def refresh_health(self):
        self.sync()
        results = []
        for h in self.health():
            if h["adapter"] == "future_adapter":
                status = "expansion_ready"
            elif "local" in h["adapter"] or "filesystem" in h["adapter"]:
                status = "socket_ready_disabled"
            else:
                status = "socket_ready_not_connected"

            self.conn.execute(
                "UPDATE adapter_health SET status=?, last_checked_ts=?, notes=? WHERE adapter=?",
                (status, now(), "Health simulated. No adapter execution performed.", h["adapter"])
            )

            results.append({
                "adapter": h["adapter"],
                "status": status,
                "execution_performed": False
            })

        self.conn.commit()
        return results

    def prepare_handoff(self, adapter, source_floor="floor_24", target_floor=None, details=None):
        details = details or {}
        socket_id = None
        target = target_floor

        for s in self.sockets():
            if s["adapter"] == adapter:
                socket_id = s["id"]
                if target is None:
                    target = s["target_floor"]
                break

        status = "prepared_not_executed"

        self.conn.execute(
            """
            INSERT INTO adapter_handoff_events
            (ts, adapter, source_floor, target_floor, socket_id, status, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now(), adapter, source_floor, target or "unknown", socket_id, status, json.dumps(details))
        )
        self.conn.commit()

        return {
            "adapter": adapter,
            "source_floor": source_floor,
            "target_floor": target,
            "socket_id": socket_id,
            "status": status,
            "execution_enabled": False
        }

    def recent_handoffs(self, limit=20):
        rows = self.conn.execute("SELECT * FROM adapter_handoff_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        self.sync()
        policy = self.policy()
        health = self.health()
        caps = self.capabilities()

        return {
            "database": str(DB),
            "floor": "floor_21",
            "department": "Adapter Systems Department",
            "version": "1.1",
            "role": "neutral_adapter_socket_layer",
            "execution_enabled": False,
            "hardwired_adapters": False,
            "models_required": False,
            "kernel_required": False,
            "providers_are_external": True,
            "adapter_count": len(health),
            "capability_records": len(caps),
            "handoff_paths": self.handoff_paths(),
            "health": health,
            "capabilities": caps,
            "recent_handoffs": self.recent_handoffs(10),
            "policy": policy
        }

if __name__ == "__main__":
    print(json.dumps(AdapterSystems().dashboard(), indent=2))
''')

write("scripts/adapter_systems_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.adapter_systems
""")

write("scripts/refresh_adapter_health.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.adapter_systems import AdapterSystems
import json
dept = AdapterSystems()
print(json.dumps(dept.refresh_health(), indent=2))
PY2
""")

write("scripts/prepare_adapter_handoff.py", """
import sys
import json
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.adapter_systems import AdapterSystems

adapter = sys.argv[1] if len(sys.argv) > 1 else 'claude_adapter'
dept = AdapterSystems()
print(json.dumps(dept.prepare_handoff(adapter, details={'manual_test': True}), indent=2))
""")

for script in [
    "scripts/adapter_systems_status.sh",
    "scripts/refresh_adapter_health.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_adapter_systems_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.adapter_systems import AdapterSystems

dept = AdapterSystems()
dash = dept.dashboard()

assert dash['floor'] == 'floor_21'
assert dash['department'] == 'Adapter Systems Department'
assert dash['execution_enabled'] is False
assert dash['hardwired_adapters'] is False
assert dash['models_required'] is False
assert dash['kernel_required'] is False
assert dash['providers_are_external'] is True
assert dash['adapter_count'] >= 8
assert dash['capability_records'] >= 8

handoff = dept.prepare_handoff('claude_adapter', source_floor='floor_24', details={'test': 'validation'})
assert handoff['adapter'] == 'claude_adapter'
assert handoff['status'] == 'prepared_not_executed'
assert handoff['execution_enabled'] is False

print('ADAPTER SYSTEMS V1.1 VALIDATION PASSED')
print('Adapters:', dash['adapter_count'])
print('Capability records:', dash['capability_records'])
""")

# Dashboard update including Floor 21.
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
from tower.adapter_systems import AdapterSystems

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
.air{background:#18385f;border:1px solid #9ac7ff}
.model{background:#143d5a;border:1px solid #50bfff}
.coding{background:#17365a;border:1px solid #7fb7ff}
.routing{background:#174a5a;border:1px solid #78e5ff}
.localmodel{background:#163f46;border:1px solid #6fffe0}
pre{background:#050c16;padding:10px;border-radius:8px;max-height:220px;overflow:auto}
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

  adapters.textContent = JSON.stringify({
    floor:a.floor,
    department:a.department,
    execution_enabled:a.execution_enabled,
    hardwired_adapters:a.hardwired_adapters,
    providers_are_external:a.providers_are_external,
    adapter_count:a.adapter_count,
    capability_records:a.capability_records,
    recent_handoffs:a.recent_handoffs,
    health:a.health
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

        if self.path.startswith("/api/adapter_systems"):
            return self.send_json(AdapterSystems().dashboard())

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
Adapter Systems Department V1.1

Floor 21 is now a neutral adapter socket layer.

It includes:
- Claude adapter socket
- Claude Code adapter socket
- Ollama adapter socket
- OpenAI adapter socket
- Gemini adapter socket
- DeepSeek adapter socket
- Local CLI adapter socket
- Filesystem adapter socket
- Future adapter socket
- Adapter health records
- Adapter capability registry
- Future handoff paths
- Dashboard panel

Floor 21 does not execute providers, CLI commands, or filesystem operations.
It only prepares neutral adapter sockets and bridge records.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/refresh_adapter_health.sh
./scripts/adapter_systems_status.sh
python3 scripts/prepare_adapter_handoff.py claude_adapter
python3 tests/test_adapter_systems_v11.py
"""

if "Adapter Systems Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Floor 21 Adapter Systems Department V1.1 installed.")
print("Run:")
print("./scripts/refresh_adapter_health.sh")
print("./scripts/adapter_systems_status.sh")
