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

def read_json(rel, fallback):
    path = ROOT / rel
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

print("Installing Penthouse Readiness V1.1...")

for folder in [
    "penthouse/kernel_installation_socket",
    "penthouse/kernel_discovery_interface",
    "penthouse/kernel_monitoring_interface",
    "penthouse/kernel_health_display",
    "penthouse/kernel_event_console",
    "penthouse/kernel_connection_ports",
    "penthouse/kernel_occupancy_acceptance",
    "penthouse/floor_53_handoff",
    "penthouse/security_precheck",
    "penthouse/emergency_stairwell_validation",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower",
    "src/dashboard"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

penthouse_policy = {
    "version": "1.1",
    "penthouse_id": "penthouse",
    "name": "Penthouse Readiness Layer",
    "status": "reserved",
    "reserved_for": "Future QSB Kernel 4.5 Installation",
    "kernel_installed": False,
    "kernel_logic_present": False,
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "principle": "The Penthouse is an installation socket, not the kernel. QSB Kernel 4.5 has not been built or installed.",
    "allowed_now": [
        "kernel installation socket",
        "kernel discovery interface",
        "kernel monitoring interface",
        "kernel health display",
        "kernel event console",
        "kernel connection ports",
        "kernel occupancy readiness report"
    ],
    "not_allowed_now": [
        "kernel reasoning logic",
        "autonomous agent logic",
        "provider execution",
        "model execution",
        "kernel self-modification",
        "external cloud calls"
    ],
    "visible_message": "Reserved For Future QSB Kernel 4.5 Installation"
}

kernel_installation_socket = {
    "socket_id": "qsb_kernel_4_5_installation_socket",
    "penthouse_id": "penthouse",
    "reserved_for": "QSB Kernel 4.5",
    "status": "socket_ready_empty",
    "kernel_installed": False,
    "kernel_logic_present": False,
    "accepts_future_kernel_version": "4.5",
    "requires_acceptance_report": True,
    "requires_security_precheck": True,
    "requires_floor_53_handoff": True,
    "requires_emergency_stairwell_route": True,
    "notice": "Reserved For Future QSB Kernel 4.5 Installation"
}

kernel_connection_ports = [
    {"id": "port_registry_read", "name": "Registry Read Port", "direction": "inbound", "target": "data/registries", "enabled": True, "execution_enabled": False},
    {"id": "port_lift_network", "name": "Lift Network Port", "direction": "inbound_outbound", "target": "src/tower/lifts.py", "enabled": True, "execution_enabled": False},
    {"id": "port_floor_53_handoff", "name": "Floor 53 Handoff Port", "direction": "inbound", "target": "floor_53", "enabled": True, "execution_enabled": False},
    {"id": "port_diagnostics", "name": "Diagnostics Port", "direction": "inbound", "target": "floor_33", "enabled": True, "execution_enabled": False},
    {"id": "port_monitoring", "name": "Monitoring Port", "direction": "inbound", "target": "floor_34", "enabled": True, "execution_enabled": False},
    {"id": "port_infrastructure", "name": "Infrastructure Services Port", "direction": "inbound", "target": "floor_35", "enabled": True, "execution_enabled": False},
    {"id": "port_security_gate", "name": "Security / Permissions Gate Port", "direction": "inbound", "target": "floor_28_floor_29_floor_30", "enabled": True, "execution_enabled": False},
    {"id": "port_event_console", "name": "Kernel Event Console Port", "direction": "outbound", "target": "penthouse/kernel_event_console", "enabled": True, "execution_enabled": False}
]

kernel_discovery_manifest = {
    "interface_id": "kernel_discovery_interface",
    "status": "ready",
    "kernel_installed": False,
    "discoverable_resources": [
        "registries",
        "lift network",
        "floor registry",
        "worker registry",
        "diagnostics department",
        "monitoring department",
        "infrastructure services department",
        "adapter systems",
        "integration services",
        "AIR LLM sockets",
        "local model inventory"
    ],
    "discovery_mode": "readiness_only",
    "execution_enabled": False
}

kernel_monitoring_interface = {
    "interface_id": "kernel_monitoring_interface",
    "status": "ready",
    "monitors": [
        "kernel socket empty/full state",
        "kernel health future port",
        "kernel event console",
        "floor 53 handoff",
        "security precheck",
        "emergency stairwell validation"
    ],
    "kernel_installed": False,
    "execution_enabled": False
}

kernel_health_display = {
    "display_id": "kernel_health_display",
    "message": "Reserved For Future QSB Kernel 4.5 Installation",
    "kernel_installed": False,
    "kernel_health": "not_installed",
    "socket_status": "ready_empty",
    "execution_enabled": False
}

floor_53_handoff = {
    "handoff_id": "floor_53_to_penthouse_handoff",
    "source_floor": "floor_53",
    "source_department": "Tower Command Department",
    "target": "penthouse",
    "status": "handoff_channel_ready",
    "sealed_packets": True,
    "allowed_lifts": ["executive_lift", "service_lift", "security_lift", "emergency_stairwell"],
    "kernel_installed": False,
    "execution_enabled": False
}

security_precheck = {
    "security_precheck_id": "penthouse_security_precheck",
    "status": "precheck_ready",
    "required_floors": ["floor_28", "floor_29", "floor_30", "floor_31", "floor_32", "floor_33", "floor_34", "floor_35"],
    "security_gate": "not_enforcing_yet",
    "execution_enabled": False,
    "notice": "Security gate records readiness only. It does not enforce kernel permissions yet."
}

write_json("data/registries/penthouse_policy.json", penthouse_policy)
write_json("data/registries/kernel_installation_socket.json", kernel_installation_socket)
write_json("data/registries/kernel_connection_ports.json", kernel_connection_ports)
write_json("data/registries/kernel_discovery_manifest.json", kernel_discovery_manifest)
write_json("data/registries/kernel_monitoring_interface.json", kernel_monitoring_interface)
write_json("data/registries/kernel_health_display.json", kernel_health_display)
write_json("data/registries/floor_53_penthouse_handoff.json", floor_53_handoff)
write_json("data/registries/penthouse_security_precheck.json", security_precheck)

write_json("penthouse/kernel_installation_socket/socket_manifest.json", kernel_installation_socket)
write_json("penthouse/kernel_discovery_interface/discovery_manifest.json", kernel_discovery_manifest)
write_json("penthouse/kernel_monitoring_interface/monitoring_interface.json", kernel_monitoring_interface)
write_json("penthouse/kernel_health_display/health_display.json", kernel_health_display)
write_json("penthouse/kernel_connection_ports/ports.json", kernel_connection_ports)
write_json("penthouse/floor_53_handoff/handoff.json", floor_53_handoff)
write_json("penthouse/security_precheck/security_precheck.json", security_precheck)

write("penthouse/kernel_event_console/events.jsonl", "")
write("penthouse/kernel_occupancy_acceptance/README.md", """
# Penthouse Kernel Occupancy Acceptance

This folder stores readiness reports for the future QSB Kernel 4.5.

The kernel is not installed.
The Penthouse is reserved and socket-ready only.
""")

# Strengthen lift registry for Penthouse readiness.
lifts = read_json("data/registries/lifts.json", [])
if lifts:
    all_stops = ["B3", "B2", "B1", "ground"] + [f"floor_{i:02d}" for i in range(1, 54)] + ["penthouse", "roof"]

    for lift in lifts:
        lid = lift.get("id")
        if lid == "emergency_stairwell":
            lift["serves"] = all_stops
            lift["status"] = lift.get("status", "available")
            lift["emergency_route"] = True

        if lid == "service_lift":
            lift["serves"] = all_stops
            lift["status"] = lift.get("status", "online")

        if lid == "security_lift":
            lift["serves"] = all_stops
            lift["status"] = lift.get("status", "online")

        if lid == "executive_lift":
            lift["serves"] = [f"floor_{i:02d}" for i in range(45, 54)] + ["penthouse"]
            lift["status"] = lift.get("status", "online")

    write_json("data/registries/lifts.json", lifts)

write("config/penthouse_readiness.yaml", """
penthouse_readiness:
  version: 1.1
  penthouse_id: penthouse
  reserved_for: Future QSB Kernel 4.5 Installation
  kernel_installed: false
  kernel_logic_present: false
  execution_enabled: false
  models_required: false

principle: The Penthouse is the reserved installation socket. It is not the kernel.

components:
  - kernel installation socket
  - kernel discovery interface
  - kernel monitoring interface
  - kernel health display
  - kernel event console
  - kernel connection ports
  - floor 53 handoff
  - emergency stairwell validation
  - security precheck
  - occupancy acceptance report
""")

write("src/tower/penthouse_readiness.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "penthouse_readiness.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json_file(path, fallback):
    path = Path(path)
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

def load_registry(name, fallback):
    return load_json_file(REG / name, fallback)

SCHEMA = """
CREATE TABLE IF NOT EXISTS penthouse_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    event_type TEXT,
    status TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS readiness_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    status TEXT,
    checks_run INTEGER,
    critical_failures INTEGER,
    warnings INTEGER,
    summary_json TEXT
);

CREATE TABLE IF NOT EXISTS connection_ports (
    port_id TEXT PRIMARY KEY,
    name TEXT,
    direction TEXT,
    target TEXT,
    enabled INTEGER,
    execution_enabled INTEGER,
    status TEXT,
    updated_ts TEXT
);
"""

class PenthouseReadiness:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.sync_ports()

    def policy(self):
        return load_registry("penthouse_policy.json", {})

    def socket(self):
        return load_registry("kernel_installation_socket.json", {})

    def ports(self):
        return load_registry("kernel_connection_ports.json", [])

    def discovery(self):
        return load_registry("kernel_discovery_manifest.json", {})

    def monitoring_interface(self):
        return load_registry("kernel_monitoring_interface.json", {})

    def health_display(self):
        return load_registry("kernel_health_display.json", {})

    def handoff(self):
        return load_registry("floor_53_penthouse_handoff.json", {})

    def security_precheck(self):
        return load_registry("penthouse_security_precheck.json", {})

    def sync_ports(self):
        for port in self.ports():
            self.conn.execute(
                """
                INSERT OR REPLACE INTO connection_ports
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    port["id"],
                    port["name"],
                    port["direction"],
                    port["target"],
                    int(bool(port.get("enabled", False))),
                    int(bool(port.get("execution_enabled", False))),
                    "registered",
                    now()
                )
            )
        self.conn.commit()

    def record_event(self, event_type, status, details):
        self.conn.execute(
            "INSERT INTO penthouse_events(ts, event_type, status, details) VALUES (?, ?, ?, ?)",
            (now(), event_type, status, json.dumps(details))
        )
        self.conn.commit()

        line = json.dumps({
            "ts": now(),
            "event_type": event_type,
            "status": status,
            "details": details
        })
        console = ROOT / "penthouse" / "kernel_event_console" / "events.jsonl"
        console.parent.mkdir(parents=True, exist_ok=True)
        with console.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def check(self, name, ok, severity="critical", message="", details=None):
        return {
            "name": name,
            "status": "pass" if ok else "fail",
            "severity": severity,
            "message": message,
            "details": details or {}
        }

    def kernel_absence_check(self):
        forbidden = [
            ROOT / "penthouse" / "qsb_kernel_4_5.py",
            ROOT / "penthouse" / "kernel.py",
            ROOT / "src" / "tower" / "qsb_kernel_4_5.py",
            ROOT / "src" / "tower" / "kernel.py"
        ]
        present = [str(p.relative_to(ROOT)) for p in forbidden if p.exists()]
        return self.check(
            "kernel_absence",
            not present,
            "critical",
            "No kernel logic present, as required." if not present else "Kernel-like files found before installation.",
            {"present": present}
        )

    def socket_checks(self):
        paths = [
            "penthouse/kernel_installation_socket/socket_manifest.json",
            "penthouse/kernel_discovery_interface/discovery_manifest.json",
            "penthouse/kernel_monitoring_interface/monitoring_interface.json",
            "penthouse/kernel_health_display/health_display.json",
            "penthouse/kernel_connection_ports/ports.json",
            "penthouse/kernel_event_console/events.jsonl",
            "penthouse/floor_53_handoff/handoff.json",
            "penthouse/security_precheck/security_precheck.json"
        ]

        items = []
        for rel in paths:
            p = ROOT / rel
            items.append(self.check(
                f"file:{rel}",
                p.exists(),
                "critical",
                "Required Penthouse file exists." if p.exists() else "Required Penthouse file missing.",
                {"path": rel}
            ))

        socket = self.socket()
        items.append(self.check(
            "installation_socket_empty_ready",
            socket.get("status") == "socket_ready_empty" and socket.get("kernel_installed") is False,
            "critical",
            "Kernel socket is ready and empty.",
            socket
        ))

        return items

    def port_checks(self):
        ports = self.ports()
        items = [
            self.check(
                "connection_ports_registered",
                len(ports) >= 8,
                "critical",
                f"Connection ports registered: {len(ports)}.",
                {"count": len(ports)}
            )
        ]

        enabled = [p for p in ports if p.get("enabled")]
        execution_enabled = [p for p in ports if p.get("execution_enabled")]

        items.append(self.check(
            "connection_ports_enabled_for_readiness",
            len(enabled) == len(ports) and len(ports) >= 8,
            "critical",
            "All ports are enabled for readiness visibility.",
            {"enabled_count": len(enabled)}
        ))

        items.append(self.check(
            "connection_ports_execution_disabled",
            len(execution_enabled) == 0,
            "critical",
            "All connection ports have execution disabled.",
            {"execution_enabled_ports": execution_enabled}
        ))

        return items

    def floor_53_handoff_checks(self):
        items = []
        try:
            from tower.registry import Registry
            floors = Registry().floors()
            floor_ids = {f.get("id") for f in floors}

            items.append(self.check(
                "floor_53_registered",
                "floor_53" in floor_ids,
                "critical",
                "Floor 53 Tower Command Department is registered.",
                {"floor_53_present": "floor_53" in floor_ids}
            ))
        except Exception as e:
            items.append(self.check("floor_53_registry_access", False, "critical", str(e)))

        handoff = self.handoff()
        items.append(self.check(
            "floor_53_handoff_channel",
            handoff.get("status") == "handoff_channel_ready" and handoff.get("target") == "penthouse",
            "critical",
            "Floor 53 to Penthouse handoff channel is ready.",
            handoff
        ))

        return items

    def emergency_stairwell_checks(self):
        items = []

        try:
            from tower.lifts import LiftNetwork
            network = LiftNetwork()

            stair = network.choose("penthouse", "B1", "emergency_stairwell")
            items.append(self.check(
                "emergency_stairwell_penthouse_to_b1",
                stair.get("id") == "emergency_stairwell",
                "critical",
                f"Penthouse to B1 route selected {stair.get('id')}.",
                {"selected": stair}
            ))

            service = network.choose("B1", "penthouse", "service_lift")
            items.append(self.check(
                "service_lift_b1_to_penthouse",
                service.get("id") == "service_lift",
                "warning",
                f"B1 to Penthouse service route selected {service.get('id')}.",
                {"selected": service}
            ))

            executive = network.choose("floor_53", "penthouse", "executive_lift")
            items.append(self.check(
                "executive_lift_floor_53_to_penthouse",
                executive.get("id") == "executive_lift",
                "warning",
                f"Floor 53 to Penthouse executive route selected {executive.get('id')}.",
                {"selected": executive}
            ))

        except Exception as e:
            items.append(self.check("emergency_stairwell_route_validation", False, "critical", str(e)))

        return items

    def security_precheck_checks(self):
        required = self.security_precheck().get("required_floors", [])
        items = []

        try:
            from tower.registry import Registry
            floors = Registry().floors()
            floor_ids = {f.get("id") for f in floors}
            missing = [f for f in required if f not in floor_ids]

            items.append(self.check(
                "security_required_floors_registered",
                not missing,
                "critical",
                "Security/precheck floors are registered." if not missing else "Some security/precheck floors are missing.",
                {"required": required, "missing": missing}
            ))
        except Exception as e:
            items.append(self.check("security_precheck_registry_access", False, "critical", str(e)))

        return items

    def lower_infrastructure_checks(self):
        items = []

        checks = [
            ("floor_33_diagnostics_department", "tower.diagnostics_department", "DiagnosticsDepartment", "diagnostic_status"),
            ("floor_34_monitoring_department", "tower.monitoring_department", "MonitoringDepartment", "monitoring_status"),
            ("floor_35_infrastructure_services", "tower.infrastructure_services", "InfrastructureServices", "infrastructure_status")
        ]

        import importlib

        for name, module_name, class_name, status_key in checks:
            try:
                mod = importlib.import_module(module_name)
                cls = getattr(mod, class_name)
                dash = cls().dashboard()
                status = dash.get(status_key)

                items.append(self.check(
                    name,
                    status in ["healthy", "degraded"],
                    "warning",
                    f"{name} dashboard reachable with status {status}.",
                    {"status": status}
                ))
            except Exception as e:
                items.append(self.check(name, False, "warning", str(e)))

        return items

    def run_acceptance(self):
        items = []
        items.append(self.kernel_absence_check())
        items.extend(self.socket_checks())
        items.extend(self.port_checks())
        items.extend(self.floor_53_handoff_checks())
        items.extend(self.emergency_stairwell_checks())
        items.extend(self.security_precheck_checks())
        items.extend(self.lower_infrastructure_checks())

        critical_failures = len([i for i in items if i["status"] == "fail" and i["severity"] == "critical"])
        warnings = len([i for i in items if i["status"] == "fail" and i["severity"] == "warning"])

        if critical_failures == 0:
            readiness_status = "ready_for_future_qsb_kernel_4_5"
        else:
            readiness_status = "not_ready_for_kernel_occupancy"

        summary = {
            "ts": now(),
            "penthouse": "penthouse",
            "reserved_for": "Future QSB Kernel 4.5 Installation",
            "readiness_status": readiness_status,
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "checks_run": len(items),
            "critical_failures": critical_failures,
            "warnings": warnings,
            "passed": len([i for i in items if i["status"] == "pass"]),
            "visible_message": "Reserved For Future QSB Kernel 4.5 Installation"
        }

        self.conn.execute(
            """
            INSERT INTO readiness_runs
            (ts, status, checks_run, critical_failures, warnings, summary_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (summary["ts"], readiness_status, len(items), critical_failures, warnings, json.dumps(summary))
        )
        self.conn.commit()

        report = {
            "summary": summary,
            "items": items
        }

        report_path = ROOT / "penthouse" / "kernel_occupancy_acceptance" / "latest_acceptance_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        self.record_event("penthouse_acceptance_run", readiness_status, summary)

        return report

    def recent_runs(self, limit=10):
        rows = self.conn.execute("SELECT * FROM readiness_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
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
        rows = self.conn.execute("SELECT * FROM penthouse_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        report = self.run_acceptance()
        summary = report["summary"]
        return {
            "database": str(DB),
            "penthouse": "penthouse",
            "department": "Penthouse Readiness Layer",
            "version": "1.1",
            "reserved_for": "Future QSB Kernel 4.5 Installation",
            "visible_message": "Reserved For Future QSB Kernel 4.5 Installation",
            "readiness_status": summary["readiness_status"],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "checks_run": summary["checks_run"],
            "critical_failures": summary["critical_failures"],
            "warnings": summary["warnings"],
            "passed": summary["passed"],
            "socket": self.socket(),
            "connection_ports": len(self.ports()),
            "discovery_interface": self.discovery().get("status"),
            "monitoring_interface": self.monitoring_interface().get("status"),
            "health_display": self.health_display(),
            "floor_53_handoff": self.handoff().get("status"),
            "latest_acceptance_report": "penthouse/kernel_occupancy_acceptance/latest_acceptance_report.json",
            "recent_runs": self.recent_runs(5),
            "recent_events": self.recent_events(10),
            "policy": self.policy()
        }

if __name__ == "__main__":
    print(json.dumps(PenthouseReadiness().dashboard(), indent=2))
''')

write("scripts/penthouse_readiness_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.penthouse_readiness
""")

write("scripts/run_penthouse_acceptance.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.penthouse_readiness import PenthouseReadiness
import json
dept = PenthouseReadiness()
report = dept.run_acceptance()
print(json.dumps(report["summary"], indent=2))
print("Report written to: penthouse/kernel_occupancy_acceptance/latest_acceptance_report.json")
PY2
""")

for script in [
    "scripts/penthouse_readiness_status.sh",
    "scripts/run_penthouse_acceptance.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_penthouse_readiness_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.penthouse_readiness import PenthouseReadiness

dept = PenthouseReadiness()
report = dept.run_acceptance()
summary = report['summary']

assert summary['penthouse'] == 'penthouse'
assert summary['reserved_for'] == 'Future QSB Kernel 4.5 Installation'
assert summary['kernel_installed'] is False
assert summary['kernel_logic_present'] is False
assert summary['execution_enabled'] is False
assert summary['checks_run'] >= 15
assert summary['critical_failures'] == 0, report
assert summary['readiness_status'] == 'ready_for_future_qsb_kernel_4_5', report

dash = dept.dashboard()
assert dash['penthouse'] == 'penthouse'
assert dash['kernel_installed'] is False
assert dash['connection_ports'] >= 8

print('PENTHOUSE READINESS V1.1 VALIDATION PASSED')
print('Readiness:', summary['readiness_status'])
print('Checks run:', summary['checks_run'])
print('Critical failures:', summary['critical_failures'])
print('Warnings:', summary['warnings'])
print('Kernel installed:', summary['kernel_installed'])
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
from tower.penthouse_readiness import PenthouseReadiness

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
.penthouse{background:#5a3900;color:#ffe49a;border:1px solid #ffd45a}
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
<div class="panel"><h2>Penthouse Readiness</h2><pre id="penthouse_panel"></pre></div>
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
  let ph = await (await fetch("/api/penthouse_readiness")).json();
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
  row("PH","Reserved For Future QSB Kernel 4.5","socket ready","penthouse");
  s.floors.forEach(f => row(f.number, f.department, f.zone, floorClass(f)));
  row("G","Reception and Command Lobby","online","occupied");
  row("B1","Core Services","online","special");
  row("B2","Vault and Archives","online","special");
  row("B3","Disaster Recovery","online","special");

  health.textContent = JSON.stringify(s.counts,null,2);

  penthouse_panel.textContent = JSON.stringify({
    penthouse:ph.penthouse,
    reserved_for:ph.reserved_for,
    visible_message:ph.visible_message,
    readiness_status:ph.readiness_status,
    kernel_installed:ph.kernel_installed,
    kernel_logic_present:ph.kernel_logic_present,
    execution_enabled:ph.execution_enabled,
    checks_run:ph.checks_run,
    critical_failures:ph.critical_failures,
    warnings:ph.warnings,
    passed:ph.passed,
    socket_status:ph.socket.status,
    connection_ports:ph.connection_ports,
    discovery_interface:ph.discovery_interface,
    monitoring_interface:ph.monitoring_interface,
    floor_53_handoff:ph.floor_53_handoff,
    latest_acceptance_report:ph.latest_acceptance_report
  },null,2);

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
    warnings:infra.warnings
  },null,2);

  monitoring_floor.textContent = JSON.stringify({
    floor:mon.floor,
    department:mon.department,
    monitoring_status:mon.monitoring_status,
    dashboard_online:mon.dashboard_online,
    service_uptime_seconds:mon.service_uptime_seconds,
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

        if self.path.startswith("/api/penthouse_readiness"):
            return self.send_json(PenthouseReadiness().dashboard())
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
Penthouse Readiness V1.1

The Penthouse is now prepared as a future installation socket for QSB Kernel 4.5.

It includes:
- Kernel Installation Socket
- Kernel Discovery Interface
- Kernel Monitoring Interface
- Kernel Health Display
- Kernel Event Console
- Kernel Connection Ports
- Floor 53 to Penthouse handoff
- Emergency Stairwell route validation
- Security/Permissions pre-check
- Kernel occupancy acceptance report
- Dashboard panel showing: Reserved For Future QSB Kernel 4.5 Installation

This does not build or install the QSB Kernel.
Kernel installed remains false.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_penthouse_acceptance.sh
./scripts/penthouse_readiness_status.sh
python3 tests/test_penthouse_readiness_v11.py
"""

if "Penthouse Readiness V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Penthouse Readiness V1.1 installed.")
print("Run:")
print("./scripts/run_penthouse_acceptance.sh")
print("./scripts/penthouse_readiness_status.sh")
