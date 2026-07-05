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

print("Installing Floor 34 Monitoring Department V1.1...")

for folder in [
    "floors/floor_34_monitoring_department/live_snapshots",
    "floors/floor_34_monitoring_department/heartbeat_records",
    "floors/floor_34_monitoring_department/lift_watch",
    "floors/floor_34_monitoring_department/packet_watch",
    "floors/floor_34_monitoring_department/service_watch",
    "floors/floor_34_monitoring_department/provider_watch",
    "floors/floor_34_monitoring_department/diagnostics_watch",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower",
    "src/dashboard"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

monitoring_policy = {
    "version": "1.1",
    "floor_id": "floor_34",
    "department": "Monitoring Department",
    "role": "live_building_watch_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "watches": [
        "dashboard heartbeat",
        "service uptime",
        "CPU and memory snapshot",
        "disk usage snapshot",
        "lift traffic",
        "packet flow",
        "floor registry",
        "adapter sockets",
        "provider sockets",
        "local model inventory",
        "diagnostics summary"
    ],
    "notice": "Floor 34 watches the living building. It does not execute providers, adapters, tools, CLI commands, model calls, or kernel logic."
}

monitoring_watch_targets = [
    {"id": "dashboard_heartbeat", "label": "Dashboard Heartbeat", "target": "http://127.0.0.1:8765/api/status", "severity": "critical"},
    {"id": "dashboard_process", "label": "Dashboard Process", "target": "data/runtime/dashboard.pid", "severity": "critical"},
    {"id": "lift_traffic", "label": "Lift Traffic", "target": "lift_state", "severity": "warning"},
    {"id": "packet_flow", "label": "Packet Flow", "target": "packets", "severity": "warning"},
    {"id": "floor_registry", "label": "Floor Registry", "target": "Registry.floors", "severity": "critical"},
    {"id": "provider_sockets", "label": "Provider Sockets", "target": "provider_sockets.json", "severity": "warning"},
    {"id": "adapter_sockets", "label": "Adapter Sockets", "target": "adapter_sockets.json", "severity": "warning"},
    {"id": "diagnostics_latest", "label": "Latest Diagnostics Report", "target": "floors/floor_33_diagnostics_department/inspection_reports/latest_report.json", "severity": "warning"}
]

write_json("data/registries/monitoring_policy.json", monitoring_policy)
write_json("data/registries/monitoring_watch_targets.json", monitoring_watch_targets)

write_json("floors/floor_34_monitoring_department/floor_manifest.json", {
    "floor_id": "floor_34",
    "department": "Monitoring Department",
    "version": "1.1",
    "role": "live_building_watch_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "notice": "Floor 34 monitors the living tower: uptime, heartbeat, traffic, packets, health, providers, and diagnostics."
})

write_json("floors/floor_34_monitoring_department/service_watch/watch_targets.json", monitoring_watch_targets)

write("config/monitoring_department.yaml", """
monitoring_department:
  version: 1.1
  floor_id: floor_34
  role: live_building_watch_layer
  execution_enabled: false
  hardwired_providers: false
  models_required: false
  kernel_required: false
  providers_are_external: true

principle: Floor 34 watches and records building activity. It does not execute providers, adapters, tools, CLI commands, model calls, or kernel logic.

watch_scope:
  - dashboard heartbeat
  - dashboard process uptime
  - cpu memory disk snapshot
  - lift traffic
  - packet flow
  - floor registry
  - provider socket watch
  - adapter socket watch
  - local model watch
  - diagnostics summary watch
""")

write("src/tower/monitoring_department.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import os
import sqlite3
import time
import urllib.request
import shutil

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "monitoring_department.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS monitoring_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    status TEXT,
    dashboard_online INTEGER,
    dashboard_pid INTEGER,
    service_uptime_seconds REAL,
    cpu_percent REAL,
    memory_percent REAL,
    root_disk_percent REAL,
    tower_disk_percent REAL,
    lift_traffic_total INTEGER,
    packet_count_recent INTEGER,
    diagnostics_status TEXT,
    summary_json TEXT
);

