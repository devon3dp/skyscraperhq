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

print("Installing Floor 33 Diagnostics Department V1.1...")

for folder in [
    "floors/floor_33_diagnostics_department/inspection_reports",
    "floors/floor_33_diagnostics_department/registry_validation",
    "floors/floor_33_diagnostics_department/lift_validation",
    "floors/floor_33_diagnostics_department/packet_validation",
    "floors/floor_33_diagnostics_department/import_validation",
    "floors/floor_33_diagnostics_department/dashboard_validation",
    "floors/floor_33_diagnostics_department/integration_validation",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower",
    "src/dashboard"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

diagnostics_policy = {
    "version": "1.1",
    "floor_id": "floor_33",
    "department": "Diagnostics Department",
    "role": "tower_engineering_inspection_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "inspection_scope": [
        "tower registry",
        "floor registry",
        "lift network",
        "packet integrity",
        "department imports",
        "dashboard endpoints",
        "model infrastructure",
        "adapter systems",
        "integration services",
        "local model inventory",
        "AIR LLM socket layer"
    ],
    "notice": "Floor 33 inspects the tower. It does not execute providers, adapters, tools, CLI commands, file operations, models, or kernel logic."
}

diagnostics_checks = [
    {"id": "module_registry", "category": "imports", "target": "tower.registry", "severity": "critical"},
    {"id": "module_database", "category": "imports", "target": "tower.database", "severity": "critical"},
    {"id": "module_lifts", "category": "imports", "target": "tower.lifts", "severity": "critical"},
    {"id": "module_model_infrastructure", "category": "imports", "target": "tower.model_infrastructure", "severity": "critical"},
    {"id": "module_coding_department", "category": "imports", "target": "tower.coding_department", "severity": "critical"},
    {"id": "module_adapter_systems", "category": "imports", "target": "tower.adapter_systems", "severity": "critical"},
    {"id": "module_integration_services", "category": "imports", "target": "tower.integration_services", "severity": "critical"},
    {"id": "module_model_routing", "category": "imports", "target": "tower.model_routing_department", "severity": "critical"},
    {"id": "module_local_models", "category": "imports", "target": "tower.local_model_operations", "severity": "critical"},
    {"id": "module_air_llm", "category": "imports", "target": "tower.air_llm_operations", "severity": "critical"},

    {"id": "registry_provider_sockets", "category": "registries", "target": "data/registries/provider_sockets.json", "severity": "critical"},
    {"id": "registry_model_paths", "category": "registries", "target": "data/registries/model_request_paths.json", "severity": "critical"},
    {"id": "registry_adapter_sockets", "category": "registries", "target": "data/registries/adapter_sockets.json", "severity": "critical"},
    {"id": "registry_integration_map", "category": "registries", "target": "data/registries/integration_service_map.json", "severity": "critical"},
    {"id": "registry_local_roles", "category": "registries", "target": "data/registries/local_model_roles.json", "severity": "warning"},
    {"id": "registry_external_providers", "category": "registries", "target": "data/registries/external_provider_capabilities.json", "severity": "warning"},

    {"id": "manifest_floor_05", "category": "floor_manifests", "target": "floors/floor_05_coding_department/floor_manifest.json", "severity": "critical"},
    {"id": "manifest_floor_21", "category": "floor_manifests", "target": "floors/floor_21_adapter_systems_department/floor_manifest.json", "severity": "critical"},
    {"id": "manifest_floor_22", "category": "floor_manifests", "target": "floors/floor_22_integration_services_department/floor_manifest.json", "severity": "critical"},
    {"id": "manifest_floor_23", "category": "floor_manifests", "target": "floors/floor_23_air_llm_operations_department/floor_manifest.json", "severity": "critical"},
    {"id": "manifest_floor_24", "category": "floor_manifests", "target": "floors/floor_24_model_routing_department/floor_manifest.json", "severity": "critical"},
    {"id": "manifest_floor_27", "category": "floor_manifests", "target": "floors/floor_27_local_model_operations_department/floor_manifest.json", "severity": "critical"},
    {"id": "manifest_floor_33", "category": "floor_manifests", "target": "floors/floor_33_diagnostics_department/floor_manifest.json", "severity": "critical"}
]

write_json("data/registries/diagnostics_policy.json", diagnostics_policy)
write_json("data/registries/diagnostics_checks.json", diagnostics_checks)

write_json("floors/floor_33_diagnostics_department/floor_manifest.json", {
    "floor_id": "floor_33",
    "department": "Diagnostics Department",
    "version": "1.1",
    "role": "tower_engineering_inspection_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "notice": "Floor 33 validates tower structure, registries, lifts, packets, imports, dashboard endpoints, and integration health."
})

