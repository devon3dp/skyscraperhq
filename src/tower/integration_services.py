from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "integration_services.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS integration_services (
    id TEXT PRIMARY KEY,
    name TEXT,
    source_floor TEXT,
    via_floor TEXT,
    target_floor TEXT,
    service_path_json TEXT,
    sealed_packets INTEGER,
    execution_enabled INTEGER,
    status TEXT,
    last_checked_ts TEXT
);

CREATE TABLE IF NOT EXISTS dependency_graph (
    component TEXT PRIMARY KEY,
    floor_id TEXT,
    depends_on_json TEXT,
    optional_depends_on_json TEXT,
    execution_enabled INTEGER,
    status TEXT
);

CREATE TABLE IF NOT EXISTS integration_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    event_type TEXT,
    service_id TEXT,
    status TEXT,
    details TEXT
);
"""

class IntegrationServices:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.sync()

    def policy(self):
        return load_json("integration_policy.json", {})

    def service_map_registry(self):
        return load_json("integration_service_map.json", [])

    def dependency_registry(self):
        return load_json("integration_dependency_graph.json", [])

    def readiness_checks(self):
        return load_json("integration_readiness_checks.json", [])

    def sync(self):
        for svc in self.service_map_registry():
            self.conn.execute(
                """
                INSERT OR REPLACE INTO integration_services
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    svc["id"],
                    svc["name"],
                    svc["source_floor"],
                    svc.get("via_floor"),
                    svc["target_floor"],
                    json.dumps(svc.get("service_path", [])),
                    int(bool(svc.get("sealed_packets", True))),
                    int(bool(svc.get("execution_enabled", False))),
                    svc.get("status", "unknown"),
                    now()
                )
            )

        for dep in self.dependency_registry():
            self.conn.execute(
                """
                INSERT OR REPLACE INTO dependency_graph
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    dep["component"],
                    dep["floor_id"],
                    json.dumps(dep.get("depends_on", [])),
                    json.dumps(dep.get("optional_depends_on", [])),
                    int(bool(dep.get("execution_enabled", False))),
                    "registered"
                )
            )

        self.conn.commit()

    def service_map(self):
        rows = self.conn.execute("SELECT * FROM integration_services ORDER BY id").fetchall()
        output = []
        for r in rows:
            item = dict(r)
            item["service_path"] = json.loads(item.pop("service_path_json"))
            item["sealed_packets"] = bool(item["sealed_packets"])
            item["execution_enabled"] = bool(item["execution_enabled"])
            output.append(item)
        return output

    def dependency_graph(self):
        rows = self.conn.execute("SELECT * FROM dependency_graph ORDER BY floor_id").fetchall()
        output = []
        for r in rows:
            item = dict(r)
            item["depends_on"] = json.loads(item.pop("depends_on_json"))
            item["optional_depends_on"] = json.loads(item.pop("optional_depends_on_json"))
            item["execution_enabled"] = bool(item["execution_enabled"])
            output.append(item)
        return output

    def run_readiness_checks(self):
        results = []
        for check in self.readiness_checks():
            required = ROOT / check["required_file"]
            ok = required.exists()
            results.append({
                "id": check["id"],
                "description": check["description"],
                "required_file": check["required_file"],
                "ok": ok,
                "status": "pass" if ok else "missing"
            })

        self.conn.execute(
            "INSERT INTO integration_events(ts, event_type, service_id, status, details) VALUES (?, ?, ?, ?, ?)",
            (now(), "readiness_checks", "all", "complete", json.dumps(results))
        )
        self.conn.commit()
        return results

    def prepare_integration_handoff(self, service_id, details=None):
        details = details or {}
        service = None
        for svc in self.service_map():
            if svc["id"] == service_id:
                service = svc
                break

        if service is None:
            status = "unknown_service"
            event_details = {"service_id": service_id, "error": "service not found", **details}
        else:
            status = "prepared_not_executed"
            event_details = {
                "service": service,
                "execution_enabled": False,
                "routing_only": True,
                **details
            }

        self.conn.execute(
            "INSERT INTO integration_events(ts, event_type, service_id, status, details) VALUES (?, ?, ?, ?, ?)",
            (now(), "prepare_integration_handoff", service_id, status, json.dumps(event_details))
        )
        self.conn.commit()

        return {
            "service_id": service_id,
            "status": status,
            "execution_enabled": False,
            "details": event_details
        }

    def refresh_health(self):
        checks = self.run_readiness_checks()
        missing = [c for c in checks if not c["ok"]]
        status = "healthy" if not missing else "degraded"

        self.conn.execute(
            "INSERT INTO integration_events(ts, event_type, service_id, status, details) VALUES (?, ?, ?, ?, ?)",
            (now(), "integration_health_refresh", "floor_22", status, json.dumps({"missing": missing}))
        )
        self.conn.commit()

        return {
            "status": status,
            "checks": checks,
            "missing_count": len(missing),
            "execution_enabled": False
        }

    def recent_events(self, limit=20):
        rows = self.conn.execute("SELECT * FROM integration_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        self.sync()
        services = self.service_map()
        deps = self.dependency_graph()
        checks = self.run_readiness_checks()
        missing = [c for c in checks if not c["ok"]]

        return {
            "database": str(DB),
            "floor": "floor_22",
            "department": "Integration Services Department",
            "version": "1.1",
            "role": "cross_floor_service_integration_layer",
            "execution_enabled": False,
            "hardwired_providers": False,
            "models_required": False,
            "kernel_required": False,
            "providers_are_external": True,
            "integration_health": "healthy" if not missing else "degraded",
            "service_paths": len(services),
            "dependency_records": len(deps),
            "readiness_checks": checks,
            "service_map": services,
            "dependency_graph": deps,
            "recent_events": self.recent_events(10),
            "policy": self.policy()
        }

if __name__ == "__main__":
    print(json.dumps(IntegrationServices().dashboard(), indent=2))
