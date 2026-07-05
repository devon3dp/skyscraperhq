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

print("Installing Security Spine V1.1: Floors 28-32...")

for folder in [
    "floors/floor_28_security_department/access_gates",
    "floors/floor_28_security_department/security_events",
    "floors/floor_29_guardian_department/guardian_rules",
    "floors/floor_29_guardian_department/guardian_events",
    "floors/floor_30_permissions_department/roles",
    "floors/floor_30_permissions_department/lift_permissions",
    "floors/floor_31_audit_department/audit_log",
    "floors/floor_31_audit_department/trace_records",
    "floors/floor_32_compliance_department/compliance_rules",
    "floors/floor_32_compliance_department/compliance_reports",
    "data/registries",
    "data/db",
    "scripts",
    "tests",
    "src/tower"
]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

security_policy = {
    "version": "1.1",
    "spine_id": "security_spine",
    "floors": ["floor_28", "floor_29", "floor_30", "floor_31", "floor_32"],
    "kernel_required": False,
    "models_required": False,
    "execution_enabled": False,
    "enforcement_enabled": False,
    "mode": "readiness_and_recording",
    "principle": "The Security Spine prepares gates, permissions, audit, and compliance before future kernel occupancy. It does not execute actions or enforce live blocking yet.",
    "notice": "Security is registered and visible. Enforcement remains disabled until explicitly activated later."
}

security_gates = [
    {
        "id": "penthouse_gate",
        "name": "Penthouse Access Gate",
        "floor": "floor_28",
        "protects": "penthouse",
        "status": "ready_not_enforcing",
        "requires": ["permissions_check", "guardian_check", "audit_record"],
        "enforcement_enabled": False
    },
    {
        "id": "model_lift_gate",
        "name": "Model Lift Gate",
        "floor": "floor_28",
        "protects": "model_lift",
        "status": "ready_not_enforcing",
        "requires": ["sealed_packet", "route_permission", "audit_record"],
        "enforcement_enabled": False
    },
    {
        "id": "external_provider_gate",
        "name": "External Provider Gate",
        "floor": "floor_28",
        "protects": "floor_23_and_roof",
        "status": "ready_not_enforcing",
        "requires": ["adapter_permission", "provider_socket_permission", "audit_record"],
        "enforcement_enabled": False
    },
    {
        "id": "service_lift_gate",
        "name": "Service Lift Gate",
        "floor": "floor_28",
        "protects": "service_lift",
        "status": "ready_not_enforcing",
        "requires": ["maintenance_permission", "audit_record"],
        "enforcement_enabled": False
    }
]

guardian_rules = [
    {
        "id": "no_kernel_logic_before_installation",
        "floor": "floor_29",
        "rule": "Kernel files must not exist before official QSB Kernel 4.5 installation.",
        "severity": "critical",
        "status": "active_readiness_rule",
        "enforcement_enabled": False
    },
    {
        "id": "no_provider_execution",
        "floor": "floor_29",
        "rule": "External provider execution remains disabled.",
        "severity": "critical",
        "status": "active_readiness_rule",
        "enforcement_enabled": False
    },
    {
        "id": "no_model_execution_required",
        "floor": "floor_29",
        "rule": "The building must run without local or external models.",
        "severity": "critical",
        "status": "active_readiness_rule",
        "enforcement_enabled": False
    },
    {
        "id": "sealed_packet_integrity",
        "floor": "floor_29",
        "rule": "Inter-floor communication must travel through lifts as sealed packets.",
        "severity": "critical",
        "status": "active_readiness_rule",
        "enforcement_enabled": False
    },
    {
        "id": "emergency_stairwell_available",
        "floor": "floor_29",
        "rule": "Emergency Stairwell must remain available from Penthouse to Basement.",
        "severity": "critical",
        "status": "active_readiness_rule",
        "enforcement_enabled": False
    }
]