write_json("floors/floor_33_diagnostics_department/registry_validation/diagnostics_checks.json", diagnostics_checks)

write("config/diagnostics_department.yaml", """
diagnostics_department:
  version: 1.1
  floor_id: floor_33
  role: tower_engineering_inspection_layer
  execution_enabled: false
  hardwired_providers: false
  models_required: false
  kernel_required: false
  providers_are_external: true

principle: Floor 33 inspects and reports. It does not execute providers, adapters, tools, CLI commands, file operations, models, or kernel logic.

inspection_scope:
  - tower registry
  - floor registry
  - lift network
  - packet integrity
  - department imports
  - dashboard endpoints
  - integration health
  - model infrastructure
  - adapter systems
  - local model inventory
  - AIR LLM socket layer
""")

write("src/tower/diagnostics_department.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import importlib
import json
import sqlite3
import urllib.request

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "diagnostics_department.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS diagnostic_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    status TEXT,
    critical_failures INTEGER,
    warning_failures INTEGER,
    checks_run INTEGER,
    summary_json TEXT
);

CREATE TABLE IF NOT EXISTS diagnostic_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    ts TEXT,
    category TEXT,
    name TEXT,
    status TEXT,
    severity TEXT,
    message TEXT,
    details_json TEXT
);
"""

class DiagnosticsDepartment:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policy(self):
        return load_json("diagnostics_policy.json", {})

    def checks_registry(self):
        return load_json("diagnostics_checks.json", [])

    def item(self, category, name, status, severity="info", message="", details=None):
        return {
            "category": category,
            "name": name,
            "status": status,
            "severity": severity,
            "message": message,
            "details": details or {}
        }

    def import_checks(self):
        output = []
        for check in self.checks_registry():
            if check.get("category") != "imports":
                continue
            module = check["target"]
            try:
                importlib.import_module(module)
                output.append(self.item("imports", module, "pass", check["severity"], "Module import passed."))
            except Exception as e:
                output.append(self.item("imports", module, "fail", check["severity"], str(e)))
        return output

    def file_and_registry_checks(self):
        output = []
        for check in self.checks_registry():
            if check.get("category") not in ["registries", "floor_manifests"]:
                continue

            path = ROOT / check["target"]
            if not path.exists():
                output.append(self.item(check["category"], check["target"], "fail", check["severity"], "Required file missing."))
                continue

            if path.suffix == ".json":
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    count = len(data) if isinstance(data, list) else len(data.keys()) if isinstance(data, dict) else 1
                    output.append(self.item(check["category"], check["target"], "pass", check["severity"], "JSON file valid.", {"records": count}))
                except Exception as e:
                    output.append(self.item(check["category"], check["target"], "fail", check["severity"], f"Invalid JSON: {e}"))
            else:
                output.append(self.item(check["category"], check["target"], "pass", check["severity"], "File exists."))

        return output

    def tower_registry_checks(self):
        output = []
        try:
            from tower.registry import Registry
            reg = Registry()

            floors = reg.floors()
            lifts = reg.lifts()
            workers = reg.workers()
            providers = reg.providers()

            output.append(self.item("tower_registry", "floor_count", "pass" if len(floors) == 53 else "fail", "critical", f"Floors registered: {len(floors)}", {"expected": 53, "actual": len(floors)}))
            vacant = [f for f in floors if f.get("vacant")]
            output.append(self.item("tower_registry", "vacant_floors", "pass" if len(vacant) == 5 else "fail", "warning", f"Vacant floors registered: {len(vacant)}", {"expected": 5, "actual": len(vacant)}))
            output.append(self.item("tower_registry", "lift_count", "pass" if len(lifts) >= 9 else "fail", "critical", f"Lifts registered: {len(lifts)}", {"actual": len(lifts)}))
            output.append(self.item("tower_registry", "worker_count", "pass" if len(workers) >= 40 else "fail", "warning", f"Workers registered: {len(workers)}", {"actual": len(workers)}))
            output.append(self.item("tower_registry", "provider_count", "pass" if len(providers) >= 6 else "fail", "warning", f"Providers registered: {len(providers)}", {"actual": len(providers)}))

        except Exception as e:
            output.append(self.item("tower_registry", "registry_access", "fail", "critical", str(e)))

        return output

    def lift_route_checks(self):
        output = []
        routes = [
            ("floor_05", "floor_24", "service_lift"),
            ("floor_24", "floor_27", "model_lift"),
            ("floor_24", "floor_23", "model_lift"),
            ("floor_21", "floor_24", "service_lift"),
            ("floor_23", "roof", "model_lift")
        ]

        try:
            from tower.lifts import LiftNetwork
            network = LiftNetwork()

            for source, target, preferred in routes:
                try:
                    lift = network.choose(source, target, preferred)
                    chosen = lift.get("id")
                    status = "pass" if chosen == preferred else "fail"
                    severity = "critical" if preferred in ["service_lift", "model_lift"] else "warning"
                    output.append(self.item(
                        "lift_routes",
                        f"{source}->{target}",
                        status,
                        severity,
                        f"Expected {preferred}, selected {chosen}.",
                        {"source": source, "target": target, "preferred": preferred, "selected": chosen}
                    ))
                except Exception as e:
                    output.append(self.item("lift_routes", f"{source}->{target}", "fail", "critical", str(e)))

        except Exception as e:
            output.append(self.item("lift_routes", "lift_network_access", "fail", "critical", str(e)))

        return output

    def packet_integrity_checks(self):
        output = []

        try:
            from tower.database import connect
            conn = connect()
            rows = conn.execute("SELECT id, ts, source, target, lift_id, priority, receipt, status FROM packets ORDER BY id DESC LIMIT 20").fetchall()
            desc = conn.execute("SELECT id, ts, source, target, lift_id, priority, receipt, status FROM packets LIMIT 1").description
            cols = [x[0] for x in desc] if desc else []
            packets = [dict(zip(cols, row)) for row in rows]
            conn.close()

            bad = [
                p for p in packets
                if not p.get("source") or not p.get("target") or not p.get("lift_id") or p.get("status") != "delivered"
            ]

            output.append(self.item(
                "packet_integrity",
                "recent_packets",
                "pass" if not bad else "fail",
                "critical",
                f"Recent packets checked: {len(packets)}. Bad packets: {len(bad)}.",
                {"recent_count": len(packets), "bad_count": len(bad), "bad_packets": bad[:5]}
            ))

            by_lift = {}
            for p in packets:
                by_lift[p.get("lift_id")] = by_lift.get(p.get("lift_id"), 0) + 1

            output.append(self.item("packet_integrity", "packet_lift_distribution", "pass", "info", "Packet lift distribution recorded.", {"by_lift": by_lift}))

        except Exception as e:
            output.append(self.item("packet_integrity", "packet_table", "fail", "warning", str(e)))

        return output

    def model_stack_checks(self):
        output = []

        stack = [
            ("coding_department", "tower.coding_department", "CodingDepartment"),
            ("adapter_systems", "tower.adapter_systems", "AdapterSystems"),
            ("integration_services", "tower.integration_services", "IntegrationServices"),
            ("model_routing_department", "tower.model_routing_department", "ModelRoutingDepartment"),
            ("local_model_operations", "tower.local_model_operations", "LocalModelOperations"),
            ("air_llm_operations", "tower.air_llm_operations", "AirLLMOperations"),
            ("model_infrastructure", "tower.model_infrastructure", "ModelInfrastructure")
        ]

        for name, module_name, class_name in stack:
            try:
                mod = importlib.import_module(module_name)
                cls = getattr(mod, class_name)
                dash = cls().dashboard()

                execution_enabled = bool(dash.get("execution_enabled", False))
                status = "pass" if execution_enabled is False else "fail"

                output.append(self.item(
                    "model_stack",
                    name,
                    status,
                    "critical",
                    f"{name} dashboard available. execution_enabled={execution_enabled}.",
                    {
                        "floor": dash.get("floor"),
                        "department": dash.get("department"),
                        "execution_enabled": execution_enabled
                    }
                ))

            except Exception as e:
                output.append(self.item("model_stack", name, "fail", "critical", str(e)))

        return output

    def dashboard_endpoint_checks(self):
        output = []
        server = ROOT / "src" / "dashboard" / "server.py"

        required_endpoints = [
            "/api/status",
            "/api/model_infrastructure",
            "/api/coding_department",
            "/api/adapter_systems",
            "/api/integration_services",
            "/api/model_routing_department",
            "/api/local_model_operations",
            "/api/air_llm_operations",
            "/api/diagnostics_department"
        ]

        if not server.exists():
            return [self.item("dashboard", "server.py", "fail", "critical", "Dashboard server missing.")]

        text = server.read_text(encoding="utf-8")
        for endpoint in required_endpoints:
            output.append(self.item(
                "dashboard",
                endpoint,
                "pass" if endpoint in text else "fail",
                "critical",
                "Endpoint found in dashboard server." if endpoint in text else "Endpoint missing from dashboard server."
            ))

        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=1.5) as r:
                status_code = getattr(r, "status", 200)
                output.append(self.item("dashboard_live", "/api/status", "pass", "info", f"Live endpoint responded with {status_code}."))
        except Exception as e:
            output.append(self.item("dashboard_live", "/api/status", "info", "info", f"Live endpoint not checked or server offline during diagnostics: {e}"))

        return output

    def run_all(self):
        items = []
        items.extend(self.import_checks())
        items.extend(self.file_and_registry_checks())
        items.extend(self.tower_registry_checks())
        items.extend(self.lift_route_checks())
        items.extend(self.packet_integrity_checks())
        items.extend(self.model_stack_checks())
        items.extend(self.dashboard_endpoint_checks())

        critical_failures = len([i for i in items if i["status"] == "fail" and i["severity"] == "critical"])
        warning_failures = len([i for i in items if i["status"] == "fail" and i["severity"] == "warning"])

        status = "healthy" if critical_failures == 0 and warning_failures == 0 else "degraded" if critical_failures == 0 else "critical"

        summary = {
            "ts": now(),
            "floor": "floor_33",
            "department": "Diagnostics Department",
            "version": "1.1",
            "status": status,
            "execution_enabled": False,
            "kernel_required": False,
            "models_required": False,
            "checks_run": len(items),
            "critical_failures": critical_failures,
            "warning_failures": warning_failures,
            "passed": len([i for i in items if i["status"] == "pass"]),
            "info": len([i for i in items if i["status"] == "info"])
        }

        cur = self.conn.execute(
            """
            INSERT INTO diagnostic_runs
            (ts, status, critical_failures, warning_failures, checks_run, summary_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (summary["ts"], status, critical_failures, warning_failures, len(items), json.dumps(summary))
        )

        run_id = cur.lastrowid

        for i in items:
            self.conn.execute(
                """
                INSERT INTO diagnostic_items
                (run_id, ts, category, name, status, severity, message, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, now(), i["category"], i["name"], i["status"], i["severity"], i["message"], json.dumps(i["details"]))
            )

        self.conn.commit()

        report = {
            "summary": summary,
            "items": items
        }

        report_path = ROOT / "floors" / "floor_33_diagnostics_department" / "inspection_reports" / "latest_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return report

    def recent_runs(self, limit=10):
        rows = self.conn.execute("SELECT * FROM diagnostic_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        output = []
        for r in rows:
            item = dict(r)
            try:
                item["summary"] = json.loads(item.pop("summary_json"))
            except Exception:
                pass
            output.append(item)
        return output

    def recent_items(self, limit=40):
        rows = self.conn.execute("SELECT * FROM diagnostic_items ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        output = []
        for r in rows:
            item = dict(r)
            try:
                item["details"] = json.loads(item.pop("details_json"))
            except Exception:
                pass
            output.append(item)
        return output

    def dashboard(self):
        report = self.run_all()
        return {
            "database": str(DB),
            "floor": "floor_33",
            "department": "Diagnostics Department",
            "version": "1.1",
            "role": "tower_engineering_inspection_layer",
            "execution_enabled": False,
            "kernel_required": False,
            "models_required": False,
            "diagnostic_status": report["summary"]["status"],
            "checks_run": report["summary"]["checks_run"],
            "critical_failures": report["summary"]["critical_failures"],
            "warning_failures": report["summary"]["warning_failures"],
            "passed": report["summary"]["passed"],
            "latest_report": "floors/floor_33_diagnostics_department/inspection_reports/latest_report.json",
            "recent_runs": self.recent_runs(5),
            "recent_items": self.recent_items(20),
            "policy": self.policy()
        }

if __name__ == "__main__":
    dept = DiagnosticsDepartment()
    print(json.dumps(dept.dashboard(), indent=2))
''')

write("scripts/diagnostics_department_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.diagnostics_department
""")

