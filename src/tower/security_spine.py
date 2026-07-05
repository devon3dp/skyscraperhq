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