permission_roles = [
    {
        "id": "building_admin",
        "floor": "floor_30",
        "name": "Building Admin",
        "permissions": ["view_all", "run_diagnostics", "run_monitoring", "view_infrastructure", "view_penthouse_readiness"],
        "execution_enabled": False
    },
    {
        "id": "tower_operator",
        "floor": "floor_30",
        "name": "Tower Operator",
        "permissions": ["view_dashboard", "view_lifts", "view_packets", "view_floor_status"],
        "execution_enabled": False
    },
    {
        "id": "future_kernel",
        "floor": "floor_30",
        "name": "Future QSB Kernel 4.5",
        "permissions": ["discover_registries", "read_lift_network", "read_floor_map", "write_kernel_events"],
        "activation_required": True,
        "currently_active": False,
        "execution_enabled": False
    },
    {
        "id": "external_provider",
        "floor": "floor_30",
        "name": "External Provider Tenant",
        "permissions": ["receive_provider_packet_only"],
        "currently_active": False,
        "execution_enabled": False
    }
]

lift_permissions = [
    {"lift": "main_low_rise", "allowed_zones": ["ZONE A"], "sealed_packets_required": True},
    {"lift": "main_mid_rise", "allowed_zones": ["ZONE A", "ZONE B"], "sealed_packets_required": True},
    {"lift": "main_high_rise", "allowed_zones": ["ZONE B", "ZONE C"], "sealed_packets_required": True},
    {"lift": "executive_lift", "allowed_zones": ["ZONE D", "penthouse"], "sealed_packets_required": True},
    {"lift": "service_lift", "allowed_zones": ["all"], "sealed_packets_required": True},
    {"lift": "memory_lift", "allowed_zones": ["selected_memory_archive_floors"], "sealed_packets_required": True},
    {"lift": "model_lift", "allowed_zones": ["floor_21", "floor_23", "floor_24", "floor_26", "floor_27", "roof"], "sealed_packets_required": True},
    {"lift": "security_lift", "allowed_zones": ["all_security_controlled"], "sealed_packets_required": True},
    {"lift": "emergency_stairwell", "allowed_zones": ["all"], "sealed_packets_required": False}
]

audit_policy = {
    "version": "1.1",
    "floor_id": "floor_31",
    "department": "Audit Department",
    "records": [
        "security spine boot",
        "readiness checks",
        "permission checks",
        "guardian checks",
        "compliance checks",
        "penthouse readiness references"
    ],
    "execution_enabled": False
}

compliance_rules = [
    {
        "id": "kernel_not_installed",
        "floor": "floor_32",
        "rule": "Kernel installed must remain false until official installation.",
        "required_value": False,
        "status": "active"
    },
    {
        "id": "execution_disabled",
        "floor": "floor_32",
        "rule": "Execution must remain disabled in readiness layers.",
        "required_value": False,
        "status": "active"
    },
    {
        "id": "providers_external",
        "floor": "floor_32",
        "rule": "External providers remain outside the building infrastructure.",
        "required_value": True,
        "status": "active"
    },
    {
        "id": "building_runs_without_models",
        "floor": "floor_32",
        "rule": "Building must run without AI models connected.",
        "required_value": True,
        "status": "active"
    },
    {
        "id": "penthouse_reserved_message",
        "floor": "floor_32",
        "rule": "Penthouse must display Reserved For Future QSB Kernel 4.5 Installation.",
        "required_value": "Reserved For Future QSB Kernel 4.5 Installation",
        "status": "active"
    }
]

write_json("data/registries/security_spine_policy.json", security_policy)
write_json("data/registries/security_gates.json", security_gates)
write_json("data/registries/guardian_rules.json", guardian_rules)
write_json("data/registries/permission_roles.json", permission_roles)
write_json("data/registries/lift_permissions.json", lift_permissions)
write_json("data/registries/audit_policy.json", audit_policy)
write_json("data/registries/compliance_rules.json", compliance_rules)

floor_manifests = [
    ("floor_28_security_department", "floor_28", "Security Department", "access_control_and_security_gate_layer"),
    ("floor_29_guardian_department", "floor_29", "Guardian Department", "safety_guardian_and_blocking_readiness_layer"),
    ("floor_30_permissions_department", "floor_30", "Permissions Department", "role_and_permission_registry_layer"),
    ("floor_31_audit_department", "floor_31", "Audit Department", "traceability_and_audit_record_layer"),
    ("floor_32_compliance_department", "floor_32", "Compliance Department", "rules_and_governance_validation_layer")
]

for folder, floor_id, dept, role in floor_manifests:
    write_json(f"floors/{folder}/floor_manifest.json", {
        "floor_id": floor_id,
        "department": dept,
        "version": "1.1",
        "role": role,
        "kernel_required": False,
        "models_required": False,
        "execution_enabled": False,
        "enforcement_enabled": False,
        "hardwired_providers": False,
        "providers_are_external": True,
        "notice": f"{dept} registered as part of Security Spine V1.1."
    })