write("scripts/run_floor_33_diagnostics.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.diagnostics_department import DiagnosticsDepartment
import json
dept = DiagnosticsDepartment()
report = dept.run_all()
print(json.dumps(report["summary"], indent=2))
print("Report written to: floors/floor_33_diagnostics_department/inspection_reports/latest_report.json")
PY2
""")

for script in [
    "scripts/diagnostics_department_status.sh",
    "scripts/run_floor_33_diagnostics.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_diagnostics_department_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.diagnostics_department import DiagnosticsDepartment

dept = DiagnosticsDepartment()
report = dept.run_all()
summary = report['summary']

assert summary['floor'] == 'floor_33'
assert summary['department'] == 'Diagnostics Department'
assert summary['execution_enabled'] is False
assert summary['kernel_required'] is False
assert summary['models_required'] is False
assert summary['checks_run'] >= 25
assert summary['critical_failures'] == 0, report

dash = dept.dashboard()
assert dash['floor'] == 'floor_33'
assert dash['execution_enabled'] is False

print('DIAGNOSTICS DEPARTMENT V1.1 VALIDATION PASSED')
print('Status:', summary['status'])
print('Checks run:', summary['checks_run'])
print('Critical failures:', summary['critical_failures'])
print('Warning failures:', summary['warning_failures'])
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
from tower.diagnostics_department import DiagnosticsDepartment

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
<div class="panel"><h2>Floor 33 Diagnostics Department</h2><pre id="diagnostics_floor"></pre></div>
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
  if(f.id==="floor_33") return "diagnostics";
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
  let d = await (await fetch("/api/diagnostics_department")).json();
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
    floor:c.floor, department:c.department, routes_through:c.routes_through,
    requests:c.requests, patch_queue:c.patch_queue, review_queue:c.review_queue,
    test_queue:c.test_queue, workspaces:c.workspaces.length, worker_slots:c.worker_slots.length
  },null,2);

  adapters.textContent = JSON.stringify({
    floor:a.floor, department:a.department, execution_enabled:a.execution_enabled,
    hardwired_adapters:a.hardwired_adapters, providers_are_external:a.providers_are_external,
    adapter_count:a.adapter_count, capability_records:a.capability_records
  },null,2);

  integration.textContent = JSON.stringify({
    floor:i.floor, department:i.department, integration_health:i.integration_health,
    execution_enabled:i.execution_enabled, service_paths:i.service_paths,
    dependency_records:i.dependency_records
  },null,2);

  diagnostics_floor.textContent = JSON.stringify({
    floor:d.floor, department:d.department, diagnostic_status:d.diagnostic_status,
    checks_run:d.checks_run, critical_failures:d.critical_failures,
    warning_failures:d.warning_failures, passed:d.passed,
    execution_enabled:d.execution_enabled, latest_report:d.latest_report,
    recent_runs:d.recent_runs
  },null,2);

  routing.textContent = JSON.stringify({
    floor:r.floor, department:r.department, execution_enabled:r.execution_enabled,
    direct_provider_access:r.direct_provider_access, incoming_lift:r.incoming_lift,
    outgoing_lift:r.outgoing_lift, route_decisions:r.route_decisions,
    by_target:r.by_target, by_socket:r.by_socket
  },null,2);

  localmodels.textContent = JSON.stringify({
    floor:lm.floor, department:lm.department, models_required:lm.models_required,
    execution_enabled:lm.execution_enabled, hardwired_models:lm.hardwired_models,
    incoming_lift:lm.incoming_lift, detected_models:lm.detected_models,
    role_summary:lm.role_summary, recommendations:lm.recommendations
  },null,2);

  airllm.textContent = JSON.stringify({
    floor:air.floor, department:air.department, providers_are_external:air.providers_are_external,
    execution_enabled:air.execution_enabled, hardwired_providers:air.hardwired_providers,
    incoming_lift:air.incoming_lift, roof_link:air.roof_link,
    provider_count:air.provider_count, socket_count:air.socket_count
  },null,2);

  model.textContent = JSON.stringify({
    principle:m.principle, building_runs_without_models:m.building_runs_without_models,
    hardwired_providers:m.hardwired_providers, execution_enabled:m.execution_enabled,
    sockets:m.sockets.length, worker_slots:m.worker_slots.length,
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
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
''')

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Diagnostics Department V1.1

Floor 33 is now the tower engineering inspection layer.

It includes:
- Full tower validation
- Registry validation
- Lift route validation
- Packet integrity validation
- Floor manifest validation
- Department module import checks
- Dashboard endpoint checks
- Model infrastructure checks
- Integration health checks
- Inspection reports
- Dashboard panel

Floor 33 does not execute providers, adapters, tools, CLI commands, file operations, models, or kernel logic.
It only inspects and reports.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_floor_33_diagnostics.sh
./scripts/diagnostics_department_status.sh
python3 tests/test_diagnostics_department_v11.py
"""

if "Diagnostics Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Floor 33 Diagnostics Department V1.1 installed.")
print("Run:")
print("./scripts/run_floor_33_diagnostics.sh")
print("./scripts/diagnostics_department_status.sh")
