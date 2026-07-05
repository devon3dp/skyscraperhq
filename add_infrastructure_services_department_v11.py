from pathlib import Path
from datetime import datetime, UTC
import json
import os
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

print("Installing Floor 35 Infrastructure Services Department V1.1...")

for folder in [
    "floors/floor_35_infrastructure_services_department/service_registry",
    "floors/floor_35_infrastructure_services_department/script_registry",
    "floors/floor_35_infrastructure_services_department/runtime_checks",
    "floors/floor_35_infrastructure_services_department/database_checks",
    "floors/floor_35_infrastructure_services_department/log_checks",
    "floors/floor_35_infrastructure_services_department/backup_readiness",
    "floors/floor_35_infrastructure_services_department/repair_hooks",
    "floors/floor_35_infrastructure_services_department/maintenance_hooks",
    "floors/floor_35_infrastructure_services_department/service_control",
    "data/registries",
    "data/db",
    "data/backups",
    "scripts",
    "tests",
    "src/tower",
    "src/dashboard"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

infrastructure_policy = {
    "version": "1.1",
    "floor_id": "floor_35",
    "department": "Infrastructure Services Department",
    "role": "building_operations_and_maintenance_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "principle": "Floor 35 maintains operational records and readiness checks. It does not execute repair hooks, provider calls, model calls, CLI commands, or kernel logic.",
    "notice": "Infrastructure services are inspection and readiness services only until explicitly activated later."
}

service_registry = [
    {"id": "dashboard_service", "name": "Dashboard Service", "type": "local_http_service", "pid_file": "data/runtime/dashboard.pid", "start_script": "run.sh", "stop_script": "stop.sh", "status_script": "status.sh", "execution_enabled": False},
    {"id": "registry_service", "name": "Registry Service", "type": "file_registry", "root": "data/registries", "execution_enabled": False},
    {"id": "database_service", "name": "SQLite Database Service", "type": "sqlite_files", "root": "data/db", "execution_enabled": False},
    {"id": "packet_service", "name": "Sealed Packet Store", "type": "sqlite_packet_records", "root": "data/packets", "execution_enabled": False},
    {"id": "runtime_service", "name": "Runtime State Service", "type": "runtime_files", "root": "data/runtime", "execution_enabled": False},
    {"id": "log_service", "name": "Log Service", "type": "local_logs", "root": "data/logs", "execution_enabled": False},
    {"id": "backup_service", "name": "Backup Readiness Service", "type": "readiness_only", "root": "data/backups", "execution_enabled": False}
]

script_registry = [
    {"id": "setup_script", "path": "setup.sh", "purpose": "Initial tower installation", "required": False, "execution_enabled": False},
    {"id": "run_script", "path": "run.sh", "purpose": "Start dashboard service", "required": True, "execution_enabled": False},
    {"id": "stop_script", "path": "stop.sh", "purpose": "Stop dashboard service", "required": True, "execution_enabled": False},
    {"id": "restart_script", "path": "restart.sh", "purpose": "Restart dashboard service", "required": True, "execution_enabled": False},
    {"id": "status_script", "path": "status.sh", "purpose": "Check dashboard service status", "required": True, "execution_enabled": False},
    {"id": "diagnostics_script", "path": "scripts/run_floor_33_diagnostics.sh", "purpose": "Run Floor 33 diagnostics", "required": True, "execution_enabled": False},
    {"id": "monitoring_script", "path": "scripts/run_floor_34_monitoring.sh", "purpose": "Run Floor 34 monitoring snapshot", "required": True, "execution_enabled": False}
]

repair_hooks = [
    {"id": "repair_lift_network", "name": "Lift Network Repair Hook", "target": "src/tower/lifts.py", "status": "registered_not_executable", "execution_enabled": False},
    {"id": "repair_monitoring", "name": "Monitoring Repair Hook", "target": "src/tower/monitoring_department.py", "status": "registered_not_executable", "execution_enabled": False},
    {"id": "repair_dashboard", "name": "Dashboard Repair Hook", "target": "src/dashboard/server.py", "status": "registered_not_executable", "execution_enabled": False},
    {"id": "repair_registries", "name": "Registry Repair Hook", "target": "data/registries", "status": "registered_not_executable", "execution_enabled": False}
]

maintenance_hooks = [
    {"id": "maintenance_database_check", "name": "Database File Check", "status": "registered_not_executable", "execution_enabled": False},
    {"id": "maintenance_log_rotation_ready", "name": "Log Rotation Readiness", "status": "registered_not_executable", "execution_enabled": False},
    {"id": "maintenance_backup_ready", "name": "Backup Readiness", "status": "registered_not_executable", "execution_enabled": False},
    {"id": "maintenance_runtime_cleanup_ready", "name": "Runtime Cleanup Readiness", "status": "registered_not_executable", "execution_enabled": False}
]

write_json("data/registries/infrastructure_policy.json", infrastructure_policy)
write_json("data/registries/infrastructure_service_registry.json", service_registry)
write_json("data/registries/infrastructure_script_registry.json", script_registry)
write_json("data/registries/infrastructure_repair_hooks.json", repair_hooks)
write_json("data/registries/infrastructure_maintenance_hooks.json", maintenance_hooks)

write_json("floors/floor_35_infrastructure_services_department/floor_manifest.json", {
    "floor_id": "floor_35",
    "department": "Infrastructure Services Department",
    "version": "1.1",
    "role": "building_operations_and_maintenance_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "service_records": len(service_registry),
    "script_records": len(script_registry),
    "repair_hooks": len(repair_hooks),
    "maintenance_hooks": len(maintenance_hooks),
    "notice": "Floor 35 records infrastructure health, readiness, service control, scripts, backups, repair hooks, and maintenance hooks."
})

write_json("floors/floor_35_infrastructure_services_department/service_registry/services.json", service_registry)
write_json("floors/floor_35_infrastructure_services_department/script_registry/scripts.json", script_registry)
write_json("floors/floor_35_infrastructure_services_department/repair_hooks/repair_hooks.json", repair_hooks)
write_json("floors/floor_35_infrastructure_services_department/maintenance_hooks/maintenance_hooks.json", maintenance_hooks)

write("config/infrastructure_services_department.yaml", """
infrastructure_services_department:
  version: 1.1
  floor_id: floor_35
  role: building_operations_and_maintenance_layer
  execution_enabled: false
  hardwired_providers: false
  models_required: false
  kernel_required: false
  providers_are_external: true

principle: Floor 35 records and checks infrastructure readiness. It does not execute repair hooks, providers, adapters, models, CLI commands, or kernel logic.

watch_scope:
  - startup shutdown scripts
  - runtime files
  - sqlite databases
  - log directories
  - backup readiness
  - repair hook registry
  - maintenance hook registry
  - service-control visibility
""")

write("src/tower/infrastructure_services.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import os
import sqlite3
import shutil

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "infrastructure_services.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS infrastructure_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    check_type TEXT,
    name TEXT,
    status TEXT,
    severity TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS service_control_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    service_id TEXT,
    action TEXT,
    status TEXT,
    execution_enabled INTEGER,
    details TEXT
);
"""

class InfrastructureServices:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policy(self):
        return load_json("infrastructure_policy.json", {})

    def service_registry(self):
        return load_json("infrastructure_service_registry.json", [])

    def script_registry(self):
        return load_json("infrastructure_script_registry.json", [])

    def repair_hooks(self):
        return load_json("infrastructure_repair_hooks.json", [])

    def maintenance_hooks(self):
        return load_json("infrastructure_maintenance_hooks.json", [])

    def record_check(self, check_type, name, status, severity, details):
        self.conn.execute(
            "INSERT INTO infrastructure_checks(ts, check_type, name, status, severity, details) VALUES (?, ?, ?, ?, ?, ?)",
            (now(), check_type, name, status, severity, json.dumps(details))
        )
        self.conn.commit()

    def script_checks(self):
        results = []
        for script in self.script_registry():
            path = ROOT / script["path"]
            exists = path.exists()
            executable = os.access(path, os.X_OK) if exists else False
            required = bool(script.get("required", False))

            status = "pass" if exists and (executable or path.suffix == ".py") else "missing" if not exists else "not_executable"
            severity = "critical" if required and status != "pass" else "warning" if status != "pass" else "info"

            result = {
                "id": script["id"],
                "path": script["path"],
                "purpose": script.get("purpose"),
                "required": required,
                "exists": exists,
                "executable": executable,
                "execution_enabled": False,
                "status": status,
                "severity": severity
            }
            results.append(result)
            self.record_check("script", script["id"], status, severity, result)
        return results

    def runtime_checks(self):
        checks = []
        runtime = ROOT / "data" / "runtime"
        pid_file = runtime / "dashboard.pid"

        checks.append({
            "name": "runtime_directory",
            "path": str(runtime),
            "exists": runtime.exists(),
            "status": "pass" if runtime.exists() else "missing"
        })

        pid_exists = pid_file.exists()
        pid_value = None
        pid_running = False

        if pid_exists:
            try:
                pid_value = int(pid_file.read_text(encoding="utf-8").strip())
                os.kill(pid_value, 0)
                pid_running = True
            except Exception:
                pid_running = False

        checks.append({
            "name": "dashboard_pid",
            "path": str(pid_file),
            "exists": pid_exists,
            "pid": pid_value,
            "running": pid_running,
            "status": "pass" if pid_exists and pid_running else "degraded"
        })

        for check in checks:
            self.record_check("runtime", check["name"], check["status"], "warning" if check["status"] != "pass" else "info", check)

        return checks

    def database_checks(self):
        db_dir = ROOT / "data" / "db"
        dbs = sorted(db_dir.glob("*.sqlite")) if db_dir.exists() else []

        results = {
            "database_directory": {
                "path": str(db_dir),
                "exists": db_dir.exists(),
                "status": "pass" if db_dir.exists() else "missing"
            },
            "sqlite_files": []
        }

        for db in dbs:
            item = {
                "name": db.name,
                "path": str(db.relative_to(ROOT)),
                "size_bytes": db.stat().st_size,
                "status": "pass" if db.stat().st_size >= 0 else "degraded"
            }
            results["sqlite_files"].append(item)

        status = "pass" if db_dir.exists() else "missing"
        self.record_check("database", "sqlite_database_directory", status, "critical" if status != "pass" else "info", results)
        return results

    def log_checks(self):
        log_dir = ROOT / "data" / "logs"
        logs = sorted(log_dir.glob("*")) if log_dir.exists() else []
        result = {
            "log_directory": str(log_dir),
            "exists": log_dir.exists(),
            "log_files": [str(p.relative_to(ROOT)) for p in logs if p.is_file()],
            "status": "pass" if log_dir.exists() else "missing"
        }
        self.record_check("logs", "log_directory", result["status"], "warning" if result["status"] != "pass" else "info", result)
        return result

    def backup_readiness(self):
        backup_dir = ROOT / "data" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        usage = shutil.disk_usage(str(ROOT))
        result = {
            "backup_directory": str(backup_dir),
            "exists": backup_dir.exists(),
            "tower_free_gb": round(usage.free / (1024 ** 3), 2),
            "ready": backup_dir.exists() and usage.free > 1024 * 1024 * 1024,
            "execution_enabled": False,
            "status": "ready" if backup_dir.exists() and usage.free > 1024 * 1024 * 1024 else "degraded"
        }
        self.record_check("backup", "backup_readiness", result["status"], "warning" if result["status"] != "ready" else "info", result)
        return result

    def hook_checks(self):
        repairs = self.repair_hooks()
        maintenance = self.maintenance_hooks()

        result = {
            "repair_hooks": repairs,
            "maintenance_hooks": maintenance,
            "repair_count": len(repairs),
            "maintenance_count": len(maintenance),
            "execution_enabled": False,
            "status": "registered"
        }
        self.record_check("hooks", "repair_and_maintenance_hooks", "registered", "info", result)
        return result

    def service_control_status(self):
        controls = []
        for service in self.service_registry():
            status = "registered"
            details = {
                "service": service,
                "execution_enabled": False,
                "action_allowed": False,
                "message": "Service control is visible but disabled until explicitly enabled later."
            }
            controls.append(details)
            self.conn.execute(
                "INSERT INTO service_control_records(ts, service_id, action, status, execution_enabled, details) VALUES (?, ?, ?, ?, ?, ?)",
                (now(), service["id"], "visibility_check", status, 0, json.dumps(details))
            )
        self.conn.commit()
        return controls

    def collect_status(self):
        script_results = self.script_checks()
        runtime = self.runtime_checks()
        dbs = self.database_checks()
        logs = self.log_checks()
        backup = self.backup_readiness()
        hooks = self.hook_checks()
        controls = self.service_control_status()

        critical_issues = []
        warnings = []

        for item in script_results:
            if item["severity"] == "critical" and item["status"] != "pass":
                critical_issues.append(f"script {item['path']} {item['status']}")
            elif item["status"] != "pass":
                warnings.append(f"script {item['path']} {item['status']}")

        if dbs["database_directory"]["status"] != "pass":
            critical_issues.append("database directory missing")

        if logs["status"] != "pass":
            warnings.append("log directory missing")

        if backup["status"] != "ready":
            warnings.append("backup readiness degraded")

        status = "healthy" if not critical_issues and not warnings else "degraded" if not critical_issues else "critical"

        snapshot = {
            "ts": now(),
            "floor": "floor_35",
            "department": "Infrastructure Services Department",
            "version": "1.1",
            "status": status,
            "execution_enabled": False,
            "kernel_required": False,
            "models_required": False,
            "critical_issues": critical_issues,
            "warnings": warnings,
            "script_checks": script_results,
            "runtime_checks": runtime,
            "database_checks": dbs,
            "log_checks": logs,
            "backup_readiness": backup,
            "hook_checks": hooks,
            "service_control": controls
        }

        out_path = ROOT / "floors" / "floor_35_infrastructure_services_department" / "service_control" / "latest_status.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

        return snapshot

    def recent_checks(self, limit=30):
        rows = self.conn.execute("SELECT * FROM infrastructure_checks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def recent_service_control(self, limit=20):
        rows = self.conn.execute("SELECT * FROM service_control_records ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        snap = self.collect_status()
        return {
            "database": str(DB),
            "floor": "floor_35",
            "department": "Infrastructure Services Department",
            "version": "1.1",
            "role": "building_operations_and_maintenance_layer",
            "infrastructure_status": snap["status"],
            "execution_enabled": False,
            "kernel_required": False,
            "models_required": False,
            "service_records": len(self.service_registry()),
            "script_records": len(self.script_registry()),
            "repair_hooks": len(self.repair_hooks()),
            "maintenance_hooks": len(self.maintenance_hooks()),
            "runtime_checks": snap["runtime_checks"],
            "database_count": len(snap["database_checks"]["sqlite_files"]),
            "backup_ready": snap["backup_readiness"]["ready"],
            "critical_issues": snap["critical_issues"],
            "warnings": snap["warnings"],
            "latest_status": "floors/floor_35_infrastructure_services_department/service_control/latest_status.json",
            "recent_checks": self.recent_checks(10),
            "recent_service_control": self.recent_service_control(10),
            "policy": self.policy()
        }

if __name__ == "__main__":
    print(json.dumps(InfrastructureServices().dashboard(), indent=2))
''')

write("scripts/infrastructure_services_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.infrastructure_services
""")