write_json("floors/floor_28_security_department/access_gates/security_gates.json", security_gates)
write_json("floors/floor_29_guardian_department/guardian_rules/guardian_rules.json", guardian_rules)
write_json("floors/floor_30_permissions_department/roles/permission_roles.json", permission_roles)
write_json("floors/floor_30_permissions_department/lift_permissions/lift_permissions.json", lift_permissions)
write_json("floors/floor_31_audit_department/audit_log/audit_policy.json", audit_policy)
write_json("floors/floor_32_compliance_department/compliance_rules/compliance_rules.json", compliance_rules)

write("config/security_spine.yaml", """
security_spine:
  version: 1.1
  floors:
    - floor_28_security_department
    - floor_29_guardian_department
    - floor_30_permissions_department
    - floor_31_audit_department
    - floor_32_compliance_department
  execution_enabled: false
  enforcement_enabled: false
  models_required: false
  kernel_required: false
  providers_are_external: true

principle: Security Spine prepares gates, permissions, guardian checks, audit records, and compliance rules before future kernel occupancy. Enforcement remains disabled until explicitly activated later.
""")

write("src/tower/security_spine.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "security_spine.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_registry(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    floor_id TEXT,
    event_type TEXT,
    status TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS audit_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    source TEXT,
    action TEXT,
    status TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS compliance_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    status TEXT,
    checks_run INTEGER,
    failures INTEGER,
    warnings INTEGER,
    summary_json TEXT
);
"""

class SecuritySpine:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policy(self):
        return load_registry("security_spine_policy.json", {})

    def gates(self):
        return load_registry("security_gates.json", [])

    def guardian_rules(self):
        return load_registry("guardian_rules.json", [])

    def permission_roles(self):
        return load_registry("permission_roles.json", [])

    def lift_permissions(self):
        return load_registry("lift_permissions.json", [])

    def compliance_rules(self):
        return load_registry("compliance_rules.json", [])

    def record_security_event(self, floor_id, event_type, status, details):
        self.conn.execute(
            "INSERT INTO security_events(ts, floor_id, event_type, status, details) VALUES (?, ?, ?, ?, ?)",
            (now(), floor_id, event_type, status, json.dumps(details))
        )
        self.conn.commit()

    def audit(self, source, action, status, details):
        self.conn.execute(
            "INSERT INTO audit_records(ts, source, action, status, details) VALUES (?, ?, ?, ?, ?)",
            (now(), source, action, status, json.dumps(details))
        )
        self.conn.commit()

        line = json.dumps({
            "ts": now(),
            "source": source,
            "action": action,
            "status": status,
            "details": details
        })
        audit_path = ROOT / "floors" / "floor_31_audit_department" / "audit_log" / "audit.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def check(self, name, ok, severity="critical", message="", details=None):
        return {
            "name": name,
            "status": "pass" if ok else "fail",
            "severity": severity,
            "message": message,
            "details": details or {}
        }

    def floor_manifest_checks(self):
        expected = [
            ("floor_28", "floors/floor_28_security_department/floor_manifest.json"),
            ("floor_29", "floors/floor_29_guardian_department/floor_manifest.json"),
            ("floor_30", "floors/floor_30_permissions_department/floor_manifest.json"),
            ("floor_31", "floors/floor_31_audit_department/floor_manifest.json"),
            ("floor_32", "floors/floor_32_compliance_department/floor_manifest.json")
        ]

        items = []
        for floor_id, rel in expected:
            p = ROOT / rel
            ok = p.exists()
            details = {"path": rel}
            if ok:
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    details["floor_id"] = data.get("floor_id")
                    details["execution_enabled"] = data.get("execution_enabled")
                    details["enforcement_enabled"] = data.get("enforcement_enabled")
                    ok = data.get("floor_id") == floor_id and data.get("execution_enabled") is False
                except Exception as e:
                    ok = False
                    details["error"] = str(e)

            items.append(self.check(
                f"{floor_id}_manifest",
                ok,
                "critical",
                f"{floor_id} manifest valid." if ok else f"{floor_id} manifest invalid or missing.",
                details
            ))

        return items

    def gate_checks(self):
        gates = self.gates()
        disabled = [g for g in gates if g.get("enforcement_enabled") is False]
        return [
            self.check("security_gates_registered", len(gates) >= 4, "critical", f"Security gates registered: {len(gates)}."),
            self.check("security_enforcement_disabled", len(disabled) == len(gates), "critical", "Security enforcement disabled as required.", {"gates": len(gates), "disabled": len(disabled)})
        ]

    def guardian_checks(self):
        rules = self.guardian_rules()
        disabled = [r for r in rules if r.get("enforcement_enabled") is False]
        return [
            self.check("guardian_rules_registered", len(rules) >= 5, "critical", f"Guardian rules registered: {len(rules)}."),
            self.check("guardian_enforcement_disabled", len(disabled) == len(rules), "critical", "Guardian enforcement disabled as required.", {"rules": len(rules), "disabled": len(disabled)})
        ]

    def permission_checks(self):
        roles = self.permission_roles()
        future_kernel = [r for r in roles if r.get("id") == "future_kernel"]
        future_kernel_inactive = future_kernel and future_kernel[0].get("currently_active") is False

        lifts = self.lift_permissions()
        sealed = [x for x in lifts if x.get("sealed_packets_required") is True]

        return [
            self.check("permission_roles_registered", len(roles) >= 4, "critical", f"Permission roles registered: {len(roles)}."),
            self.check("future_kernel_role_inactive", bool(future_kernel_inactive), "critical", "Future kernel role exists but is inactive.", {"future_kernel": future_kernel}),
            self.check("lift_permissions_registered", len(lifts) >= 9, "critical", f"Lift permission records registered: {len(lifts)}."),
            self.check("sealed_packet_policy_present", len(sealed) >= 8, "warning", f"Sealed packet policy records: {len(sealed)}.")
        ]

    def compliance_checks(self):
        rules = self.compliance_rules()
        items = [
            self.check("compliance_rules_registered", len(rules) >= 5, "critical", f"Compliance rules registered: {len(rules)}.")
        ]

        try:
            from tower.penthouse_readiness import PenthouseReadiness
            ph = PenthouseReadiness().dashboard()

            items.append(self.check(
                "penthouse_kernel_not_installed",
                ph.get("kernel_installed") is False,
                "critical",
                "Penthouse confirms kernel_installed false.",
                {"kernel_installed": ph.get("kernel_installed")}
            ))

            items.append(self.check(
                "penthouse_kernel_logic_absent",
                ph.get("kernel_logic_present") is False,
                "critical",
                "Penthouse confirms kernel_logic_present false.",
                {"kernel_logic_present": ph.get("kernel_logic_present")}
            ))

            items.append(self.check(
                "penthouse_reserved_message",
                ph.get("visible_message") == "Reserved For Future QSB Kernel 4.5 Installation",
                "critical",
                "Penthouse reserved message is correct.",
                {"visible_message": ph.get("visible_message")}
            ))

        except Exception as e:
            items.append(self.check("penthouse_compliance_reference", False, "critical", str(e)))

        try:
            from tower.infrastructure_services import InfrastructureServices
            infra = InfrastructureServices().dashboard()
            items.append(self.check(
                "infrastructure_healthy_or_degraded",
                infra.get("infrastructure_status") in ["healthy", "degraded"],
                "warning",
                f"Infrastructure status: {infra.get('infrastructure_status')}.",
                {"status": infra.get("infrastructure_status")}
            ))
        except Exception as e:
            items.append(self.check("infrastructure_compliance_reference", False, "warning", str(e)))

        return items

    def lift_security_checks(self):
        items = []
        try:
            from tower.lifts import LiftNetwork
            net = LiftNetwork()

            routes = [
                ("floor_24", "floor_27", "model_lift"),
                ("floor_05", "floor_24", "service_lift"),
                ("floor_53", "penthouse", "executive_lift"),
                ("penthouse", "B1", "emergency_stairwell"),
                ("floor_28", "penthouse", "security_lift")
            ]

            for source, target, expected in routes:
                try:
                    lift = net.choose(source, target, expected)
                    items.append(self.check(
                        f"secure_route_{source}_to_{target}",
                        lift.get("id") == expected,
                        "critical" if expected in ["model_lift", "security_lift", "emergency_stairwell"] else "warning",
                        f"Expected {expected}, selected {lift.get('id')}.",
                        {"source": source, "target": target, "expected": expected, "selected": lift}
                    ))
                except Exception as e:
                    items.append(self.check(f"secure_route_{source}_to_{target}", False, "critical", str(e)))

        except Exception as e:
            items.append(self.check("lift_security_access", False, "critical", str(e)))

        return items

    def run_security_spine_check(self):
        items = []
        items.extend(self.floor_manifest_checks())
        items.extend(self.gate_checks())
        items.extend(self.guardian_checks())
        items.extend(self.permission_checks())
        items.extend(self.compliance_checks())
        items.extend(self.lift_security_checks())

        failures = len([x for x in items if x["status"] == "fail" and x["severity"] == "critical"])
        warnings = len([x for x in items if x["status"] == "fail" and x["severity"] == "warning"])

        status = "healthy" if failures == 0 and warnings == 0 else "degraded" if failures == 0 else "critical"

        summary = {
            "ts": now(),
            "spine": "security_spine",
            "version": "1.1",
            "status": status,
            "floors": ["floor_28", "floor_29", "floor_30", "floor_31", "floor_32"],
            "execution_enabled": False,
            "enforcement_enabled": False,
            "checks_run": len(items),
            "critical_failures": failures,
            "warnings": warnings,
            "passed": len([x for x in items if x["status"] == "pass"])
        }

        self.conn.execute(
            """
            INSERT INTO compliance_runs
            (ts, status, checks_run, failures, warnings, summary_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (summary["ts"], status, len(items), failures, warnings, json.dumps(summary))
        )
        self.conn.commit()

        self.record_security_event("floor_28", "security_spine_check", status, summary)
        self.audit("security_spine", "run_security_spine_check", status, summary)

        report = {
            "summary": summary,
            "items": items
        }

        report_path = ROOT / "floors" / "floor_32_compliance_department" / "compliance_reports" / "latest_security_spine_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return report

    def recent_security_events(self, limit=20):
        rows = self.conn.execute("SELECT * FROM security_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def recent_audit_records(self, limit=20):
        rows = self.conn.execute("SELECT * FROM audit_records ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def recent_compliance_runs(self, limit=10):
        rows = self.conn.execute("SELECT * FROM compliance_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        output = []
        for r in rows:
            item = dict(r)
            try:
                item["summary"] = json.loads(item.pop("summary_json"))
            except Exception:
                pass
            output.append(item)
        return output

    def dashboard(self):
        report = self.run_security_spine_check()
        summary = report["summary"]
        return {
            "database": str(DB),
            "spine": "security_spine",
            "department": "Security Spine",
            "version": "1.1",
            "status": summary["status"],
            "floors": summary["floors"],
            "execution_enabled": False,
            "enforcement_enabled": False,
            "security_gates": len(self.gates()),
            "guardian_rules": len(self.guardian_rules()),
            "permission_roles": len(self.permission_roles()),
            "lift_permissions": len(self.lift_permissions()),
            "compliance_rules": len(self.compliance_rules()),
            "checks_run": summary["checks_run"],
            "critical_failures": summary["critical_failures"],
            "warnings": summary["warnings"],
            "passed": summary["passed"],
            "latest_report": "floors/floor_32_compliance_department/compliance_reports/latest_security_spine_report.json",
            "recent_security_events": self.recent_security_events(10),
            "recent_audit_records": self.recent_audit_records(10),
            "recent_compliance_runs": self.recent_compliance_runs(5),
            "policy": self.policy()
        }

if __name__ == "__main__":
    print(json.dumps(SecuritySpine().dashboard(), indent=2))
''')

write("scripts/security_spine_status.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 -m tower.security_spine
""")

write("scripts/run_security_spine_check.sh", """
#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.security_spine import SecuritySpine
import json
spine = SecuritySpine()
report = spine.run_security_spine_check()
print(json.dumps(report["summary"], indent=2))
print("Report written to: floors/floor_32_compliance_department/compliance_reports/latest_security_spine_report.json")
PY2
""")

for script in [
    "scripts/security_spine_status.sh",
    "scripts/run_security_spine_check.sh"
]:
    os.chmod(ROOT / script, 0o755)

write("tests/test_security_spine_v11.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.security_spine import SecuritySpine

spine = SecuritySpine()
report = spine.run_security_spine_check()
summary = report['summary']

assert summary['spine'] == 'security_spine'
assert summary['execution_enabled'] is False
assert summary['enforcement_enabled'] is False
assert summary['checks_run'] >= 20
assert summary['critical_failures'] == 0, report
assert summary['status'] in ['healthy', 'degraded']

dash = spine.dashboard()
assert dash['spine'] == 'security_spine'
assert dash['security_gates'] >= 4
assert dash['guardian_rules'] >= 5
assert dash['permission_roles'] >= 4
assert dash['lift_permissions'] >= 9
assert dash['compliance_rules'] >= 5

print('SECURITY SPINE V1.1 VALIDATION PASSED')
print('Status:', summary['status'])
print('Checks run:', summary['checks_run'])
print('Critical failures:', summary['critical_failures'])
print('Warnings:', summary['warnings'])
print('Enforcement enabled:', summary['enforcement_enabled'])
""")

# Patch dashboard server to include Security Spine.
server = ROOT / "src" / "dashboard" / "server.py"
text = server.read_text(encoding="utf-8")

if "from tower.security_spine import SecuritySpine" not in text:
    text = text.replace(
        "from tower.penthouse_readiness import PenthouseReadiness",
        "from tower.penthouse_readiness import PenthouseReadiness\nfrom tower.security_spine import SecuritySpine"
    )

if '<div class="panel"><h2>Security Spine</h2><pre id="security_spine_panel"></pre></div>' not in text:
    text = text.replace(
        '<div class="panel"><h2>Penthouse Readiness</h2><pre id="penthouse_panel"></pre></div>',
        '<div class="panel"><h2>Penthouse Readiness</h2><pre id="penthouse_panel"></pre></div>\n<div class="panel"><h2>Security Spine</h2><pre id="security_spine_panel"></pre></div>'
    )

if 'let sec = await (await fetch("/api/security_spine")).json();' not in text:
    text = text.replace(
        'let ph = await (await fetch("/api/penthouse_readiness")).json();',
        'let ph = await (await fetch("/api/penthouse_readiness")).json();\n  let sec = await (await fetch("/api/security_spine")).json();'
    )

if "security_spine_panel.textContent" not in text:
    text = text.replace(
        "infrastructure_floor.textContent = JSON.stringify({",
        """security_spine_panel.textContent = JSON.stringify({
    spine:sec.spine,
    department:sec.department,
    status:sec.status,
    floors:sec.floors,
    execution_enabled:sec.execution_enabled,
    enforcement_enabled:sec.enforcement_enabled,
    security_gates:sec.security_gates,
    guardian_rules:sec.guardian_rules,
    permission_roles:sec.permission_roles,
    lift_permissions:sec.lift_permissions,
    compliance_rules:sec.compliance_rules,
    checks_run:sec.checks_run,
    critical_failures:sec.critical_failures,
    warnings:sec.warnings,
    passed:sec.passed,
    latest_report:sec.latest_report
  },null,2);

  infrastructure_floor.textContent = JSON.stringify({"""
    )

if 'if self.path.startswith("/api/security_spine"):' not in text:
    text = text.replace(
        'if self.path.startswith("/api/penthouse_readiness"):',
        'if self.path.startswith("/api/security_spine"):\n            return self.send_json(SecuritySpine().dashboard())\n        if self.path.startswith("/api/penthouse_readiness"):'
    )

server.write_text(text, encoding="utf-8")

readme = ROOT / "README.md"
existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

addition = """
Security Spine V1.1

Floors 28-32 are now registered as the Security Spine:

- Floor 28 Security Department
- Floor 29 Guardian Department
- Floor 30 Permissions Department
- Floor 31 Audit Department
- Floor 32 Compliance Department

This includes:
- Security gates
- Guardian readiness rules
- Permission roles
- Lift permission records
- Audit records
- Compliance rules
- Security spine validation
- Dashboard panel

Security Spine V1.1 does not enforce live blocking yet.
It does not execute providers, adapters, models, CLI commands, or kernel logic.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_security_spine_check.sh
./scripts/security_spine_status.sh
python3 tests/test_security_spine_v11.py
"""

if "Security Spine V1.1" not in existing:
    readme.write_text(existing + "\n\n" + addition, encoding="utf-8")

print("Security Spine V1.1 installed.")
print("Run:")
print("./scripts/run_security_spine_check.sh")
print("./scripts/security_spine_status.sh")
