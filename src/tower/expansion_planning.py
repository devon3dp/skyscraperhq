from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "expansion_planning.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_registry(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS expansion_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    check_type TEXT,
    floor_id TEXT,
    status TEXT,
    severity TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS activation_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    floor_id TEXT,
    blueprint_id TEXT,
    status TEXT,
    execution_enabled INTEGER,
    details TEXT
);
"""

class ExpansionPlanning:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policy(self):
        return load_registry("expansion_policy.json", {})

    def vacant_floors(self):
        return load_registry("vacant_floor_registry.json", [])

    def blueprints(self):
        return load_registry("future_department_blueprints.json", [])

    def hooks(self):
        return load_registry("vacant_floor_activation_hooks.json", [])

    def check(self, check_type, floor_id, ok, severity="critical", message="", details=None):
        item = {
            "check_type": check_type,
            "floor_id": floor_id,
            "status": "pass" if ok else "fail",
            "severity": severity,
            "message": message,
            "details": details or {}
        }
        self.conn.execute(
            "INSERT INTO expansion_checks(ts, check_type, floor_id, status, severity, details) VALUES (?, ?, ?, ?, ?, ?)",
            (now(), check_type, floor_id, item["status"], severity, json.dumps(item))
        )
        self.conn.commit()
        return item

    def validate_vacant_floor_registry(self):
        items = []
        floors = self.vacant_floors()

        items.append(self.check(
            "vacant_floor_count",
            "all",
            len(floors) == 5,
            "critical",
            f"Vacant floors registered: {len(floors)}.",
            {"expected": 5, "actual": len(floors)}
        ))

        expected = {f"floor_{i:02d}" for i in range(41, 46)}
        actual = {f.get("floor_id") for f in floors}

        items.append(self.check(
            "vacant_floor_ids",
            "all",
            expected == actual,
            "critical",
            "Vacant floor IDs match expected 41-45.",
            {"expected": sorted(expected), "actual": sorted(actual)}
        ))

        return items

    def validate_floor_directories(self):
        items = []
        folder_map = {
            "floor_41": "floors/floor_41_future_systems_vacant",
            "floor_42": "floors/floor_42_future_systems_vacant",
            "floor_43": "floors/floor_43_future_systems_vacant",
            "floor_44": "floors/floor_44_future_systems_vacant",
            "floor_45": "floors/floor_45_future_systems_vacant"
        }

        for floor_id, rel in folder_map.items():
            path = ROOT / rel
            items.append(self.check(
                "floor_directory",
                floor_id,
                path.exists(),
                "critical",
                f"{floor_id} directory exists." if path.exists() else f"{floor_id} directory missing.",
                {"path": rel}
            ))

        return items

    def validate_floor_registry_alignment(self):
        items = []
        try:
            from tower.registry import Registry
            floors = Registry().floors()
            by_id = {f.get("id"): f for f in floors}
            for floor in self.vacant_floors():
                floor_id = floor["floor_id"]
                reg = by_id.get(floor_id)
                ok = bool(reg and reg.get("vacant") is True and reg.get("status") == "vacant_ready")
                items.append(self.check(
                    "floor_registry_alignment",
                    floor_id,
                    ok,
                    "critical",
                    f"{floor_id} registry alignment checked.",
                    {"registry_record": reg}
                ))
        except Exception as e:
            items.append(self.check("floor_registry_alignment", "all", False, "critical", str(e)))

        return items

    def validate_lift_access(self):
        items = []
        try:
            from tower.registry import Registry
            lifts = Registry().lifts()
            lift_ids = {l.get("id") for l in lifts}

            for floor in self.vacant_floors():
                floor_id = floor["floor_id"]
                required = set(floor.get("lift_access", []))
                missing = sorted(required - lift_ids)
                items.append(self.check(
                    "lift_access_registry",
                    floor_id,
                    not missing,
                    "critical",
                    f"{floor_id} lift access registry checked.",
                    {"required": sorted(required), "missing": missing}
                ))

        except Exception as e:
            items.append(self.check("lift_access_registry", "all", False, "critical", str(e)))

        return items

    def validate_utilities(self):
        items = []
        required = {"power", "storage", "network", "registry", "dashboard_visibility"}

        for floor in self.vacant_floors():
            floor_id = floor["floor_id"]
            utilities = set(floor.get("utilities", []))
            missing = sorted(required - utilities)
            items.append(self.check(
                "utility_readiness",
                floor_id,
                not missing,
                "critical",
                f"{floor_id} utilities checked.",
                {"required": sorted(required), "available": sorted(utilities), "missing": missing}
            ))

        return items

    def validate_activation_hooks(self):
        items = []
        hooks = self.hooks()
        hooks_by_floor = {h.get("floor_id"): h for h in hooks}

        for floor in self.vacant_floors():
            floor_id = floor["floor_id"]
            hook = hooks_by_floor.get(floor_id)
            hook_path = ROOT / floor["activation_hook"]
            ok = bool(
                hook and
                hook.get("activation_execution_enabled") is False and
                hook_path.exists()
            )
            items.append(self.check(
                "activation_hook",
                floor_id,
                ok,
                "critical",
                f"{floor_id} activation hook registered and non-executable.",
                {"hook": hook, "hook_path": floor["activation_hook"], "hook_file_exists": hook_path.exists()}
            ))

        return items

    def validate_security_spine_reference(self):
        items = []
        try:
            from tower.security_spine import SecuritySpine
            sec = SecuritySpine().dashboard()
            ok = sec.get("status") in ["healthy", "degraded"] and sec.get("enforcement_enabled") is False
            items.append(self.check(
                "security_spine_reference",
                "all",
                ok,
                "warning",
                f"Security spine reachable with status {sec.get('status')}.",
                {"status": sec.get("status"), "enforcement_enabled": sec.get("enforcement_enabled")}
            ))
        except Exception as e:
            items.append(self.check("security_spine_reference", "all", False, "warning", str(e)))

        return items

    def capacity_report(self):
        floors = self.vacant_floors()
        blueprints = self.blueprints()
        ready = [f for f in floors if f.get("activation_status") == "ready_not_activated"]

        report = {
            "ts": now(),
            "floor": "floor_36",
            "department": "Expansion Planning Department",
            "version": "1.1",
            "managed_vacant_floors": len(floors),
            "ready_vacant_floors": len(ready),
            "future_department_blueprints": len(blueprints),
            "activation_execution_enabled": False,
            "suggested_allocations": [
                {
                    "floor_id": f["floor_id"],
                    "suggested_future_use": f["suggested_future_use"],
                    "activation_status": f["activation_status"]
                }
                for f in floors
            ]
        }

        out = ROOT / "floors" / "floor_36_expansion_planning_department" / "capacity_reports" / "latest_capacity_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return report

    def prepare_activation_plan(self, floor_id, blueprint_id=None):
        floor = next((f for f in self.vacant_floors() if f.get("floor_id") == floor_id), None)
        if not floor:
            status = "unknown_floor"
            details = {"floor_id": floor_id}
        else:
            if blueprint_id is None:
                bp = next((b for b in self.blueprints() if b.get("preferred_floor") == floor_id), None)
            else:
                bp = next((b for b in self.blueprints() if b.get("blueprint_id") == blueprint_id), None)

            status = "prepared_not_executed"
            details = {
                "floor": floor,
                "blueprint": bp,
                "activation_execution_enabled": False,
                "requires_manual_approval": True,
                "message": "Activation plan prepared only. No floor modification executed."
            }
            blueprint_id = bp.get("blueprint_id") if bp else blueprint_id

        self.conn.execute(
            "INSERT INTO activation_plans(ts, floor_id, blueprint_id, status, execution_enabled, details) VALUES (?, ?, ?, ?, ?, ?)",
            (now(), floor_id, blueprint_id, status, 0, json.dumps(details))
        )
        self.conn.commit()

        return {
            "floor_id": floor_id,
            "blueprint_id": blueprint_id,
            "status": status,
            "execution_enabled": False,
            "details": details
        }

    def run_expansion_readiness(self):
        items = []
        items.extend(self.validate_vacant_floor_registry())
        items.extend(self.validate_floor_directories())
        items.extend(self.validate_floor_registry_alignment())
        items.extend(self.validate_lift_access())
        items.extend(self.validate_utilities())
        items.extend(self.validate_activation_hooks())
        items.extend(self.validate_security_spine_reference())

        critical_failures = len([i for i in items if i["status"] == "fail" and i["severity"] == "critical"])
        warnings = len([i for i in items if i["status"] == "fail" and i["severity"] == "warning"])

        status = "healthy" if critical_failures == 0 and warnings == 0 else "degraded" if critical_failures == 0 else "critical"

        report = {
            "summary": {
                "ts": now(),
                "floor": "floor_36",
                "department": "Expansion Planning Department",
                "version": "1.1",
                "status": status,
                "execution_enabled": False,
                "activation_execution_enabled": False,
                "managed_vacant_floors": len(self.vacant_floors()),
                "future_department_blueprints": len(self.blueprints()),
                "activation_hooks": len(self.hooks()),
                "checks_run": len(items),
                "critical_failures": critical_failures,
                "warnings": warnings,
                "passed": len([i for i in items if i["status"] == "pass"])
            },
            "items": items,
            "capacity_report": self.capacity_report()
        }

        out = ROOT / "floors" / "floor_36_expansion_planning_department" / "capacity_reports" / "latest_expansion_readiness_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return report

    def recent_checks(self, limit=30):
        rows = self.conn.execute("SELECT * FROM expansion_checks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def recent_activation_plans(self, limit=10):
        rows = self.conn.execute("SELECT * FROM activation_plans ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        report = self.run_expansion_readiness()
        summary = report["summary"]

        return {
            "database": str(DB),
            "floor": "floor_36",
            "department": "Expansion Planning Department",
            "version": "1.1",
            "expansion_status": summary["status"],
            "execution_enabled": False,
            "activation_execution_enabled": False,
            "managed_vacant_floors": summary["managed_vacant_floors"],
            "future_department_blueprints": summary["future_department_blueprints"],
            "activation_hooks": summary["activation_hooks"],
            "checks_run": summary["checks_run"],
            "critical_failures": summary["critical_failures"],
            "warnings": summary["warnings"],
            "passed": summary["passed"],
            "vacant_floors": self.vacant_floors(),
            "capacity_report": report["capacity_report"],
            "latest_report": "floors/floor_36_expansion_planning_department/capacity_reports/latest_expansion_readiness_report.json",
            "recent_checks": self.recent_checks(10),
            "recent_activation_plans": self.recent_activation_plans(10),
            "policy": self.policy()
        }

if __name__ == "__main__":
    print(json.dumps(ExpansionPlanning().dashboard(), indent=2))