CREATE TABLE IF NOT EXISTS monitoring_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    event_type TEXT,
    status TEXT,
    details TEXT
);
"""

class MonitoringDepartment:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policy(self):
        return load_json("monitoring_policy.json", {})

    def watch_targets(self):
        return load_json("monitoring_watch_targets.json", [])

    def _optional_psutil(self):
        try:
            import psutil
            return psutil
        except Exception:
            return None

    def system_snapshot(self):
        psutil = self._optional_psutil()

        cpu_percent = None
        memory_percent = None

        if psutil:
            try:
                cpu_percent = psutil.cpu_percent(interval=0.05)
            except Exception:
                cpu_percent = None
            try:
                memory_percent = psutil.virtual_memory().percent
            except Exception:
                memory_percent = None
        else:
            try:
                meminfo = Path("/proc/meminfo").read_text()
                data = {}
                for line in meminfo.splitlines():
                    key, val = line.split(":", 1)
                    data[key] = int(val.strip().split()[0])
                total = data.get("MemTotal")
                available = data.get("MemAvailable")
                if total and available:
                    memory_percent = round(((total - available) / total) * 100, 2)
            except Exception:
                memory_percent = None

        root_usage = shutil.disk_usage("/")
        tower_usage = shutil.disk_usage(str(ROOT))

        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "root_disk_percent": round((root_usage.used / root_usage.total) * 100, 2),
            "tower_disk_percent": round((tower_usage.used / tower_usage.total) * 100, 2),
            "tower_free_gb": round(tower_usage.free / (1024 ** 3), 2)
        }

    def dashboard_heartbeat(self):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=1.5) as response:
                body = response.read().decode("utf-8", errors="replace")
                data = json.loads(body)
                return {
                    "online": True,
                    "status_code": getattr(response, "status", 200),
                    "floor_count": data.get("counts", {}).get("floors"),
                    "kernel_installed": data.get("counts", {}).get("kernel_installed"),
                    "message": "Dashboard heartbeat OK."
                }
        except Exception as e:
            return {
                "online": False,
                "status_code": None,
                "message": str(e)
            }

    def service_uptime(self):
        pid_path = ROOT / "data" / "runtime" / "dashboard.pid"
        if not pid_path.exists():
            return {
                "pid": None,
                "running": False,
                "uptime_seconds": 0,
                "message": "No dashboard.pid file."
            }

        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except Exception as e:
            return {
                "pid": None,
                "running": False,
                "uptime_seconds": 0,
                "message": f"Invalid pid file: {e}"
            }

        running = False
        try:
            os.kill(pid, 0)
            running = True
        except Exception:
            running = False

        uptime = 0
        psutil = self._optional_psutil()
        if running and psutil:
            try:
                uptime = time.time() - psutil.Process(pid).create_time()
            except Exception:
                uptime = 0
        elif running:
            try:
                uptime = time.time() - pid_path.stat().st_mtime
            except Exception:
                uptime = 0

        return {
            "pid": pid,
            "running": running,
            "uptime_seconds": round(uptime, 2),
            "message": "Dashboard process running." if running else "Dashboard process not running."
        }

    def lift_traffic(self):
        try:
            from tower.lifts import LiftNetwork
            states = LiftNetwork().states()
            total = sum(int(x.get("traffic_count", 0) or 0) for x in states)
            active = [x for x in states if int(x.get("traffic_count", 0) or 0) > 0]
            return {
                "ok": True,
                "total_traffic": total,
                "active_lifts": len(active),
                "states": states
            }
        except Exception as e:
            return {
                "ok": False,
                "total_traffic": 0,
                "active_lifts": 0,
                "error": str(e),
                "states": []
            }

    def packet_flow(self):
        try:
            from tower.lifts import LiftNetwork
            packets = LiftNetwork().packets()
            by_lift = {}
            by_status = {}
            for p in packets:
                by_lift[p.get("lift_id")] = by_lift.get(p.get("lift_id"), 0) + 1
                by_status[p.get("status")] = by_status.get(p.get("status"), 0) + 1
            return {
                "ok": True,
                "recent_count": len(packets),
                "by_lift": by_lift,
                "by_status": by_status,
                "recent": packets[:10]
            }
        except Exception as e:
            return {
                "ok": False,
                "recent_count": 0,
                "by_lift": {},
                "by_status": {},
                "error": str(e),
                "recent": []
            }

    def floor_registry_watch(self):
        try:
            from tower.registry import Registry
            reg = Registry()
            floors = reg.floors()
            return {
                "ok": True,
                "floors": len(floors),
                "vacant": len([f for f in floors if f.get("vacant")]),
                "zone_counts": self._zone_counts(floors)
            }
        except Exception as e:
            return {
                "ok": False,
                "floors": 0,
                "vacant": 0,
                "error": str(e)
            }

    def _zone_counts(self, floors):
        out = {}
        for f in floors:
            z = f.get("zone", "unknown")
            out[z] = out.get(z, 0) + 1
        return out

    def provider_socket_watch(self):
        out = {
            "adapter_systems": None,
            "air_llm_operations": None,
            "local_model_operations": None
        }

        try:
            from tower.adapter_systems import AdapterSystems
            a = AdapterSystems().dashboard()
            out["adapter_systems"] = {
                "adapter_count": a.get("adapter_count"),
                "execution_enabled": a.get("execution_enabled"),
                "hardwired_adapters": a.get("hardwired_adapters")
            }
        except Exception as e:
            out["adapter_systems"] = {"error": str(e)}

        try:
            from tower.air_llm_operations import AirLLMOperations
            air = AirLLMOperations().dashboard()
            out["air_llm_operations"] = {
                "provider_count": air.get("provider_count"),
                "socket_count": air.get("socket_count"),
                "execution_enabled": air.get("execution_enabled"),
                "hardwired_providers": air.get("hardwired_providers")
            }
        except Exception as e:
            out["air_llm_operations"] = {"error": str(e)}

        try:
            from tower.local_model_operations import LocalModelOperations
            lm = LocalModelOperations().dashboard()
            out["local_model_operations"] = {
                "detected_models": lm.get("detected_models"),
                "execution_enabled": lm.get("execution_enabled"),
                "hardwired_models": lm.get("hardwired_models")
            }
        except Exception as e:
            out["local_model_operations"] = {"error": str(e)}

        return out

    def diagnostics_watch(self):
        report_path = ROOT / "floors" / "floor_33_diagnostics_department" / "inspection_reports" / "latest_report.json"
        if not report_path.exists():
            return {
                "available": False,
                "status": "unknown",
                "message": "No Floor 33 latest report yet."
            }

        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            summary = report.get("summary", {})
            return {
                "available": True,
                "status": summary.get("status", "unknown"),
                "checks_run": summary.get("checks_run"),
                "critical_failures": summary.get("critical_failures"),
                "warning_failures": summary.get("warning_failures"),
                "ts": summary.get("ts")
            }
        except Exception as e:
            return {
                "available": False,
                "status": "error",
                "message": str(e)
            }

    def record_event(self, event_type, status, details):
        self.conn.execute(
            "INSERT INTO monitoring_events(ts, event_type, status, details) VALUES (?, ?, ?, ?)",
            (now(), event_type, status, json.dumps(details))
        )
        self.conn.commit()

    def collect_snapshot(self):
        system = self.system_snapshot()
        heartbeat = self.dashboard_heartbeat()
        uptime = self.service_uptime()
        lifts = self.lift_traffic()
        packets = self.packet_flow()
        floors = self.floor_registry_watch()
        providers = self.provider_socket_watch()
        diagnostics = self.diagnostics_watch()

        critical_issues = []
        warnings = []

        if not heartbeat.get("online"):
            critical_issues.append("dashboard heartbeat offline")
        if not uptime.get("running"):
            critical_issues.append("dashboard process not running")
        if not floors.get("ok"):
            critical_issues.append("floor registry unavailable")
        if not lifts.get("ok"):
            warnings.append("lift traffic unavailable")
        if not packets.get("ok"):
            warnings.append("packet flow unavailable")
        if diagnostics.get("status") not in ["healthy", "unknown"]:
            warnings.append(f"diagnostics status: {diagnostics.get('status')}")

        status = "healthy" if not critical_issues and not warnings else "degraded" if not critical_issues else "critical"

        summary = {
            "ts": now(),
            "floor": "floor_34",
            "department": "Monitoring Department",
            "version": "1.1",
            "status": status,
            "execution_enabled": False,
            "kernel_required": False,
            "models_required": False,
            "critical_issues": critical_issues,
            "warnings": warnings,
            "system": system,
            "dashboard_heartbeat": heartbeat,
            "service_uptime": uptime,
            "lift_traffic": lifts,
            "packet_flow": packets,
            "floor_registry": floors,
            "provider_socket_watch": providers,
            "diagnostics_watch": diagnostics
        }

        self.conn.execute(
            """
            INSERT INTO monitoring_snapshots
            (ts, status, dashboard_online, dashboard_pid, service_uptime_seconds, cpu_percent,
             memory_percent, root_disk_percent, tower_disk_percent, lift_traffic_total,
             packet_count_recent, diagnostics_status, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["ts"],
                status,
                int(bool(heartbeat.get("online"))),
                uptime.get("pid"),
                float(uptime.get("uptime_seconds", 0) or 0),
                system.get("cpu_percent"),
                system.get("memory_percent"),
                system.get("root_disk_percent"),
                system.get("tower_disk_percent"),
                int(lifts.get("total_traffic", 0) or 0),
                int(packets.get("recent_count", 0) or 0),
                diagnostics.get("status"),
                json.dumps(summary)
            )
        )
        self.conn.commit()

        out_path = ROOT / "floors" / "floor_34_monitoring_department" / "live_snapshots" / "latest_snapshot.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        return summary

    def recent_snapshots(self, limit=10):
        rows = self.conn.execute("SELECT * FROM monitoring_snapshots ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["summary"] = json.loads(item.pop("summary_json"))
            except Exception:
                pass
            out.append(item)
        return out

    def recent_events(self, limit=20):
        rows = self.conn.execute("SELECT * FROM monitoring_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        snap = self.collect_snapshot()
        return {
            "database": str(DB),
            "floor": "floor_34",
            "department": "Monitoring Department",
            "version": "1.1",
            "role": "live_building_watch_layer",
            "execution_enabled": False,
            "kernel_required": False,
            "models_required": False,
            "monitoring_status": snap["status"],
            "dashboard_online": snap["dashboard_heartbeat"].get("online"),
            "dashboard_pid": snap["service_uptime"].get("pid"),
            "service_uptime_seconds": snap["service_uptime"].get("uptime_seconds"),
            "cpu_percent": snap["system"].get("cpu_percent"),
            "memory_percent": snap["system"].get("memory_percent"),
            "tower_disk_percent": snap["system"].get("tower_disk_percent"),
            "tower_free_gb": snap["system"].get("tower_free_gb"),
            "lift_traffic_total": snap["lift_traffic"].get("total_traffic"),
            "active_lifts": snap["lift_traffic"].get("active_lifts"),
            "packet_count_recent": snap["packet_flow"].get("recent_count"),
            "diagnostics_status": snap["diagnostics_watch"].get("status"),
            "critical_issues": snap["critical_issues"],
            "warnings": snap["warnings"],
            "provider_socket_watch": snap["provider_socket_watch"],
            "recent_snapshots": self.recent_snapshots(5),
            "latest_snapshot": "floors/floor_34_monitoring_department/live_snapshots/latest_snapshot.json",
            "policy": self.policy()
        }

if __name__ == "__main__":
    print(json.dumps(MonitoringDepartment().dashboard(), indent=2))
''')

write("scripts/monitoring_department_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.monitoring_department
""")

write("scripts/run_floor_34_monitoring.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.monitoring_department import MonitoringDepartment
import json
dept = MonitoringDepartment()
snapshot = dept.collect_snapshot()
print(json.dumps({
    "status": snapshot["status"],
    "dashboard_online": snapshot["dashboard_heartbeat"].get("online"),
    "dashboard_pid": snapshot["service_uptime"].get("pid"),
    "uptime_seconds": snapshot["service_uptime"].get("uptime_seconds"),
    "cpu_percent": snapshot["system"].get("cpu_percent"),
    "memory_percent": snapshot["system"].get("memory_percent"),
    "tower_disk_percent": snapshot["system"].get("tower_disk_percent"),
    "tower_free_gb": snapshot["system"].get("tower_free_gb"),
    "lift_traffic_total": snapshot["lift_traffic"].get("total_traffic"),
    "packet_count_recent": snapshot["packet_flow"].get("recent_count"),
    "diagnostics_status": snapshot["diagnostics_watch"].get("status"),
    "critical_issues": snapshot["critical_issues"],
    "warnings": snapshot["warnings"]
}, indent=2))
print("Snapshot written to: floors/floor_34_monitoring_department/live_snapshots/latest_snapshot.json")
PY2
""")

for script in [
    "scripts/monitoring_department_status.sh",
    "scripts/run_floor_34_monitoring.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_monitoring_department_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.monitoring_department import MonitoringDepartment

dept = MonitoringDepartment()
snap = dept.collect_snapshot()

assert snap['floor'] == 'floor_34'
assert snap['department'] == 'Monitoring Department'
assert snap['execution_enabled'] is False
assert snap['kernel_required'] is False
assert snap['models_required'] is False
assert 'system' in snap
assert 'dashboard_heartbeat' in snap
assert 'lift_traffic' in snap
assert 'packet_flow' in snap
assert 'provider_socket_watch' in snap
assert 'diagnostics_watch' in snap

dash = dept.dashboard()
assert dash['floor'] == 'floor_34'
assert dash['execution_enabled'] is False
assert dash['latest_snapshot'].endswith('latest_snapshot.json')

print('MONITORING DEPARTMENT V1.1 VALIDATION PASSED')
print('Status:', snap['status'])
print('Dashboard online:', snap['dashboard_heartbeat'].get('online'))
print('Lift traffic total:', snap['lift_traffic'].get('total_traffic'))
print('Packet count recent:', snap['packet_flow'].get('recent_count'))
print('Diagnostics status:', snap['diagnostics_watch'].get('status'))
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
from tower.monitoring_department import MonitoringDepartment

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
.air{background:#18385f;border:1px solid #9ac7ff}
.model{background:#143d5a;border:1px solid #50bfff}
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
<div class="panel"><h2>Floor 34 Monitoring Department</h2><pre id="monitoring_floor"></pre></div>
<div class="panel"><h2>Floor 33 Diagnostics Department</h2><pre id="diagnostics_floor"></pre></div>
<div class="panel"><h2>Floor 22 Integration Services</h2><pre id="integration"></pre></div>
<div class="panel"><h2>Floor 21 Adapter Systems</h2><pre id="adapters"></pre></div>
<div class="panel"><h2>Floor 5 Coding Department</h2><pre id="coding"></pre></div>
<div class="panel"><h2>Floor 24 Model Routing Department</h2><pre id="routing"></pre></div>
<div class="panel"><h2>Floor 27 Local Model Operations</h2><pre id="localmodels"></pre></div>
<div class="panel"><h2>Floor 23 AIR LLM Operations</h2><pre id="airllm"></pre></div>
<div class="panel"><h2>Model Infrastructure</h2><pre id="model"></pre></div>
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
  let mon = await (await fetch("/api/monitoring_department")).json();
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

  monitoring_floor.textContent = JSON.stringify({
    floor:mon.floor,
    department:mon.department,
    monitoring_status:mon.monitoring_status,
    dashboard_online:mon.dashboard_online,
    dashboard_pid:mon.dashboard_pid,
    service_uptime_seconds:mon.service_uptime_seconds,
    cpu_percent:mon.cpu_percent,
    memory_percent:mon.memory_percent,
    tower_disk_percent:mon.tower_disk_percent,
    tower_free_gb:mon.tower_free_gb,
    lift_traffic_total:mon.lift_traffic_total,
    active_lifts:mon.active_lifts,
    packet_count_recent:mon.packet_count_recent,
    diagnostics_status:mon.diagnostics_status,
    critical_issues:mon.critical_issues,
    warnings:mon.warnings,
    latest_snapshot:mon.latest_snapshot
  },null,2);

  diagnostics_floor.textContent = JSON.stringify({
    floor:d.floor, department:d.department, diagnostic_status:d.diagnostic_status,
    checks_run:d.checks_run, critical_failures:d.critical_failures,
    warning_failures:d.warning_failures, passed:d.passed,
    latest_report:d.latest_report
  },null,2);

  integration.textContent = JSON.stringify({
    floor:i.floor, department:i.department, integration_health:i.integration_health,
    execution_enabled:i.execution_enabled, service_paths:i.service_paths,
    dependency_records:i.dependency_records
  },null,2);

  adapters.textContent = JSON.stringify({
    floor:a.floor, department:a.department, execution_enabled:a.execution_enabled,
    hardwired_adapters:a.hardwired_adapters, providers_are_external:a.providers_are_external,
    adapter_count:a.adapter_count, capability_records:a.capability_records
  },null,2);

  coding.textContent = JSON.stringify({
    floor:c.floor, department:c.department, routes_through:c.routes_through,
    requests:c.requests, patch_queue:c.patch_queue, review_queue:c.review_queue,
    test_queue:c.test_queue, workspaces:c.workspaces.length, worker_slots:c.worker_slots.length
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
    role_summary:lm.role_summary
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
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
''')

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Monitoring Department V1.1

Floor 34 is now the live building watch layer.

It includes:
- CPU/RAM/disk snapshot
- Dashboard heartbeat
- Dashboard process uptime tracker
- Lift traffic monitor
- Packet flow monitor
- Floor activity monitor
- Provider/socket watch
- Diagnostics summary watch
- Building health timeline
- Dashboard panel

Floor 34 does not execute providers, adapters, tools, CLI commands, model calls, or kernel logic.
It only watches and records live building activity.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_floor_34_monitoring.sh
./scripts/monitoring_department_status.sh
python3 tests/test_monitoring_department_v11.py
"""

if "Monitoring Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Floor 34 Monitoring Department V1.1 installed.")
print("Run:")
print("./scripts/run_floor_34_monitoring.sh")
print("./scripts/monitoring_department_status.sh")
