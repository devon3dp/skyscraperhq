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