write("scripts/run_floor_35_infrastructure.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.infrastructure_services import InfrastructureServices
import json
dept = InfrastructureServices()
snap = dept.collect_status()
print(json.dumps({
    "status": snap["status"],
    "critical_issues": snap["critical_issues"],
    "warnings": snap["warnings"],
    "script_checks": len(snap["script_checks"]),
    "database_files": len(snap["database_checks"]["sqlite_files"]),
    "backup_ready": snap["backup_readiness"]["ready"],
    "repair_hooks": snap["hook_checks"]["repair_count"],
    "maintenance_hooks": snap["hook_checks"]["maintenance_count"]
}, indent=2))
print("Status written to: floors/floor_35_infrastructure_services_department/service_control/latest_status.json")
PY2
""")

for script in [
    "scripts/infrastructure_services_status.sh",
    "scripts/run_floor_35_infrastructure.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_infrastructure_services_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.infrastructure_services import InfrastructureServices

dept = InfrastructureServices()
snap = dept.collect_status()

assert snap['floor'] == 'floor_35'
assert snap['department'] == 'Infrastructure Services Department'
assert snap['execution_enabled'] is False
assert snap['kernel_required'] is False
assert snap['models_required'] is False
assert len(snap['script_checks']) >= 5
assert len(snap['database_checks']['sqlite_files']) >= 1
assert snap['hook_checks']['repair_count'] >= 4
assert snap['hook_checks']['maintenance_count'] >= 4

dash = dept.dashboard()
assert dash['floor'] == 'floor_35'
assert dash['execution_enabled'] is False
assert dash['latest_status'].endswith('latest_status.json')

print('INFRASTRUCTURE SERVICES V1.1 VALIDATION PASSED')
print('Status:', snap['status'])
print('Critical issues:', snap['critical_issues'])
print('Warnings:', snap['warnings'])
print('Database files:', len(snap['database_checks']['sqlite_files']))
print('Backup ready:', snap['backup_readiness']['ready'])
""")

