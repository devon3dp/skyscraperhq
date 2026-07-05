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
