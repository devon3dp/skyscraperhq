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

print("Installing Floor 36 Expansion Planning Department V1.1...")

for folder in [
    "floors/floor_36_expansion_planning_department/vacant_floor_registry",
    "floors/floor_36_expansion_planning_department/activation_hooks",
    "floors/floor_36_expansion_planning_department/future_department_plans",
    "floors/floor_36_expansion_planning_department/capacity_reports",
    "floors/floor_36_expansion_planning_department/utility_checks",
    "floors/floor_36_expansion_planning_department/lift_access_checks",
    "floors/floor_41_future_systems_vacant/activation_hook",
    "floors/floor_42_future_systems_vacant/activation_hook",
    "floors/floor_43_future_systems_vacant/activation_hook",
    "floors/floor_44_future_systems_vacant/activation_hook",
    "floors/floor_45_future_systems_vacant/activation_hook",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

expansion_policy = {
    "version": "1.1",
    "floor_id": "floor_36",
    "department": "Expansion Planning Department",
    "role": "vacant_floor_capacity_and_future_department_allocation_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "activation_execution_enabled": False,
    "principle": "Vacant floors are fully serviced expansion-ready spaces, not unfinished areas.",
    "managed_floors": ["floor_41", "floor_42", "floor_43", "floor_44", "floor_45"],
    "notice": "Floor 36 plans future occupancy. It does not activate departments automatically."
}

vacant_floors = [
    {
        "floor_id": "floor_41",
        "number": 41,
        "name": "Future Systems / Vacant",
        "zone": "ZONE C",
        "status": "vacant_ready",
        "activation_status": "ready_not_activated",
        "utilities": ["power", "storage", "network", "registry", "dashboard_visibility"],
        "lift_access": ["main_high_rise", "service_lift", "security_lift", "emergency_stairwell"],
        "activation_hook": "floors/floor_41_future_systems_vacant/activation_hook/activate_floor_41.json",
        "suggested_future_use": "Advanced Systems Department"
    },
    {
        "floor_id": "floor_42",
        "number": 42,
        "name": "Future Systems / Vacant",
        "zone": "ZONE C",
        "status": "vacant_ready",
        "activation_status": "ready_not_activated",
        "utilities": ["power", "storage", "network", "registry", "dashboard_visibility"],
        "lift_access": ["main_high_rise", "service_lift", "security_lift", "emergency_stairwell"],
        "activation_hook": "floors/floor_42_future_systems_vacant/activation_hook/activate_floor_42.json",
        "suggested_future_use": "Advanced Automation Department"
    },
    {
        "floor_id": "floor_43",
        "number": 43,
        "name": "Future Systems / Vacant",
        "zone": "ZONE C",
        "status": "vacant_ready",
        "activation_status": "ready_not_activated",
        "utilities": ["power", "storage", "network", "registry", "dashboard_visibility"],
        "lift_access": ["main_high_rise", "service_lift", "security_lift", "emergency_stairwell"],
        "activation_hook": "floors/floor_43_future_systems_vacant/activation_hook/activate_floor_43.json",
        "suggested_future_use": "Advanced Memory Department"
    },
    {
        "floor_id": "floor_44",
        "number": 44,
        "name": "Future Systems / Vacant",
        "zone": "ZONE C",
        "status": "vacant_ready",
        "activation_status": "ready_not_activated",
        "utilities": ["power", "storage", "network", "registry", "dashboard_visibility"],
        "lift_access": ["main_high_rise", "service_lift", "security_lift", "emergency_stairwell"],
        "activation_hook": "floors/floor_44_future_systems_vacant/activation_hook/activate_floor_44.json",
        "suggested_future_use": "Advanced Simulation Department"
    },
    {
        "floor_id": "floor_45",
        "number": 45,
        "name": "Future Systems / Vacant",
        "zone": "ZONE C",
        "status": "vacant_ready",
        "activation_status": "ready_not_activated",
        "utilities": ["power", "storage", "network", "registry", "dashboard_visibility"],
        "lift_access": ["main_high_rise", "executive_lift", "service_lift", "security_lift", "emergency_stairwell"],
        "activation_hook": "floors/floor_45_future_systems_vacant/activation_hook/activate_floor_45.json",
        "suggested_future_use": "Executive Expansion Buffer"
    }
]

future_department_blueprints = [
    {
        "blueprint_id": "advanced_systems_department",
        "preferred_floor": "floor_41",
        "department_name": "Advanced Systems Department",
        "activation_requires": ["floor_manifest_update", "worker_slot_allocation", "dashboard_visibility", "lift_permission_check"],
        "execution_enabled": False
    },
    {
        "blueprint_id": "advanced_automation_department",
        "preferred_floor": "floor_42",
        "department_name": "Advanced Automation Department",
        "activation_requires": ["floor_manifest_update", "worker_slot_allocation", "dashboard_visibility", "lift_permission_check"],
        "execution_enabled": False
    },
    {
        "blueprint_id": "advanced_memory_department",
        "preferred_floor": "floor_43",
        "department_name": "Advanced Memory Department",
        "activation_requires": ["floor_manifest_update", "worker_slot_allocation", "dashboard_visibility", "lift_permission_check"],
        "execution_enabled": False
    },
    {
        "blueprint_id": "advanced_simulation_department",
        "preferred_floor": "floor_44",
        "department_name": "Advanced Simulation Department",
        "activation_requires": ["floor_manifest_update", "worker_slot_allocation", "dashboard_visibility", "lift_permission_check"],
        "execution_enabled": False
    },
    {
        "blueprint_id": "executive_expansion_buffer",
        "preferred_floor": "floor_45",
        "department_name": "Executive Expansion Buffer",
        "activation_requires": ["floor_manifest_update", "executive_lift_check", "security_precheck", "dashboard_visibility"],
        "execution_enabled": False
    }
]

activation_hooks = []
for floor in vacant_floors:
    hook = {
        "hook_id": f"activate_{floor['floor_id']}",
        "floor_id": floor["floor_id"],
        "status": "registered_not_executable",
        "activation_execution_enabled": False,
        "requires_manual_approval": True,
        "required_checks": [
            "floor_exists",
            "floor_registered",
            "lift_access_ready",
            "utilities_ready",
            "security_spine_ready",
            "dashboard_visibility_ready"
        ],
        "notice": "Activation hook is a readiness record only. It does not modify the floor automatically."
    }
    activation_hooks.append(hook)
    write_json(floors_path := floor["activation_hook"], hook)

write_json("data/registries/expansion_policy.json", expansion_policy)
write_json("data/registries/vacant_floor_registry.json", vacant_floors)
write_json("data/registries/future_department_blueprints.json", future_department_blueprints)
write_json("data/registries/vacant_floor_activation_hooks.json", activation_hooks)

write_json("floors/floor_36_expansion_planning_department/floor_manifest.json", {
    "floor_id": "floor_36",
    "department": "Expansion Planning Department",
    "version": "1.1",
    "role": "vacant_floor_capacity_and_future_department_allocation_layer",
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "activation_execution_enabled": False,
    "hardwired_providers": False,
    "providers_are_external": True,
    "managed_vacant_floors": 5,
    "future_department_blueprints": len(future_department_blueprints),
    "activation_hooks": len(activation_hooks),
    "notice": "Floor 36 manages expansion planning for fully serviced vacant floors."
})

write_json("floors/floor_36_expansion_planning_department/vacant_floor_registry/vacant_floors.json", vacant_floors)
write_json("floors/floor_36_expansion_planning_department/future_department_plans/future_department_blueprints.json", future_department_blueprints)
write_json("floors/floor_36_expansion_planning_department/activation_hooks/activation_hooks.json", activation_hooks)

write("config/expansion_planning_department.yaml", """
expansion_planning_department:
  version: 1.1
  floor_id: floor_36
  role: vacant_floor_capacity_and_future_department_allocation_layer
  managed_vacant_floors:
    - floor_41
    - floor_42
    - floor_43
    - floor_44
    - floor_45
  execution_enabled: false
  activation_execution_enabled: false
  models_required: false
  kernel_required: false

principle: Vacant floors are fully serviced expansion-ready floors. They already have lift access, utilities, registry entries, dashboard visibility, and activation hooks.
""")

write("src/tower/expansion_planning.py", r'''
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
''')

write("scripts/expansion_planning_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.expansion_planning
""")

write("scripts/run_floor_36_expansion.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.expansion_planning import ExpansionPlanning
import json
dept = ExpansionPlanning()
report = dept.run_expansion_readiness()
print(json.dumps(report["summary"], indent=2))
print("Report written to: floors/floor_36_expansion_planning_department/capacity_reports/latest_expansion_readiness_report.json")
PY2
""")

write("scripts/prepare_vacant_floor_activation.py", """
import sys
import json
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.expansion_planning import ExpansionPlanning

floor_id = sys.argv[1] if len(sys.argv) > 1 else 'floor_41'
blueprint_id = sys.argv[2] if len(sys.argv) > 2 else None

dept = ExpansionPlanning()
print(json.dumps(dept.prepare_activation_plan(floor_id, blueprint_id), indent=2))
""")

for script in [
    "scripts/expansion_planning_status.sh",
    "scripts/run_floor_36_expansion.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_expansion_planning_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.expansion_planning import ExpansionPlanning

dept = ExpansionPlanning()
report = dept.run_expansion_readiness()
summary = report['summary']

assert summary['floor'] == 'floor_36'
assert summary['department'] == 'Expansion Planning Department'
assert summary['execution_enabled'] is False
assert summary['activation_execution_enabled'] is False
assert summary['managed_vacant_floors'] == 5
assert summary['future_department_blueprints'] >= 5
assert summary['activation_hooks'] >= 5
assert summary['checks_run'] >= 25
assert summary['critical_failures'] == 0, report

plan = dept.prepare_activation_plan('floor_41')
assert plan['floor_id'] == 'floor_41'
assert plan['status'] == 'prepared_not_executed'
assert plan['execution_enabled'] is False

dash = dept.dashboard()
assert dash['floor'] == 'floor_36'
assert dash['managed_vacant_floors'] == 5
assert len(dash['vacant_floors']) == 5

print('EXPANSION PLANNING V1.1 VALIDATION PASSED')
print('Status:', summary['status'])
print('Managed vacant floors:', summary['managed_vacant_floors'])
print('Checks run:', summary['checks_run'])
print('Critical failures:', summary['critical_failures'])
print('Warnings:', summary['warnings'])
""")

# Patch dashboard server to include Floor 36 Expansion Planning.
server = ROOT / "src" / "dashboard" / "server.py"
text = server.read_text(encoding="utf-8")

if "from tower.expansion_planning import ExpansionPlanning" not in text:
    marker = "from tower.security_spine import SecuritySpine"
    if marker in text:
        text = text.replace(marker, marker + "\nfrom tower.expansion_planning import ExpansionPlanning")
    else:
        text = text.replace("from tower.penthouse_readiness import PenthouseReadiness", "from tower.penthouse_readiness import PenthouseReadiness\nfrom tower.expansion_planning import ExpansionPlanning")

if ".expansion{" not in text:
    text = text.replace(
        ".infrastructure{background:#3d3b1b;border:1px solid #fff095}",
        ".infrastructure{background:#3d3b1b;border:1px solid #fff095}\n.expansion{background:#243d1b;border:1px solid #bcff95}"
    )

if 'if(f.id==="floor_36") return "expansion";' not in text:
    text = text.replace(
        'if(f.id==="floor_35") return "infrastructure";',
        'if(f.id==="floor_35") return "infrastructure";\n  if(f.id==="floor_36") return "expansion";'
    )

if '<div class="panel"><h2>Floor 36 Expansion Planning</h2><pre id="expansion_floor"></pre></div>' not in text:
    text = text.replace(
        '<div class="panel"><h2>Floor 35 Infrastructure Services</h2><pre id="infrastructure_floor"></pre></div>',
        '<div class="panel"><h2>Floor 36 Expansion Planning</h2><pre id="expansion_floor"></pre></div>\n<div class="panel"><h2>Floor 35 Infrastructure Services</h2><pre id="infrastructure_floor"></pre></div>'
    )

if 'let exp = await (await fetch("/api/expansion_planning")).json();' not in text:
    text = text.replace(
        'let infra = await (await fetch("/api/infrastructure_services")).json();',
        'let exp = await (await fetch("/api/expansion_planning")).json();\n  let infra = await (await fetch("/api/infrastructure_services")).json();'
    )

if "expansion_floor.textContent" not in text:
    text = text.replace(
        "infrastructure_floor.textContent = JSON.stringify({",
        """expansion_floor.textContent = JSON.stringify({
    floor:exp.floor,
    department:exp.department,
    expansion_status:exp.expansion_status,
    execution_enabled:exp.execution_enabled,
    activation_execution_enabled:exp.activation_execution_enabled,
    managed_vacant_floors:exp.managed_vacant_floors,
    future_department_blueprints:exp.future_department_blueprints,
    activation_hooks:exp.activation_hooks,
    checks_run:exp.checks_run,
    critical_failures:exp.critical_failures,
    warnings:exp.warnings,
    passed:exp.passed,
    vacant_floors:exp.vacant_floors.map(v => ({
      floor_id:v.floor_id,
      activation_status:v.activation_status,
      suggested_future_use:v.suggested_future_use,
      lift_access:v.lift_access
    })),
    latest_report:exp.latest_report
  },null,2);

  infrastructure_floor.textContent = JSON.stringify({"""
    )

if 'if self.path.startswith("/api/expansion_planning"):' not in text:
    text = text.replace(
        'if self.path.startswith("/api/security_spine"):',
        'if self.path.startswith("/api/expansion_planning"):\n            return self.send_json(ExpansionPlanning().dashboard())\n        if self.path.startswith("/api/security_spine"):'
    )

server.write_text(text, encoding="utf-8")

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Expansion Planning Department V1.1

Floor 36 now manages vacant expansion-ready floors 41-45.

It includes:
- Vacant floor registry
- Activation readiness checks
- Future department allocation planner
- Expansion hooks for floors 41-45
- Capacity report
- Service/lift/utility confirmation
- Dashboard panel showing expansion-ready floors

Vacant floors are fully serviced and ready for future departments.
Floor 36 does not activate departments automatically.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_floor_36_expansion.sh
./scripts/expansion_planning_status.sh
python3 scripts/prepare_vacant_floor_activation.py floor_41
python3 tests/test_expansion_planning_v11.py
"""

if "Expansion Planning Department V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Floor 36 Expansion Planning Department V1.1 installed.")
print("Run:")
print("./scripts/run_floor_36_expansion.sh")
print("./scripts/expansion_planning_status.sh")
