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