write("src/dashboard/server.py", r'''
import sys
import json
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

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
from tower.diagnostics_department import DiagnosticsDepartment
from tower.monitoring_department import MonitoringDepartment
from tower.infrastructure_services import InfrastructureServices

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
.diagnostics{background:#3c285f;border:1px solid #f5a3ff}
.monitoring{background:#1b4d35;border:1px solid #95ffb5}
.infrastructure{background:#3d3b1b;border:1px solid #fff095}
.air{background:#18385f;border:1px solid #9ac7ff}
.coding{background:#17365a;border:1px solid #7fb7ff}
.routing{background:#174a5a;border:1px solid #78e5ff}
.localmodel{background:#163f46;border:1px solid #6fffe0}
pre{background:#050c16;padding:10px;border-radius:8px;max-height:210px;overflow:auto}
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
<div class="panel"><h2>Floor 35 Infrastructure Services</h2><pre id="infrastructure_floor"></pre></div>
<div class="panel"><h2>Floor 34 Monitoring Department</h2><pre id="monitoring_floor"></pre></div>
<div class="panel"><h2>Floor 33 Diagnostics Department</h2><pre id="diagnostics_floor"></pre></div>
<div class="panel"><h2>Floor 22 Integration Services</h2><pre id="integration"></pre></div>
<div class="panel"><h2>Floor 21 Adapter Systems</h2><pre id="adapters"></pre></div>
<div class="panel"><h2>Floor 5 Coding Department</h2><pre id="coding"></pre></div>
<div class="panel"><h2>Floor 24 Model Routing Department</h2><pre id="routing"></pre></div>
<div class="panel"><h2>Floor 27 Local Model Operations</h2><pre id="localmodels"></pre></div>
<div class="panel"><h2>Floor 23 AIR LLM Operations</h2><pre id="airllm"></pre></div>
<div class="panel"><h2>Lift Network</h2><pre id="lifts"></pre></div>
<div class="panel"><h2>Packets</h2><pre id="packets"></pre></div>
</div>
</div>

<script>
function floorClass(f){
  if(f.id==="floor_21") return "adapter";
  if(f.id==="floor_22") return "integration";
  if(f.id==="floor_33") return "diagnostics";
  if(f.id==="floor_34") return "monitoring";
  if(f.id==="floor_35") return "infrastructure";
  if(f.id==="floor_23") return "air";
  if(f.id==="floor_24") return "routing";
  if(f.id==="floor_27") return "localmodel";
  if(f.id==="floor_05") return "coding";
  return f.status;
}

async function load(){
  let s = await (await fetch("/api/status")).json();
  let infra = await (await fetch("/api/infrastructure_services")).json();
  let mon = await (await fetch("/api/monitoring_department")).json();
  let d = await (await fetch("/api/diagnostics_department")).json();
  let i = await (await fetch("/api/integration_services")).json();
  let a = await (await fetch("/api/adapter_systems")).json();
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

  infrastructure_floor.textContent = JSON.stringify({
    floor:infra.floor,
    department:infra.department,
    infrastructure_status:infra.infrastructure_status,
    service_records:infra.service_records,
    script_records:infra.script_records,
    repair_hooks:infra.repair_hooks,
    maintenance_hooks:infra.maintenance_hooks,
    database_count:infra.database_count,
    backup_ready:infra.backup_ready,
    critical_issues:infra.critical_issues,
    warnings:infra.warnings,
    latest_status:infra.latest_status
  },null,2);

  monitoring_floor.textContent = JSON.stringify({
    floor:mon.floor,
    department:mon.department,
    monitoring_status:mon.monitoring_status,
    dashboard_online:mon.dashboard_online,
    service_uptime_seconds:mon.service_uptime_seconds,
    cpu_percent:mon.cpu_percent,
    memory_percent:mon.memory_percent,
    tower_free_gb:mon.tower_free_gb,
    diagnostics_status:mon.diagnostics_status
  },null,2);

  diagnostics_floor.textContent = JSON.stringify({
    floor:d.floor,
    department:d.department,
    diagnostic_status:d.diagnostic_status,
    checks_run:d.checks_run,
    critical_failures:d.critical_failures,
    warning_failures:d.warning_failures,
    passed:d.passed
  },null,2);

  integration.textContent = JSON.stringify({
    floor:i.floor,
    department:i.department,
    integration_health:i.integration_health,
    service_paths:i.service_paths,
    dependency_records:i.dependency_records
  },null,2);

  adapters.textContent = JSON.stringify({
    floor:a.floor,
    department:a.department,
    adapter_count:a.adapter_count,
    capability_records:a.capability_records,
    execution_enabled:a.execution_enabled
  },null,2);

  coding.textContent = JSON.stringify({
    floor:c.floor,
    department:c.department,
    requests:c.requests,
    patch_queue:c.patch_queue,
    review_queue:c.review_queue,
    test_queue:c.test_queue
  },null,2);

  routing.textContent = JSON.stringify({
    floor:r.floor,
    department:r.department,
    route_decisions:r.route_decisions,
    incoming_lift:r.incoming_lift,
    outgoing_lift:r.outgoing_lift
  },null,2);

  localmodels.textContent = JSON.stringify({
    floor:lm.floor,
    department:lm.department,
    detected_models:lm.detected_models,
    role_summary:lm.role_summary
  },null,2);

  airllm.textContent = JSON.stringify({
    floor:air.floor,
    department:air.department,
    provider_count:air.provider_count,
    socket_count:air.socket_count,
    execution_enabled:air.execution_enabled
  },null,2);

  lifts.textContent = JSON.stringify(s.lifts,null,2);
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

        if self.path.startswith("/api/infrastructure_services"):
            return self.send_json(InfrastructureServices().dashboard())
        if self.path.startswith("/api/monitoring_department"):
            return self.send_json(MonitoringDepartment().dashboard())
        if self.path.startswith("/api/diagnostics_department"):
            return self.send_json(DiagnosticsDepartment().dashboard())
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
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
''')

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Infrastructure Services Department V1.1

Floor 35 is now the building operations and maintenance layer.

It includes:
- Startup/shutdown service registry
- Script registry
- Runtime file checks
- SQLite database checks
- Log directory checks
- Backup readiness
- Repair hook registry
- Maintenance hook registry
- Service-control dashboard panel

Floor 35 does not execute repair hooks, providers, adapters, models, CLI commands, or kernel logic.
It only records readiness and infrastructure status.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_floor_35_infrastructure.sh
./scripts/infrastructure_services_status.sh
python3 tests/test_infrastructure_services_v11.py
"""

if "Infrastructure Services Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Floor 35 Infrastructure Services Department V1.1 installed.")
print("Run:")
print("./scripts/run_floor_35_infrastructure.sh")
print("./scripts/infrastructure_services_status.sh")
