from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "executive_command.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_registry(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS executive_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    check_type TEXT,
    target TEXT,
    status TEXT,
    severity TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS executive_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    event_type TEXT,
    status TEXT,
    details TEXT
);
"""

class ExecutiveCommand:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policy(self):
        return load_registry("executive_command_policy.json", {})

    def executive_floors(self):
        return load_registry("executive_floors.json", [])

    def channels(self):
        return load_registry("executive_command_channels.json", [])

    def roadmap(self):
        return load_registry("strategic_roadmap.json", [])

    def resource_capacity(self):
        return load_registry("resource_capacity.json", {})

    def governance_rules(self):
        return load_registry("building_governance_rules.json", [])

    def council_records(self):
        return load_registry("executive_council_records.json", [])

    def infrastructure_links(self):
        return load_registry("infrastructure_command_links.json", [])

    def tower_handoff(self):
        return load_registry("tower_command_handoff.json", {})

    def record_check(self, check_type, target, ok, severity="critical", message="", details=None):
        item = {
            "check_type": check_type,
            "target": target,
            "status": "pass" if ok else "fail",
            "severity": severity,
            "message": message,
            "details": details or {}
        }
        self.conn.execute(
            "INSERT INTO executive_checks(ts, check_type, target, status, severity, details) VALUES (?, ?, ?, ?, ?, ?)",
            (now(), check_type, target, item["status"], severity, json.dumps(item))
        )
        self.conn.commit()
        return item

    def record_event(self, event_type, status, details):
        self.conn.execute(
            "INSERT INTO executive_events(ts, event_type, status, details) VALUES (?, ?, ?, ?)",
            (now(), event_type, status, json.dumps(details))
        )
        self.conn.commit()

    def validate_floor_manifests(self):
        folder_map = {
            "floor_46": "floors/floor_46_executive_support_department/floor_manifest.json",
            "floor_47": "floors/floor_47_executive_operations_department/floor_manifest.json",
            "floor_48": "floors/floor_48_strategic_planning_department/floor_manifest.json",
            "floor_49": "floors/floor_49_resource_management_department/floor_manifest.json",
            "floor_50": "floors/floor_50_building_governance_department/floor_manifest.json",
            "floor_51": "floors/floor_51_executive_council_department/floor_manifest.json",
            "floor_52": "floors/floor_52_infrastructure_command_department/floor_manifest.json",
            "floor_53": "floors/floor_53_tower_command_department/floor_manifest.json"
        }

        items = []
        for floor_id, rel in folder_map.items():
            path = ROOT / rel
            ok = path.exists()
            details = {"path": rel}

            if ok:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    details["manifest"] = data
                    ok = (
                        data.get("floor_id") == floor_id
                        and data.get("execution_enabled") is False
                        and data.get("kernel_installed") is False
                    )
                except Exception as e:
                    ok = False
                    details["error"] = str(e)

            items.append(self.record_check(
                "floor_manifest",
                floor_id,
                ok,
                "critical",
                f"{floor_id} executive manifest valid." if ok else f"{floor_id} executive manifest invalid.",
                details
            ))

        return items

    def validate_registry_records(self):
        checks = [
            ("executive_floors", len(self.executive_floors()) == 8, "Executive floors registered."),
            ("executive_command_channels", len(self.channels()) >= 8, "Executive command channels registered."),
            ("strategic_roadmap", len(self.roadmap()) >= 4, "Strategic roadmap registered."),
            ("resource_capacity", bool(self.resource_capacity()), "Resource capacity registry present."),
            ("building_governance_rules", len(self.governance_rules()) >= 6, "Building governance rules registered."),
            ("executive_council_records", len(self.council_records()) >= 2, "Executive council records registered."),
            ("infrastructure_command_links", len(self.infrastructure_links()) >= 5, "Infrastructure command links registered."),
            ("tower_command_handoff", bool(self.tower_handoff()), "Tower command handoff registry present.")
        ]

        return [
            self.record_check("registry", name, ok, "critical", message)
            for name, ok, message in checks
        ]

    def validate_executive_lift_routes(self):
        items = []
        try:
            from tower.lifts import LiftNetwork
            net = LiftNetwork()

            routes = [
                ("floor_46", "floor_47"),
                ("floor_47", "floor_48"),
                ("floor_48", "floor_49"),
                ("floor_49", "floor_50"),
                ("floor_50", "floor_51"),
                ("floor_51", "floor_52"),
                ("floor_52", "floor_53"),
                ("floor_53", "penthouse")
            ]

            for source, target in routes:
                try:
                    lift = net.choose(source, target, "executive_lift")
                    ok = lift.get("id") == "executive_lift"
                    items.append(self.record_check(
                        "executive_lift_route",
                        f"{source}->{target}",
                        ok,
                        "critical",
                        f"Executive route {source}->{target} selected {lift.get('id')}.",
                        {"source": source, "target": target, "selected": lift}
                    ))
                except Exception as e:
                    items.append(self.record_check(
                        "executive_lift_route",
                        f"{source}->{target}",
                        False,
                        "critical",
                        str(e)
                    ))

        except Exception as e:
            items.append(self.record_check("executive_lift_network", "all", False, "critical", str(e)))

        return items

    def validate_handoff_dependencies(self):
        items = []

        try:
            from tower.penthouse_readiness import PenthouseReadiness
            ph = PenthouseReadiness().dashboard()
            ok = (
                ph.get("readiness_status") == "ready_for_future_qsb_kernel_4_5"
                and ph.get("kernel_installed") is False
                and ph.get("kernel_logic_present") is False
            )
            items.append(self.record_check(
                "penthouse_dependency",
                "penthouse_readiness",
                ok,
                "critical",
                f"Penthouse readiness status: {ph.get('readiness_status')}.",
                {"penthouse": ph}
            ))
        except Exception as e:
            items.append(self.record_check("penthouse_dependency", "penthouse_readiness", False, "critical", str(e)))

        try:
            from tower.security_spine import SecuritySpine
            sec = SecuritySpine().dashboard()
            ok = (
                sec.get("status") in ["healthy", "degraded"]
                and sec.get("execution_enabled") is False
                and sec.get("enforcement_enabled") is False
            )
            items.append(self.record_check(
                "security_dependency",
                "security_spine",
                ok,
                "critical",
                f"Security spine status: {sec.get('status')}.",
                {"security": sec}
            ))
        except Exception as e:
            items.append(self.record_check("security_dependency", "security_spine", False, "critical", str(e)))

        try:
            from tower.expansion_planning import ExpansionPlanning
            exp = ExpansionPlanning().dashboard()
            ok = exp.get("expansion_status") in ["healthy", "degraded"]
            items.append(self.record_check(
                "expansion_dependency",
                "floor_36",
                ok,
                "warning",
                f"Expansion planning status: {exp.get('expansion_status')}.",
                {"expansion": exp}
            ))
        except Exception as e:
            items.append(self.record_check("expansion_dependency", "floor_36", False, "warning", str(e)))

        try:
            from tower.infrastructure_services import InfrastructureServices
            infra = InfrastructureServices().dashboard()
            ok = infra.get("infrastructure_status") in ["healthy", "degraded"]
            items.append(self.record_check(
                "infrastructure_dependency",
                "floor_35",
                ok,
                "warning",
                f"Infrastructure status: {infra.get('infrastructure_status')}.",
                {"infrastructure": infra}
            ))
        except Exception as e:
            items.append(self.record_check("infrastructure_dependency", "floor_35", False, "warning", str(e)))

        return items

    def validate_no_kernel_logic(self):
        forbidden = [
            ROOT / "penthouse" / "qsb_kernel_4_5.py",
            ROOT / "penthouse" / "kernel.py",
            ROOT / "src" / "tower" / "qsb_kernel_4_5.py",
            ROOT / "src" / "tower" / "kernel.py"
        ]
        present = [str(p.relative_to(ROOT)) for p in forbidden if p.exists()]

        return [self.record_check(
            "kernel_absence",
            "future_kernel_files",
            not present,
            "critical",
            "Kernel files absent, as required." if not present else "Kernel files found before installation.",
            {"present": present}
        )]

    def executive_summary(self):
        return {
            "ts": now(),
            "floor": "executive_command_spine",
            "department": "Executive Command Spine",
            "version": "1.1",
            "floors": [f.get("floor_id") for f in self.executive_floors()],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "command_execution_enabled": False,
            "roadmap": self.roadmap(),
            "resource_capacity": self.resource_capacity(),
            "governance_rules": self.governance_rules(),
            "council_records": self.council_records(),
            "infrastructure_command_links": self.infrastructure_links(),
            "tower_command_handoff": self.tower_handoff()
        }

    def run_executive_command_check(self):
        items = []
        items.extend(self.validate_floor_manifests())
        items.extend(self.validate_registry_records())
        items.extend(self.validate_executive_lift_routes())
        items.extend(self.validate_handoff_dependencies())
        items.extend(self.validate_no_kernel_logic())

        critical_failures = len([i for i in items if i["status"] == "fail" and i["severity"] == "critical"])
        warnings = len([i for i in items if i["status"] == "fail" and i["severity"] == "warning"])

        status = "healthy" if critical_failures == 0 and warnings == 0 else "degraded" if critical_failures == 0 else "critical"

        summary = {
            "ts": now(),
            "spine": "executive_command_spine",
            "version": "1.1",
            "status": status,
            "floors": [f"floor_{i}" for i in range(46, 54)],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "command_execution_enabled": False,
            "checks_run": len(items),
            "critical_failures": critical_failures,
            "warnings": warnings,
            "passed": len([i for i in items if i["status"] == "pass"]),
            "next_recommended_phase": "Ground Floor Reception and Command Lobby V1.1"
        }

        report = {
            "summary": summary,
            "items": items,
            "executive_summary": self.executive_summary()
        }

        out = ROOT / "floors" / "floor_53_tower_command_department" / "tower_command_records" / "latest_executive_command_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

        self.record_event("executive_command_check", status, summary)

        return report

    def recent_checks(self, limit=30):
        rows = self.conn.execute("SELECT * FROM executive_checks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def recent_events(self, limit=20):
        rows = self.conn.execute("SELECT * FROM executive_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        report = self.run_executive_command_check()
        summary = report["summary"]
        exec_summary = report["executive_summary"]

        return {
            "database": str(DB),
            "spine": "executive_command_spine",
            "department": "Executive Command Spine",
            "version": "1.1",
            "status": summary["status"],
            "floors": summary["floors"],
            "kernel_installed": False,
            "kernel_logic_present": False,
            "execution_enabled": False,
            "command_execution_enabled": False,
            "executive_floors": len(self.executive_floors()),
            "command_channels": len(self.channels()),
            "governance_rules": len(self.governance_rules()),
            "roadmap_items": len(self.roadmap()),
            "resource_capacity": exec_summary["resource_capacity"],
            "tower_command_handoff": exec_summary["tower_command_handoff"],
            "checks_run": summary["checks_run"],
            "critical_failures": summary["critical_failures"],
            "warnings": summary["warnings"],
            "passed": summary["passed"],
            "next_recommended_phase": summary["next_recommended_phase"],
            "latest_report": "floors/floor_53_tower_command_department/tower_command_records/latest_executive_command_report.json",
            "recent_checks": self.recent_checks(10),
            "recent_events": self.recent_events(10),
            "policy": self.policy()
        }

if __name__ == "__main__":
    print(json.dumps(ExecutiveCommand().dashboard(), indent=2))
